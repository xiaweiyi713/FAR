"""Build a deterministic paired dev error analysis for a RAMDocs suite."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256, verify_active_protocol
from experiments.ramdocs_suite import verify_suite


def _by_id(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result = {str(row[key]): row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"duplicate {key} values")
    return result


def _outcome(candidate: dict[str, Any], baseline: dict[str, Any]) -> str:
    pair = (int(candidate["ramdocs_exact_match"]), int(baseline["ramdocs_exact_match"]))
    return {
        (1, 1): "both_correct",
        (1, 0): "far_only",
        (0, 1): "baseline_only",
        (0, 0): "both_incorrect",
    }[pair]


def _failure_reasons(score: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if float(score["gold_answer_coverage"]) < 1.0:
        reasons.append("missing_gold")
    if float(score["wrong_answer_exclusion"]) < 1.0:
        reasons.append("contains_wrong")
    return reasons


def _prediction_summary(prediction: dict[str, Any]) -> dict[str, Any]:
    metadata = prediction.get("metadata", {})
    revisions = metadata.get("revision_trace", []) if isinstance(metadata, dict) else []
    answer = str(prediction.get("answer", ""))
    return {
        "answer_chars": len(answer),
        "answer_words": len(answer.split()),
        "predicted_conflict": bool(prediction.get("predicted_conflict_types", [])),
        "revision_changed": any(bool(item.get("changed")) for item in revisions),
    }


def _group_summary(
    sample_ids: list[str],
    scores: dict[str, dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not sample_ids:
        return {"samples": 0}
    prediction_rows = [_prediction_summary(predictions[sample_id]) for sample_id in sample_ids]
    score_rows = [scores[sample_id] for sample_id in sample_ids]
    failures = Counter(
        reason for score in score_rows for reason in _failure_reasons(score)
    )
    return {
        "samples": len(sample_ids),
        "exact_match": mean(float(row["ramdocs_exact_match"]) for row in score_rows),
        "gold_answer_coverage": mean(float(row["gold_answer_coverage"]) for row in score_rows),
        "wrong_answer_exclusion": mean(float(row["wrong_answer_exclusion"]) for row in score_rows),
        "unsupported_sentence_rate": mean(
            float(row["unsupported_sentence_rate"]) for row in score_rows
        ),
        "mean_answer_chars": mean(int(row["answer_chars"]) for row in prediction_rows),
        "predicted_conflict_rate": mean(
            int(bool(row["predicted_conflict"])) for row in prediction_rows
        ),
        "revision_changed_rate": mean(
            int(bool(row["revision_changed"])) for row in prediction_rows
        ),
        "failure_reasons": dict(sorted(failures.items())),
    }


def build_analysis(
    data_dir: Path,
    suite_dir: Path,
    output_dir: Path,
    *,
    baseline_method: str = "multi_query_rag",
) -> dict[str, Any]:
    verify_active_protocol()
    audit = verify_suite(suite_dir, data_dir)
    if not audit["valid"]:
        raise ValueError(f"RAMDocs suite is invalid: {audit['errors']}")
    suite = json.loads((suite_dir / "suite_manifest.json").read_text(encoding="utf-8"))
    if suite.get("split") != "dev" or suite.get("samples") != 350:
        raise ValueError("error analysis requires the complete frozen 350-row dev suite")
    if suite.get("strongest_baseline") != baseline_method:
        raise ValueError("baseline_method must match the suite-selected strongest baseline")

    tasks = _by_id(
        [row for row in read_jsonl(data_dir / "tasks.jsonl") if row.get("split") == "dev"],
        "id",
    )
    far_scores_path = suite_dir / "evaluations/far/scores.jsonl"
    baseline_scores_path = suite_dir / f"evaluations/{baseline_method}/scores.jsonl"
    far_predictions_path = suite_dir / "runs/far/predictions.jsonl"
    baseline_predictions_path = suite_dir / f"runs/{baseline_method}/predictions.jsonl"
    far_scores = _by_id(read_jsonl(far_scores_path), "sample_id")
    baseline_scores = _by_id(read_jsonl(baseline_scores_path), "sample_id")
    far_predictions = _by_id(read_jsonl(far_predictions_path), "sample_id")
    baseline_predictions = _by_id(read_jsonl(baseline_predictions_path), "sample_id")
    expected_ids = set(tasks)
    for name, rows in (
        ("far_scores", far_scores),
        ("baseline_scores", baseline_scores),
        ("far_predictions", far_predictions),
        ("baseline_predictions", baseline_predictions),
    ):
        if set(rows) != expected_ids:
            raise ValueError(f"{name} sample IDs differ from frozen dev tasks")

    outcome_ids: dict[str, list[str]] = defaultdict(list)
    category_outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    gold_count_outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    wrong_count_outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    cases: list[dict[str, Any]] = []
    for sample_id in sorted(expected_ids):
        task = tasks[sample_id]
        outcome = _outcome(far_scores[sample_id], baseline_scores[sample_id])
        outcome_ids[outcome].append(sample_id)
        category_outcomes[str(task["category"])][outcome] += 1
        gold_count_outcomes[str(len(task["gold_answers"]))][outcome] += 1
        wrong_count_outcomes[str(len(task["wrong_answers"]))][outcome] += 1
        if outcome in {"far_only", "baseline_only"}:
            cases.append(
                {
                    "sample_id": sample_id,
                    "outcome": outcome,
                    "category": task["category"],
                    "question": task["question"],
                    "gold_answers": task["gold_answers"],
                    "wrong_answers": task["wrong_answers"],
                    "document_count": len(task["document_ids"]),
                    "far_score": far_scores[sample_id],
                    "baseline_score": baseline_scores[sample_id],
                    "far_answer": far_predictions[sample_id]["answer"],
                    "baseline_answer": baseline_predictions[sample_id]["answer"],
                    "far_prediction_summary": _prediction_summary(far_predictions[sample_id]),
                    "baseline_prediction_summary": _prediction_summary(
                        baseline_predictions[sample_id]
                    ),
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    cases_path = output_dir / "discordant_cases.jsonl"
    write_jsonl(cases_path, cases)
    comparison = json.loads(
        (suite_dir / f"comparisons/far_vs_{baseline_method}.json").read_text(
            encoding="utf-8"
        )
    )
    outcome_order = ("both_correct", "far_only", "baseline_only", "both_incorrect")
    report = {
        "schema_version": "far-ramdocs-dev-error-analysis-v1",
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "split": "dev",
        "samples": len(expected_ids),
        "candidate_method": "far",
        "baseline_method": baseline_method,
        "gate_a_passed": comparison["gate_a_passed"],
        "stop_rule_triggered": suite["stop_rule_triggered"],
        "paired_comparison": comparison,
        "paired_outcomes": {
            outcome: len(outcome_ids.get(outcome, [])) for outcome in outcome_order
        },
        "method_summaries": {
            "far": _group_summary(sorted(expected_ids), far_scores, far_predictions),
            baseline_method: _group_summary(
                sorted(expected_ids), baseline_scores, baseline_predictions
            ),
        },
        "discordant_summaries": {
            outcome: {
                "far": _group_summary(outcome_ids[outcome], far_scores, far_predictions),
                baseline_method: _group_summary(
                    outcome_ids[outcome], baseline_scores, baseline_predictions
                ),
            }
            for outcome in ("far_only", "baseline_only")
        },
        "segments": {
            "category": {
                key: {outcome: value.get(outcome, 0) for outcome in outcome_order}
                for key, value in sorted(category_outcomes.items())
            },
            "gold_answer_count": {
                key: {outcome: value.get(outcome, 0) for outcome in outcome_order}
                for key, value in sorted(gold_count_outcomes.items(), key=lambda item: int(item[0]))
            },
            "wrong_answer_count": {
                key: {outcome: value.get(outcome, 0) for outcome in outcome_order}
                for key, value in sorted(
                    wrong_count_outcomes.items(), key=lambda item: int(item[0])
                )
            },
        },
        "source_fingerprints": {
            "suite_manifest": sha256_file(suite_dir / "suite_manifest.json"),
            "tasks": sha256_file(data_dir / "tasks.jsonl"),
            "far_scores": sha256_file(far_scores_path),
            "baseline_scores": sha256_file(baseline_scores_path),
            "far_predictions": sha256_file(far_predictions_path),
            "baseline_predictions": sha256_file(baseline_predictions_path),
            "discordant_cases": sha256_file(cases_path),
        },
        "publication_gold": False,
        "human_iaa": False,
    }
    write_json(output_dir / "report.json", report)
    _write_markdown(output_dir / "README.md", report)
    return report


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    comparison = report["paired_comparison"]
    paired = comparison["comparison"]
    mcnemar = comparison["mcnemar"]
    methods = report["method_summaries"]
    baseline = report["baseline_method"]
    outcomes = report["paired_outcomes"]
    lines = [
        "# RAMDocs dev error analysis",
        "",
        "This is a deterministic analysis of the frozen 350-row dev evidence. "
        "It is not test-set evidence, human annotation, or human IAA.",
        "",
        "## Gate result",
        "",
        f"- G-A passed: `{str(report['gate_a_passed']).lower()}`",
        f"- FAR exact match: `{methods['far']['exact_match']:.6f}`",
        f"- {baseline} exact match: `{methods[baseline]['exact_match']:.6f}`",
        f"- paired difference: `{paired['candidate_minus_baseline']:.6f}`",
        f"- bootstrap 95% CI: `[{paired['lower']:.6f}, {paired['upper']:.6f}]`",
        f"- McNemar p: `{mcnemar['p_value']:.6f}`",
        "- The preregistered stop rule is active; Phase B must not start.",
        "",
        "## Paired outcomes",
        "",
        "| Outcome | Samples |",
        "|---|---:|",
    ]
    lines.extend(f"| {name} | {outcomes[name]} |" for name in outcomes)
    lines.extend(
        [
            "",
            "## Aggregate diagnostics",
            "",
            "| Method | Gold coverage | Wrong exclusion | Unsupported sentences |",
            "|---|---:|---:|---:|",
            f"| FAR | {methods['far']['gold_answer_coverage']:.4f} | "
            f"{methods['far']['wrong_answer_exclusion']:.4f} | "
            f"{methods['far']['unsupported_sentence_rate']:.4f} |",
            f"| {baseline} | {methods[baseline]['gold_answer_coverage']:.4f} | "
            f"{methods[baseline]['wrong_answer_exclusion']:.4f} | "
            f"{methods[baseline]['unsupported_sentence_rate']:.4f} |",
            "",
            "## Category breakdown",
            "",
            "| Category | Both correct | FAR only | Baseline only | Both incorrect |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for category, values in report["segments"]["category"].items():
        lines.append(
            f"| {category} | {values['both_correct']} | {values['far_only']} | "
            f"{values['baseline_only']} | {values['both_incorrect']} |"
        )
    lines.extend(
        [
            "",
            "The complete 32-row discordant audit trail is in "
            "`discordant_cases.jsonl`.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--suite-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-method", default="multi_query_rag")
    args = parser.parse_args()
    report = build_analysis(
        args.data_dir,
        args.suite_dir,
        args.output_dir,
        baseline_method=args.baseline_method,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
