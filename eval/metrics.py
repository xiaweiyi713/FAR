"""Answer, evidence, conflict, revision, and overclaim metrics."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PredictionRecord:
    sample_id: str
    answer: str
    evidence_ids: tuple[str, ...]
    predicted_conflict_types: tuple[str, ...] = ()
    revision_action: str | None = None
    method: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> PredictionRecord:
        return cls(
            sample_id=str(row["sample_id"]),
            answer=str(row["answer"]),
            evidence_ids=tuple(str(item) for item in row.get("evidence_ids", [])),
            predicted_conflict_types=tuple(
                str(item) for item in row.get("predicted_conflict_types", [])
            ),
            revision_action=(
                str(row["revision_action"]) if row.get("revision_action") is not None else None
            ),
            method=str(row.get("method", "unknown")),
            metadata=dict(row.get("metadata", {})),
        )


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\b(?:a|an|the)\b", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _soft_tokens(text: str) -> list[str]:
    normalized = _normalize(text)
    tokens = re.findall(r"\d+(?:\.\d+)?%?|[a-z]+(?:-[a-z]+)*", normalized)
    for run in re.findall(r"[\u4e00-\u9fff]+", normalized):
        tokens.extend(
            [run] if len(run) == 1 else [run[index : index + 2] for index in range(len(run) - 1)]
        )
    return tokens


def soft_f1(predicted: str, reference: str) -> float:
    """VeraRAG-compatible mixed Chinese/English lexical soft F1."""
    pred_normalized = _normalize(predicted).replace(" ", "")
    ref_normalized = _normalize(reference).replace(" ", "")
    if not pred_normalized and not ref_normalized:
        return 1.0
    if not pred_normalized or not ref_normalized:
        return 0.0
    if ref_normalized in pred_normalized:
        return 1.0
    pred_tokens = _soft_tokens(predicted)
    ref_tokens = _soft_tokens(reference)
    common = sum((Counter(pred_tokens) & Counter(ref_tokens)).values())
    if not pred_tokens or not ref_tokens or common == 0:
        return 0.0
    precision = common / len(pred_tokens)
    recall = common / len(ref_tokens)
    return 2 * precision * recall / (precision + recall)


def exact_match(predicted: str, reference: str) -> float:
    return float(_normalize(predicted) == _normalize(reference))


def _precision_recall(retrieved: set[str], relevant: set[str]) -> tuple[float, float]:
    precision = len(retrieved & relevant) / len(retrieved) if retrieved else 0.0
    recall = len(retrieved & relevant) / len(relevant) if relevant else 1.0
    return precision, recall


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"(?<!\w)\d+(?:\.\d+)?(?:%|％|万|亿)?", text))


def _has_causal_language(text: str) -> bool:
    return bool(
        re.search(
            r"导致|引起|造成|完全由|\b(?:causes?|caused|results? in|leads? to)\b",
            text,
            flags=re.I,
        )
    )


def _overclaim_reduction(sample: dict[str, Any], answer: str) -> float | None:
    category = sample["category"]
    reference = sample["expected_revision"]["revised_answer"]
    initial = sample["initial_answer"]
    if category == "causal_overclaim":
        initial_overclaim = _has_causal_language(initial) and not _has_causal_language(reference)
        final_overclaim = _has_causal_language(answer) and not _has_causal_language(reference)
    elif category == "numerical_conflict":
        reference_numbers = _numbers(reference)
        initial_overclaim = bool(_numbers(initial) - reference_numbers)
        final_overclaim = bool(_numbers(answer) - reference_numbers)
    else:
        return None
    if not initial_overclaim:
        return None
    return float(not final_overclaim)


def score_sample(sample: dict[str, Any], prediction: PredictionRecord) -> dict[str, Any]:
    if sample["id"] != prediction.sample_id:
        raise ValueError("sample and prediction IDs do not match")
    reference = str(sample["expected_revision"]["revised_answer"])
    relevant_docs = {
        str(item["doc_id"]) for item in (*sample["gold_evidence"], *sample["counter_evidence"])
    }
    counter_docs = {str(item["doc_id"]) for item in sample["counter_evidence"]}
    retrieved = set(prediction.evidence_ids)
    evidence_precision, evidence_recall = _precision_recall(retrieved, relevant_docs)
    _, counter_recall = _precision_recall(retrieved, counter_docs)
    gold_conflict = str(sample["conflict_type"])
    gold_conflict_present = gold_conflict != "no_conflict"
    predicted_conflicts = set(prediction.predicted_conflict_types)
    conflict_presence_correct = bool(predicted_conflicts) == gold_conflict_present
    typed_conflict_correct = (
        gold_conflict in predicted_conflicts if gold_conflict_present else not predicted_conflicts
    )
    answer_score = soft_f1(prediction.answer, reference)
    action_correct = prediction.revision_action == sample["expected_revision"]["action"]
    return {
        "sample_id": sample["id"],
        "method": prediction.method,
        "category": sample["category"],
        "split": sample["split"],
        "dependency_group": sample["source_metadata"].get("dependency_group"),
        "answer_correctness": answer_score,
        "answer_exact_match": exact_match(prediction.answer, reference),
        "unsupported_claim_rate": float(not bool(retrieved & relevant_docs)),
        "evidence_precision": evidence_precision,
        "evidence_recall": evidence_recall,
        "counter_evidence_recall": counter_recall,
        "conflict_detected": float(conflict_presence_correct),
        "typed_conflict_correct": float(typed_conflict_correct),
        "gold_conflict_present": gold_conflict_present,
        "predicted_conflict_count": len(predicted_conflicts),
        "revision_action_correct": float(action_correct),
        "revision_accuracy": float(action_correct and answer_score >= 0.8),
        "overclaim_reduction": _overclaim_reduction(sample, prediction.answer),
    }


def aggregate_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot aggregate an empty score set")
    metric_names = (
        "answer_correctness",
        "answer_exact_match",
        "unsupported_claim_rate",
        "evidence_precision",
        "evidence_recall",
        "counter_evidence_recall",
        "conflict_detected",
        "typed_conflict_correct",
        "revision_action_correct",
        "revision_accuracy",
        "overclaim_reduction",
    )

    def means(items: list[dict[str, Any]]) -> dict[str, float]:
        result: dict[str, float] = {}
        for name in metric_names:
            values = [float(row[name]) for row in items if row.get(name) is not None]
            result[name] = sum(values) / len(values) if values else 0.0
        return result

    true_positives = sum(
        int(row["typed_conflict_correct"])
        for row in rows
        if bool(row.get("gold_conflict_present", True))
    )
    predicted = sum(int(row["predicted_conflict_count"]) for row in rows)
    gold = sum(bool(row.get("gold_conflict_present", True)) for row in rows)
    precision = true_positives / predicted if predicted else 0.0
    recall = true_positives / gold if gold else 0.0
    typed_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[str(row["category"])].append(row)
    return {
        "samples": len(rows),
        "metrics": {**means(rows), "typed_conflict_f1": typed_f1},
        "typed_conflict_counts": {
            "true_positives": true_positives,
            "predicted": predicted,
            "gold": gold,
        },
        "by_category": {category: means(items) for category, items in sorted(by_category.items())},
    }
