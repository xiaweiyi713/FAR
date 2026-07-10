"""Build a candidate set from an optional author-internal VeraBench checkout.

Pass ``--source-dir`` or set ``FAR_VERA_HOME``; public FAR runtime paths do not
depend on this source checkout.
"""

from __future__ import annotations

import argparse
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, stable_rank, write_json, write_jsonl

_VERA_HOME = os.getenv("FAR_VERA_HOME")
_VERA_BENCH_DIR = os.getenv("VERARAG_BENCH_DIR")
DEFAULT_SOURCE = (
    Path(_VERA_BENCH_DIR).expanduser()
    if _VERA_BENCH_DIR
    else Path(_VERA_HOME).expanduser() / "data/verabench"
    if _VERA_HOME
    else None
)
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1]
SEED = 1729
PER_CATEGORY = 60

CATEGORIES = (
    "temporal_shift",
    "numerical_conflict",
    "entity_confusion",
    "causal_overclaim",
    "multi_source_conflict",
)
SPLIT_TARGETS = {
    "train": {"total": 180, "per_category": 36},
    "dev": {"total": 60, "per_category": 12},
    "test": {"total": 60, "per_category": 12},
}
YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
NUMBER = re.compile(
    r"(?<![A-Za-z0-9_.,])(\d+(?:\.\d+)?)(%|％|万|亿|个|GB|TB(?:/s)?|million|billion)?",
    re.I,
)


def _first_evidence(question: dict[str, Any]) -> dict[str, Any] | None:
    evidence = question.get("evidence", [])
    return evidence[0] if evidence else None


def _mutate_year(answer: str) -> str | None:
    match = YEAR.search(answer)
    if match is None:
        return None
    value = int(match.group())
    replacement = str(value + 1 if value < 2099 else value - 1)
    return f"{answer[: match.start()]}{replacement}{answer[match.end() :]}"


def _temporal_candidate(question: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    answer = str(question["ground_truth_answer"])
    for match in YEAR.finditer(answer):
        evidence = next(
            (
                item
                for item in question.get("evidence", [])
                if match.group() in str(item.get("text_span", ""))
            ),
            None,
        )
        if evidence is None:
            continue
        value = int(match.group())
        replacement = str(value + 1 if value < 2099 else value - 1)
        return f"{answer[: match.start()]}{replacement}{answer[match.end() :]}", evidence
    return None


def _mutate_number(answer: str) -> str | None:
    for match in NUMBER.finditer(answer):
        raw_number, unit = match.groups()
        if unit is None and len(raw_number) == 4 and 1900 <= int(float(raw_number)) <= 2099:
            continue
        value = float(raw_number)
        changed = value + max(1.0, abs(value) * 0.1)
        replacement = f"{changed:.1f}".rstrip("0").rstrip(".") + (unit or "")
        return f"{answer[: match.start()]}{replacement}{answer[match.end() :]}"
    return None


def _numerical_candidate(question: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    answer = str(question["ground_truth_answer"])
    for match in NUMBER.finditer(answer):
        raw_number, unit = match.groups()
        if unit is None and len(raw_number) == 4 and 1900 <= int(float(raw_number)) <= 2099:
            continue
        original = match.group()
        evidence = next(
            (
                item
                for item in question.get("evidence", [])
                if original in str(item.get("text_span", ""))
            ),
            None,
        )
        if evidence is None:
            continue
        value = float(raw_number)
        changed = value + max(1.0, abs(value) * 0.1)
        replacement = f"{changed:.1f}".rstrip("0").rstrip(".") + (unit or "")
        return f"{answer[: match.start()]}{replacement}{answer[match.end() :]}", evidence
    return None


def _answer_entity(
    question: dict[str, Any],
    corpus: dict[str, dict[str, Any]],
) -> str | None:
    answer = str(question["ground_truth_answer"])
    entities = [
        str(entity)
        for evidence in question.get("evidence", [])
        for entity in corpus[evidence["doc_id"]].get("entities", [])
        if str(entity) in answer
    ]
    return max(entities, key=len) if entities else None


def _mutate_entity(
    question: dict[str, Any],
    corpus: dict[str, dict[str, Any]],
    distractors: tuple[str, ...],
) -> str | None:
    entity = _answer_entity(question, corpus)
    if entity is None:
        return None
    candidates = [
        item
        for item in distractors
        if item != entity and item not in question["ground_truth_answer"]
    ]
    if not candidates:
        return None
    distractor = min(candidates, key=lambda item: stable_rank(SEED, question["id"], item))
    return str(question["ground_truth_answer"]).replace(entity, distractor, 1)


def _entity_candidate(
    question: dict[str, Any],
    corpus: dict[str, dict[str, Any]],
    distractors: tuple[str, ...],
) -> tuple[str, dict[str, Any]] | None:
    answer = str(question["ground_truth_answer"])
    candidates = []
    for evidence in question.get("evidence", []):
        span = str(evidence.get("text_span", ""))
        for entity in corpus[evidence["doc_id"]].get("entities", []):
            entity = str(entity)
            if entity and entity in answer and entity in span:
                candidates.append((entity, evidence))
    if not candidates:
        return None
    entity, evidence = min(
        candidates,
        key=lambda item: stable_rank(SEED, str(question["id"]), item[0], item[1]["doc_id"]),
    )
    alternatives = [item for item in distractors if item != entity and item not in answer]
    if not alternatives:
        return None
    distractor = min(alternatives, key=lambda item: stable_rank(SEED, question["id"], item))
    return answer.replace(entity, distractor, 1), evidence


def _generic_mutation(
    question: dict[str, Any],
    corpus: dict[str, dict[str, Any]],
    distractors: tuple[str, ...],
) -> str | None:
    return (
        _mutate_number(str(question["ground_truth_answer"]))
        or _mutate_year(str(question["ground_truth_answer"]))
        or _mutate_entity(question, corpus, distractors)
    )


def _eligible(
    category: str,
    question: dict[str, Any],
    corpus: dict[str, dict[str, Any]],
    distractors: tuple[str, ...],
) -> tuple[str, dict[str, Any]] | None:
    answer = str(question["ground_truth_answer"]).strip()
    first = _first_evidence(question)
    if not answer or first is None:
        return None
    if category == "temporal_shift":
        return _temporal_candidate(question)
    if category == "numerical_conflict":
        return _numerical_candidate(question)
    if category == "entity_confusion":
        return _entity_candidate(question, corpus, distractors)
    if category == "causal_overclaim":
        topic = str(question["question"]).strip("?？。 ")
        return f"{answer} 这一结果完全由“{topic}”所述因素导致。", first
    return (
        _numerical_candidate(question)
        or _temporal_candidate(question)
        or _entity_candidate(question, corpus, distractors)
    )


def _select_records(
    questions: list[dict[str, Any]],
    corpus: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    distractors = tuple(
        sorted(
            {str(entity) for document in corpus.values() for entity in document.get("entities", [])}
        )
    )
    records: list[dict[str, Any]] = []
    for category in CATEGORIES:
        candidates = []
        for question in questions:
            candidate = _eligible(category, question, corpus, distractors)
            if candidate is None:
                continue
            initial, evidence = candidate
            if initial == question["ground_truth_answer"]:
                continue
            candidates.append(
                {
                    "category": category,
                    "question": question,
                    "initial_answer": initial,
                    "evidence": evidence,
                    "dependency_doc_id": evidence["doc_id"],
                }
            )
        candidates.sort(key=lambda row: stable_rank(SEED, category, str(row["question"]["id"])))
        if len(candidates) < PER_CATEGORY:
            raise ValueError(f"{category}: need {PER_CATEGORY} candidates, found {len(candidates)}")
        records.extend(candidates[:PER_CATEGORY])
    return records


def _assign_splits(records: list[dict[str, Any]]) -> dict[str, str]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record["dependency_doc_id"])].append(record)
    counts: dict[str, Counter[str]] = {split: Counter() for split in SPLIT_TARGETS}
    assignment: dict[str, str] = {}
    ordered_groups = sorted(
        groups.items(),
        key=lambda item: (-len(item[1]), stable_rank(SEED, "split", item[0])),
    )
    for doc_id, members in ordered_groups:
        member_counts = Counter(str(item["category"]) for item in members)
        costs: dict[str, float] = {}
        for split in SPLIT_TARGETS:
            target = SPLIT_TARGETS[split]
            total_ratio = (counts[split]["total"] + len(members)) / target["total"]
            category_ratios = [
                (counts[split][category] + member_counts[category]) / target["per_category"]
                for category in CATEGORIES
            ]
            overshoot = sum(max(0.0, ratio - 1.0) ** 2 for ratio in category_ratios)
            balance = sum(ratio**2 for ratio in category_ratios) + total_ratio**2
            costs[split] = overshoot * 1000 + balance

        selected = min(SPLIT_TARGETS, key=lambda split: (costs[split], split))
        assignment[doc_id] = selected
        counts[selected]["total"] += len(members)
        counts[selected].update(member_counts)
    return assignment


def _conflict_spec(category: str) -> tuple[str, str, str]:
    return {
        "temporal_shift": ("temporal", "temporal", "correct_temporal"),
        "numerical_conflict": ("numerical", "numerical", "replace_numerical"),
        "entity_confusion": ("factual", "entity", "requalify_entity"),
        "causal_overclaim": ("causal", "causal", "downgrade_causal_to_correlation"),
        "multi_source_conflict": (
            "factual",
            "source_reliability",
            "prefer_reliable_source",
        ),
    }[category]


def _build_sample(
    index: int,
    record: dict[str, Any],
    split: str,
    corpus: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sample_id = f"F{index:04d}"
    category = str(record["category"])
    question = record["question"]
    first = record["evidence"]
    source_doc = corpus[first["doc_id"]]
    claim_type, conflict_type, action = _conflict_spec(category)
    correct_answer = str(question["ground_truth_answer"]).strip()
    initial_answer = str(record["initial_answer"]).strip()
    synthetic_docs: list[dict[str, Any]] = []
    counter_doc_id = str(first["doc_id"])
    counter_span = str(first["text_span"])

    if category == "causal_overclaim":
        counter_doc_id = f"{sample_id}-BOUNDARY"
        counter_span = (
            f"The source supports this answer: {correct_answer} "
            "It does not establish the added causal relationship; "
            "that causal wording is an overclaim."
        )
        synthetic_docs.append(
            {
                "doc_id": counter_doc_id,
                "title": f"Controlled causal-boundary note for {question['id']}",
                "content": counter_span,
                "source": "controlled_boundary",
                "date": None,
                "author": "FalsiRAG-Bench construction pipeline",
                "url": None,
                "license": "MIT-controlled-summary",
                "synthetic": True,
                "source_doc_id": first["doc_id"],
                "metadata": {"construction": "causal-entailment-boundary-v1"},
            }
        )
    elif category == "multi_source_conflict":
        initial_answer = f"An unverified secondary summary reports: {initial_answer}"
        misleading_id = f"{sample_id}-LOWREL"
        misleading_text = initial_answer
        synthetic_docs.append(
            {
                "doc_id": misleading_id,
                "title": f"Controlled low-reliability distractor for {question['id']}",
                "content": misleading_text,
                "source": "controlled_low_reliability",
                "date": source_doc.get("date"),
                "author": "FalsiRAG-Bench construction pipeline",
                "url": None,
                "license": "MIT-controlled-summary",
                "synthetic": True,
                "source_doc_id": first["doc_id"],
                "metadata": {"construction": "source-conflict-distractor-v1"},
            }
        )

    gold = {
        "evidence_id": f"{sample_id}-G1",
        "doc_id": first["doc_id"],
        "text_span": first["text_span"],
        "type": claim_type,
        "supports_claim": "C1",
    }
    counter = {
        "evidence_id": f"{sample_id}-C1",
        "doc_id": counter_doc_id,
        "text_span": counter_span,
        "refutes_claim": "C1",
        "conflict_type": conflict_type,
    }
    sample = {
        "id": sample_id,
        "category": category,
        "split": split,
        "question": question["question"],
        "initial_answer": initial_answer,
        "claims": [
            {
                "claim_id": "C1",
                "claim": initial_answer,
                "type": claim_type,
                "depends_on": [],
            }
        ],
        "gold_evidence": [gold],
        "counter_evidence": [counter],
        "conflict_type": conflict_type,
        "expected_revision": {"action": action, "revised_answer": correct_answer},
        "annotation_status": "machine_seeded",
        "source_metadata": {
            "source_dataset": "VeraBench-v1.1.2",
            "source_question_id": question["id"],
            "source_doc_ids": [first["doc_id"]],
            "dependency_group": first["doc_id"],
            "generation_protocol": f"falsirag-{category}-v1",
            "machine_seed_is_gold": False,
        },
    }
    return sample, synthetic_docs


def build(source_dir: Path, output_dir: Path) -> dict[str, Any]:
    questions = read_jsonl(source_dir / "questions.jsonl")
    corpus_rows = read_jsonl(source_dir / "corpus.jsonl")
    corpus = {row["doc_id"]: row for row in corpus_rows}
    records = _select_records(questions, corpus)
    split_by_doc = _assign_splits(records)
    category_order = {category: index for index, category in enumerate(CATEGORIES)}
    records.sort(
        key=lambda row: (
            category_order[str(row["category"])],
            stable_rank(SEED, str(row["category"]), str(row["question"]["id"])),
        )
    )

    samples: list[dict[str, Any]] = []
    synthetic_docs: list[dict[str, Any]] = []
    referenced_doc_ids: set[str] = set()
    for index, record in enumerate(records, start=1):
        split = split_by_doc[str(record["dependency_doc_id"])]
        sample, generated = _build_sample(index, record, split, corpus)
        samples.append(sample)
        synthetic_docs.extend(generated)
        referenced_doc_ids.update(sample["source_metadata"]["source_doc_ids"])
    output_corpus = [
        {
            **corpus[doc_id],
            "license": "MIT-controlled-summary",
            "synthetic": False,
            "source_doc_id": None,
            "metadata": {"source_dataset": "VeraBench-v1.1.2"},
        }
        for doc_id in sorted(referenced_doc_ids)
    ] + synthetic_docs
    output_corpus.sort(key=lambda row: row["doc_id"])

    corpus_path = output_dir / "corpus.jsonl"
    benchmark_path = output_dir / "falsirag_bench.jsonl"
    write_jsonl(corpus_path, output_corpus)
    write_jsonl(benchmark_path, samples)
    for split in ("train", "dev"):
        write_jsonl(
            output_dir / "splits" / f"{split}.jsonl",
            (sample for sample in samples if sample["split"] == split),
        )
    test_inputs = [
        {
            "id": sample["id"],
            "category": sample["category"],
            "split": "test",
            "question": sample["question"],
            "initial_answer": sample["initial_answer"],
        }
        for sample in samples
        if sample["split"] == "test"
    ]
    write_jsonl(output_dir / "splits" / "test_inputs.jsonl", test_inputs)

    assignments = {sample["id"]: sample["split"] for sample in samples}
    groups = {sample["id"]: sample["source_metadata"]["dependency_group"] for sample in samples}
    split_counts = Counter(sample["split"] for sample in samples)
    category_counts = Counter(sample["category"] for sample in samples)
    split_category_counts = {
        split: dict(Counter(sample["category"] for sample in samples if sample["split"] == split))
        for split in SPLIT_TARGETS
    }
    split_manifest = {
        "schema_version": "falsirag-split-manifest-v1",
        "seed": SEED,
        "assignment_method": "greedy balance over source-document dependency groups",
        "question_assignments": assignments,
        "dependency_group_by_question": groups,
        "split_counts": dict(split_counts),
        "split_category_counts": split_category_counts,
        "cross_split_dependency_groups": {},
        "test_policy": (
            "Test labels are present in the research archive but must not be used during method, "
            "prompt, retrieval, or calibration development. "
            "test_inputs.jsonl is the operational view."
        ),
    }
    write_json(output_dir / "split_manifest.json", split_manifest)
    manifest = {
        "schema_version": "falsirag-bench-manifest-v1",
        "dataset_id": "falsirag-bench-v0.2.0-candidate",
        "version": "0.2.0-candidate",
        "construction_seed": SEED,
        "counts": {
            "samples": len(samples),
            "documents": len(output_corpus),
            "categories": dict(category_counts),
            "splits": dict(split_counts),
            "synthetic_documents": sum(bool(row.get("synthetic")) for row in output_corpus),
        },
        "fingerprints": {
            "corpus_sha256": sha256_file(corpus_path),
            "benchmark_sha256": sha256_file(benchmark_path),
            "split_manifest_sha256": sha256_file(output_dir / "split_manifest.json"),
        },
        "source": {
            "dataset": "VeraBench-v1.1.2",
            "corpus_sha256": sha256_file(source_dir / "corpus.jsonl"),
            "questions_sha256": sha256_file(source_dir / "questions.jsonl"),
            "license": "MIT; upstream scenario/source materials retain their own terms",
        },
        "annotation": {
            "status": "machine_seeded",
            "machine_seed_is_gold": False,
            "required_annotators": 2,
            "required_adjudication": True,
            "minimum_binary_kappa": 0.6,
        },
        "publication_ready": False,
        "publication_blockers": [
            "two independent annotations per sample",
            "adjudication of disagreements",
            "Cohen's kappa report for conflict type and revision action",
            "externally held blind-test protocol",
        ],
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.source_dir is None:
        parser.error("--source-dir is required unless FAR_VERA_HOME is set")
    manifest = build(args.source_dir, args.output_dir)
    print(f"built {manifest['counts']['samples']} candidate samples at {args.output_dir}")


if __name__ == "__main__":
    main()
