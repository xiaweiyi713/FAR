"""Named FAR ablations used to test each claimed method component."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from far.adapters.conflict import ConflictDetector, HeuristicConflictDetector
from far.adapters.retrieval import Retriever
from far.claims import ClaimNode, LLMClaimDecomposer
from far.counterfactual import LLMTypedQueryGenerator, TypedQueryGenerator
from far.evidence_types import EvidenceType, TypedConflict
from far.models import EvidenceDocument
from far.pipeline import FARPipeline
from far.protocols import TextGenerator
from far.revision import (
    LLMTypedRevisionEngine,
    RevisionAction,
    RevisionTrace,
    TypedRevisionEngine,
)

ABLATION_NAMES = (
    "full",
    "minus_typed_conflict",
    "minus_refutation_query",
    "minus_boundary_query",
    "minus_typed_revision",
)


class UntypedConflictDetector:
    def __init__(self, detector: ConflictDetector) -> None:
        self.detector = detector

    def detect(
        self,
        claim: ClaimNode,
        evidence: EvidenceDocument,
        *,
        question: str = "",
    ) -> tuple[TypedConflict, ...]:
        return self._as_untyped(self.detector.detect(claim, evidence, question=question))

    def detect_many(
        self,
        claim: ClaimNode,
        evidence: tuple[EvidenceDocument, ...],
        *,
        question: str = "",
    ) -> tuple[TypedConflict, ...]:
        detect_many = getattr(self.detector, "detect_many", None)
        conflicts = (
            detect_many(claim, evidence, question=question)
            if callable(detect_many)
            else tuple(
                conflict
                for document in evidence
                for conflict in self.detector.detect(
                    claim,
                    document,
                    question=question,
                )
            )
        )
        return self._as_untyped(conflicts)

    @staticmethod
    def _as_untyped(
        conflicts: tuple[TypedConflict, ...],
    ) -> tuple[TypedConflict, ...]:
        return tuple(
            replace(
                conflict,
                conflict_type=EvidenceType.COUNTER_EVIDENCE,
                rationale=f"Untyped contradiction: {conflict.rationale}",
                suggested_revision=None,
            )
            for conflict in conflicts
        )


class GenericRevisionEngine(TypedRevisionEngine):
    """Remove typed actions while retaining a trace for evaluation accountability."""

    def revise(
        self,
        claim: ClaimNode,
        conflicts: tuple[TypedConflict, ...],
        evidence: tuple[EvidenceDocument, ...],
    ) -> RevisionTrace:
        if not conflicts:
            return super().revise(claim, conflicts, evidence)
        confidence = max(conflict.confidence for conflict in conflicts)
        return RevisionTrace(
            claim_id=claim.claim_id,
            before=claim.text,
            after=(
                "Retrieved evidence conflicts with this claim, so it remains uncertain: "
                f"{claim.text}"
            ),
            action=RevisionAction.QUALIFY_UNCERTAINTY,
            conflict_types=tuple(dict.fromkeys(conflict.conflict_type for conflict in conflicts)),
            evidence_ids=tuple(dict.fromkeys(conflict.evidence_id for conflict in conflicts)),
            rationale="Generic repair without a conflict-type-specific action.",
            confidence=confidence,
        )


def build_ablation(
    name: str,
    retriever: Retriever,
    *,
    conflict_detector: ConflictDetector | None = None,
    text_generator: TextGenerator | None = None,
    top_k_per_query: int = 5,
    pipeline_options: dict[str, Any] | None = None,
) -> FARPipeline:
    if name not in ABLATION_NAMES:
        raise ValueError(f"unknown ablation {name!r}; expected one of {ABLATION_NAMES}")
    detector = conflict_detector or HeuristicConflictDetector()
    query_generator: TypedQueryGenerator = (
        LLMTypedQueryGenerator(text_generator) if text_generator else TypedQueryGenerator()
    )
    revision_engine: TypedRevisionEngine = (
        LLMTypedRevisionEngine(text_generator) if text_generator else TypedRevisionEngine()
    )
    if name == "minus_typed_conflict":
        detector = UntypedConflictDetector(detector)
        query_generator = (
            LLMTypedQueryGenerator(text_generator, typed=False)
            if text_generator
            else TypedQueryGenerator(typed=False)
        )
    elif name == "minus_refutation_query":
        query_generator = (
            LLMTypedQueryGenerator(text_generator, include_refutation=False)
            if text_generator
            else TypedQueryGenerator(include_refutation=False)
        )
    elif name == "minus_boundary_query":
        query_generator = (
            LLMTypedQueryGenerator(text_generator, include_boundary=False)
            if text_generator
            else TypedQueryGenerator(include_boundary=False)
        )
    elif name == "minus_typed_revision":
        revision_engine = GenericRevisionEngine()
    return FARPipeline(
        retriever,
        decomposer=LLMClaimDecomposer(text_generator) if text_generator else None,
        query_generator=query_generator,
        conflict_detector=detector,
        revision_engine=revision_engine,
        top_k_per_query=top_k_per_query,
        **(pipeline_options or {}),
    )
