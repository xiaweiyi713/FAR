"""Named FAR ablations used to test each claimed method component."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from far.adapters.conflict import (
    ConflictDetector,
    HeuristicConflictDetector,
    NLIOnlyConflictDetector,
)
from far.adapters.retrieval import Retriever
from far.claims import (
    ClaimDecomposer,
    ClaimGraph,
    ClaimNode,
    LLMClaimDecomposer,
    RuleBasedClaimDecomposer,
)
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
    "minus_typed_revision_aggressive",
    "minus_typed_detection_nli",
    "flat_claims",
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


class AggressiveGenericRevisionEngine(TypedRevisionEngine):
    """Apply strong type-blind repair without degrading every conflict to a caveat."""

    def revise(
        self,
        claim: ClaimNode,
        conflicts: tuple[TypedConflict, ...],
        evidence: tuple[EvidenceDocument, ...],
    ) -> RevisionTrace:
        if not conflicts:
            return super().revise(claim, conflicts, evidence)
        controlling = max(conflicts, key=lambda conflict: conflict.confidence)
        action = (
            RevisionAction.RETRACT
            if controlling.strength == "strong"
            else RevisionAction.QUALIFY_UNCERTAINTY
        )
        type_blind = replace(
            controlling,
            conflict_type=EvidenceType.COUNTER_EVIDENCE,
            suggested_revision=None,
        )
        return RevisionTrace(
            claim_id=claim.claim_id,
            before=claim.text,
            after=self._rewrite(claim.text, type_blind, action),
            action=action,
            conflict_types=(),
            evidence_ids=tuple(dict.fromkeys(conflict.evidence_id for conflict in conflicts)),
            rationale="Aggressive type-blind repair using conflict strength but not conflict type.",
            confidence=controlling.confidence,
        )


class LLMAggressiveGenericRevisionEngine(AggressiveGenericRevisionEngine):
    """Realize the type-blind aggressive policy with the same configured generator."""

    def __init__(self, generator: TextGenerator) -> None:
        self.generator = generator

    def revise(
        self,
        claim: ClaimNode,
        conflicts: tuple[TypedConflict, ...],
        evidence: tuple[EvidenceDocument, ...],
    ) -> RevisionTrace:
        policy_trace = super().revise(claim, conflicts, evidence)
        if not conflicts or policy_trace.action is RevisionAction.KEEP:
            return policy_trace
        context = "\n".join(
            f"[{item.evidence_id}] {item.title}: {item.text}" for item in evidence[:8]
        )
        prompt = (
            f"Original claim: {claim.text}\n"
            f"Required revision action: {policy_trace.action.value}\n"
            f"Evidence:\n{context}\n"
            "Rewrite only the claim. Preserve supported content, apply the required action "
            "aggressively, and do not add facts absent from evidence. No conflict-type label is "
            "available; infer only what the evidence itself supports."
        )
        try:
            revised = self.generator.complete(
                prompt,
                system_prompt="Perform an evidence-grounded type-blind revision.",
                temperature=0.0,
                max_tokens=500,
            ).strip()
        except (RuntimeError, ValueError):
            return policy_trace
        if not revised or revised == claim.text:
            return policy_trace
        return RevisionTrace(
            claim_id=policy_trace.claim_id,
            before=policy_trace.before,
            after=revised,
            action=policy_trace.action,
            conflict_types=(),
            evidence_ids=policy_trace.evidence_ids,
            rationale=f"{policy_trace.rationale}; type-blind policy realized by the configured LLM",
            confidence=policy_trace.confidence,
        )


class FlatClaimDecomposer:
    """Remove dependency edges while preserving claim texts, types, and order."""

    def __init__(self, inner: ClaimDecomposer) -> None:
        self.inner = inner

    def decompose(self, answer: str) -> ClaimGraph:
        graph = self.inner.decompose(answer)
        return ClaimGraph(tuple(replace(claim, depends_on=()) for claim in graph.claims))


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
    if name == "minus_typed_detection_nli":
        if not isinstance(conflict_detector, NLIOnlyConflictDetector):
            raise ValueError(
                "minus_typed_detection_nli requires an explicit "
                "NLIOnlyConflictDetector; layered or heuristic detectors are invalid"
            )
        detector: ConflictDetector = conflict_detector
    else:
        detector = conflict_detector or HeuristicConflictDetector()
    decomposer: ClaimDecomposer = (
        LLMClaimDecomposer(text_generator) if text_generator else RuleBasedClaimDecomposer()
    )
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
    elif name == "minus_typed_revision_aggressive":
        revision_engine = (
            LLMAggressiveGenericRevisionEngine(text_generator)
            if text_generator
            else AggressiveGenericRevisionEngine()
        )
    elif name == "flat_claims":
        decomposer = FlatClaimDecomposer(decomposer)
    return FARPipeline(
        retriever,
        decomposer=decomposer,
        query_generator=query_generator,
        conflict_detector=detector,
        revision_engine=revision_engine,
        top_k_per_query=top_k_per_query,
        **(pipeline_options or {}),
    )
