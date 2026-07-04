"""Frozen RAMDocs scoring used by the 2+4 external-evidence path."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from eval.stats import mcnemar_exact, paired_bootstrap_comparison


def normalize_ramdocs_answer(text: str) -> tuple[str, ...]:
    """Apply the frozen Unicode/case/article/punctuation/whitespace normalizer."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"\b(?:a|an|the)\b", " ", normalized)
    normalized = "".join(
        " " if unicodedata.category(char).startswith("P") else char for char in normalized
    )
    return tuple(normalized.split())


def _contains_phrase(container: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    if not phrase or len(phrase) > len(container):
        return False
    return any(
        container[index : index + len(phrase)] == phrase
        for index in range(len(container) - len(phrase) + 1)
    )


def score_ramdocs_answer(
    prediction: str,
    gold_answers: list[str],
    wrong_answers: list[str],
) -> dict[str, float]:
    predicted = normalize_ramdocs_answer(prediction)
    gold_hits = [
        _contains_phrase(predicted, normalize_ramdocs_answer(answer)) for answer in gold_answers
    ]
    wrong_hits = [
        _contains_phrase(predicted, normalize_ramdocs_answer(answer)) for answer in wrong_answers
    ]
    gold_coverage = sum(gold_hits) / len(gold_hits) if gold_hits else 0.0
    wrong_exclusion = float(not any(wrong_hits))
    return {
        "ramdocs_exact_match": float(bool(gold_hits) and all(gold_hits) and not any(wrong_hits)),
        "gold_answer_coverage": gold_coverage,
        "wrong_answer_exclusion": wrong_exclusion,
    }


def unsupported_sentence_rate(prediction: str, correct_documents: list[str]) -> float:
    """Return the preregistered lexical support proxy, not a factuality judgement."""

    cleaned = re.sub(r"\[[^\]]+\]", " ", prediction)
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?:[.!?。！？]+|\n+)", cleaned)
        if sentence.strip()
    ]
    if not sentences:
        return 1.0
    document_tokens = [normalize_ramdocs_answer(text) for text in correct_documents]

    def token_f1(left: tuple[str, ...], right: tuple[str, ...]) -> float:
        if not left or not right:
            return 0.0
        common = sum((Counter(left) & Counter(right)).values())
        if common == 0:
            return 0.0
        precision = common / len(left)
        recall = common / len(right)
        return 2 * precision * recall / (precision + recall)

    unsupported = 0
    for sentence in sentences:
        tokens = normalize_ramdocs_answer(sentence)
        best = max((token_f1(tokens, document) for document in document_tokens), default=0.0)
        unsupported += best < 0.50
    return unsupported / len(sentences)


def _unique(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        item_id = str(row[key])
        if item_id in result:
            raise ValueError(f"duplicate {key}: {item_id}")
        result[item_id] = row
    return result


def evaluate_ramdocs(
    tasks_path: Path,
    predictions_path: Path,
    corpus_path: Path,
    output_dir: Path,
    *,
    split: str = "dev",
    allow_partial: bool = False,
) -> dict[str, Any]:
    tasks = _unique([row for row in read_jsonl(tasks_path) if row["split"] == split], "id")
    predictions = _unique(read_jsonl(predictions_path), "sample_id")
    corpus = _unique(read_jsonl(corpus_path), "doc_id")
    if allow_partial and set(predictions).issubset(tasks):
        tasks = {sample_id: tasks[sample_id] for sample_id in predictions}
    elif set(tasks) != set(predictions):
        raise ValueError("RAMDocs evaluation requires exactly the selected split predictions")
    scores: list[dict[str, Any]] = []
    for sample_id in sorted(tasks):
        task = tasks[sample_id]
        prediction = predictions[sample_id]
        metrics = score_ramdocs_answer(
            str(prediction["answer"]),
            [str(item) for item in task["gold_answers"]],
            [str(item) for item in task["wrong_answers"]],
        )
        correct_documents = [
            str(corpus[doc_id]["content"])
            for doc_id in map(str, task["document_ids"])
            if corpus[doc_id].get("metadata", {}).get("document_type") == "correct"
        ]
        metrics["unsupported_sentence_rate"] = unsupported_sentence_rate(
            str(prediction["answer"]), correct_documents
        )
        scores.append(
            {
                "sample_id": sample_id,
                "method": str(prediction.get("method", "unknown")),
                "category": str(task["category"]),
                "split": split,
                **metrics,
            }
        )
    metrics = {
        name: sum(float(row[name]) for row in scores) / len(scores)
        for name in (
            "ramdocs_exact_match",
            "gold_answer_coverage",
            "wrong_answer_exclusion",
            "unsupported_sentence_rate",
        )
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    scores_path = output_dir / "scores.jsonl"
    write_jsonl(scores_path, scores)
    report = {
        "schema_version": "far-ramdocs-evaluation-v1",
        "split": split,
        "samples": len(scores),
        "partial": allow_partial,
        "method": scores[0]["method"],
        "metrics": metrics,
        "scoring_protocol": "all_normalized_gold_answers_and_no_normalized_wrong_answers",
        "publication_gold": False,
        "provenance": {
            "tasks_sha256": sha256_file(tasks_path),
            "predictions_sha256": sha256_file(predictions_path),
            "corpus_sha256": sha256_file(corpus_path),
            "scores_sha256": sha256_file(scores_path),
        },
    }
    write_json(output_dir / "report.json", report)
    return report


def compare_ramdocs(
    baseline_scores: Path,
    candidate_scores: Path,
    output_path: Path,
    *,
    resamples: int = 2000,
    seed: int = 1729,
) -> dict[str, Any]:
    baseline = read_jsonl(baseline_scores)
    candidate = read_jsonl(candidate_scores)
    comparison = paired_bootstrap_comparison(
        baseline,
        candidate,
        "ramdocs_exact_match",
        resamples=resamples,
        seed=seed,
    )
    baseline_by_id = {str(row["sample_id"]): row for row in baseline}
    candidate_by_id = {str(row["sample_id"]): row for row in candidate}
    ordered_ids = sorted(baseline_by_id)
    mcnemar = mcnemar_exact(
        [bool(baseline_by_id[sample_id]["ramdocs_exact_match"]) for sample_id in ordered_ids],
        [bool(candidate_by_id[sample_id]["ramdocs_exact_match"]) for sample_id in ordered_ids],
    )
    result = {
        "schema_version": "far-ramdocs-paired-comparison-v1",
        "comparison": comparison,
        "mcnemar": mcnemar,
        "gate_a_passed": float(comparison["lower"]) > 0.0
        or (
            float(comparison["candidate_minus_baseline"]) > 0.0 and float(mcnemar["p_value"]) < 0.05
        ),
        "baseline_scores_sha256": sha256_file(baseline_scores),
        "candidate_scores_sha256": sha256_file(candidate_scores),
    }
    write_json(output_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--tasks", type=Path, required=True)
    evaluate_parser.add_argument("--predictions", type=Path, required=True)
    evaluate_parser.add_argument("--corpus", type=Path, required=True)
    evaluate_parser.add_argument("--output-dir", type=Path, required=True)
    evaluate_parser.add_argument("--split", choices=("dev", "test"), default="dev")
    evaluate_parser.add_argument("--allow-partial", action="store_true")
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--baseline-scores", type=Path, required=True)
    compare_parser.add_argument("--candidate-scores", type=Path, required=True)
    compare_parser.add_argument("--output", type=Path, required=True)
    compare_parser.add_argument("--resamples", type=int, default=2000)
    compare_parser.add_argument("--seed", type=int, default=1729)
    args = parser.parse_args()
    if args.command == "evaluate":
        result = evaluate_ramdocs(
            args.tasks,
            args.predictions,
            args.corpus,
            args.output_dir,
            split=args.split,
            allow_partial=args.allow_partial,
        )
    else:
        result = compare_ramdocs(
            args.baseline_scores,
            args.candidate_scores,
            args.output,
            resamples=args.resamples,
            seed=args.seed,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
