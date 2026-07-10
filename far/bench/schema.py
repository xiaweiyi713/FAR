"""Strict, serializable schema for FalsiRAG-Bench."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BenchmarkCategory(str, Enum):
    TEMPORAL_SHIFT = "temporal_shift"
    NUMERICAL_CONFLICT = "numerical_conflict"
    ENTITY_CONFUSION = "entity_confusion"
    CAUSAL_OVERCLAIM = "causal_overclaim"
    MULTI_SOURCE_CONFLICT = "multi_source_conflict"


class AnnotationStatus(str, Enum):
    MACHINE_SEEDED = "machine_seeded"
    DOUBLE_ANNOTATED = "double_annotated"
    ADJUDICATED = "adjudicated"


VALID_SPLITS = {"train", "dev", "test"}
BLIND_TEST_ALLOWED_FIELDS = {"id", "category", "split", "question", "initial_answer"}
VALID_CLAIM_TYPES = {
    "factual",
    "numerical",
    "temporal",
    "causal",
    "comparative",
    "definitional",
    "inferential",
}
VALID_CONFLICT_TYPES = {
    "temporal",
    "entity",
    "numerical",
    "causal",
    "source_reliability",
    "definition",
    "counter_evidence",
}
VALID_SAMPLE_CONFLICT_TYPES = VALID_CONFLICT_TYPES | {"no_conflict"}
VALID_REVISION_ACTIONS = {
    "correct_temporal",
    "replace_numerical",
    "requalify_entity",
    "downgrade_causal_to_correlation",
    "prefer_reliable_source",
    "clarify_definition",
    "retract",
    "qualify_uncertainty",
}


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class CorpusDocument:
    doc_id: str
    title: str
    content: str
    source: str
    date: str | None = None
    author: str | None = None
    url: str | None = None
    license: str = "MIT-controlled-summary"
    synthetic: bool = False
    source_doc_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> CorpusDocument:
        return cls(
            doc_id=_required_string(row.get("doc_id"), "doc_id"),
            title=_required_string(row.get("title"), "title"),
            content=_required_string(row.get("content"), "content"),
            source=_required_string(row.get("source"), "source"),
            date=row.get("date"),
            author=row.get("author"),
            url=row.get("url"),
            license=str(row.get("license", "MIT-controlled-summary")),
            synthetic=bool(row.get("synthetic", False)),
            source_doc_id=row.get("source_doc_id"),
            metadata=dict(row.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "date": self.date,
            "author": self.author,
            "url": self.url,
            "license": self.license,
            "synthetic": self.synthetic,
            "source_doc_id": self.source_doc_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class FalsiRAGSample:
    sample_id: str
    category: BenchmarkCategory
    split: str
    question: str
    initial_answer: str
    claims: tuple[dict[str, Any], ...]
    gold_evidence: tuple[dict[str, Any], ...]
    counter_evidence: tuple[dict[str, Any], ...]
    conflict_type: str
    expected_revision: dict[str, Any]
    annotation_status: AnnotationStatus
    source_metadata: dict[str, Any]

    def __post_init__(self) -> None:
        if self.split not in VALID_SPLITS:
            raise ValueError(f"unknown split: {self.split}")
        if self.conflict_type not in VALID_SAMPLE_CONFLICT_TYPES:
            raise ValueError(f"unknown conflict type: {self.conflict_type}")
        if not self.claims or not self.gold_evidence or not self.counter_evidence:
            raise ValueError("claims, gold_evidence, and counter_evidence must be non-empty")
        self._validate_claims()
        self._validate_evidence()
        action = self.expected_revision.get("action")
        if action not in VALID_REVISION_ACTIONS:
            raise ValueError(f"unknown revision action: {action}")
        _required_string(self.expected_revision.get("revised_answer"), "revised_answer")

    def _validate_claims(self) -> None:
        claim_ids = {_required_string(claim.get("claim_id"), "claim_id") for claim in self.claims}
        if len(claim_ids) != len(self.claims):
            raise ValueError("claim IDs must be unique")
        for claim in self.claims:
            _required_string(claim.get("claim"), "claim")
            if claim.get("type") not in VALID_CLAIM_TYPES:
                raise ValueError(f"invalid claim type: {claim.get('type')}")
            missing = set(claim.get("depends_on", [])) - claim_ids
            if missing:
                raise ValueError(f"claim has missing dependencies: {sorted(missing)}")

    def _validate_evidence(self) -> None:
        claim_ids = {claim["claim_id"] for claim in self.claims}
        evidence_ids: set[str] = set()
        for evidence in (*self.gold_evidence, *self.counter_evidence):
            evidence_id = _required_string(evidence.get("evidence_id"), "evidence_id")
            evidence_ids.add(evidence_id)
            _required_string(evidence.get("doc_id"), "doc_id")
            _required_string(evidence.get("text_span"), "text_span")
        for evidence in self.counter_evidence:
            if evidence.get("refutes_claim") not in claim_ids:
                raise ValueError("counter evidence must reference an existing claim")
            if evidence.get("conflict_type") not in VALID_CONFLICT_TYPES:
                raise ValueError("counter evidence has an invalid conflict type")
        if len(evidence_ids) != len(self.gold_evidence) + len(self.counter_evidence):
            raise ValueError("evidence IDs must be unique within a sample")

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> FalsiRAGSample:
        return cls(
            sample_id=_required_string(row.get("id"), "id"),
            category=BenchmarkCategory(row.get("category")),
            split=_required_string(row.get("split"), "split"),
            question=_required_string(row.get("question"), "question"),
            initial_answer=_required_string(row.get("initial_answer"), "initial_answer"),
            claims=tuple(row.get("claims", [])),
            gold_evidence=tuple(row.get("gold_evidence", [])),
            counter_evidence=tuple(row.get("counter_evidence", [])),
            conflict_type=_required_string(row.get("conflict_type"), "conflict_type"),
            expected_revision=dict(row.get("expected_revision", {})),
            annotation_status=AnnotationStatus(row.get("annotation_status")),
            source_metadata=dict(row.get("source_metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.sample_id,
            "category": self.category.value,
            "split": self.split,
            "question": self.question,
            "initial_answer": self.initial_answer,
            "claims": [dict(item) for item in self.claims],
            "gold_evidence": [dict(item) for item in self.gold_evidence],
            "counter_evidence": [dict(item) for item in self.counter_evidence],
            "conflict_type": self.conflict_type,
            "expected_revision": dict(self.expected_revision),
            "annotation_status": self.annotation_status.value,
            "source_metadata": dict(self.source_metadata),
        }
