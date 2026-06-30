"""Four-stage FAR orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapters.conflict import ConflictDetector, HeuristicConflictDetector
from .adapters.retrieval import Retriever
from .claims import ClaimDecomposer, ClaimGraph, RuleBasedClaimDecomposer
from .counterfactual import CounterfactualQuery, TypedQueryGenerator
from .evidence_types import (
    EvidenceRequirement,
    EvidenceRequirementAssigner,
    TypedConflict,
)
from .models import EvidenceDocument
from .revision import RevisionTrace, TypedRevisionEngine


@dataclass(frozen=True)
class QueryRetrieval:
    query: CounterfactualQuery
    evidence_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"query": self.query.to_dict(), "evidence_ids": list(self.evidence_ids)}


@dataclass(frozen=True)
class FARResult:
    question: str
    initial_answer: str
    revised_answer: str
    claim_graph: ClaimGraph
    requirements: dict[str, tuple[EvidenceRequirement, ...]]
    evidence_map: dict[str, tuple[EvidenceDocument, ...]]
    conflicts: dict[str, tuple[TypedConflict, ...]]
    revision_trace: tuple[RevisionTrace, ...]
    retrieval_trace: tuple[QueryRetrieval, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "initial_answer": self.initial_answer,
            "revised_answer": self.revised_answer,
            "claim_graph": self.claim_graph.to_dict(),
            "requirements": {
                claim_id: [item.to_dict() for item in items]
                for claim_id, items in self.requirements.items()
            },
            "evidence_map": {
                claim_id: [item.to_dict() for item in items]
                for claim_id, items in self.evidence_map.items()
            },
            "conflicts": {
                claim_id: [item.to_dict() for item in items]
                for claim_id, items in self.conflicts.items()
            },
            "revision_trace": [item.to_dict() for item in self.revision_trace],
            "retrieval_trace": [item.to_dict() for item in self.retrieval_trace],
        }


class FARPipeline:
    """Run claim graph → typed needs → falsifying retrieval → typed revision."""

    def __init__(
        self,
        retriever: Retriever,
        *,
        decomposer: ClaimDecomposer | None = None,
        requirement_assigner: EvidenceRequirementAssigner | None = None,
        query_generator: TypedQueryGenerator | None = None,
        conflict_detector: ConflictDetector | None = None,
        revision_engine: TypedRevisionEngine | None = None,
        top_k_per_query: int = 5,
    ) -> None:
        if top_k_per_query < 1:
            raise ValueError("top_k_per_query must be positive")
        self.retriever = retriever
        self.decomposer = decomposer or RuleBasedClaimDecomposer()
        self.requirement_assigner = requirement_assigner or EvidenceRequirementAssigner()
        self.query_generator = query_generator or TypedQueryGenerator()
        self.conflict_detector = conflict_detector or HeuristicConflictDetector()
        self.revision_engine = revision_engine or TypedRevisionEngine()
        self.top_k_per_query = top_k_per_query

    def run(self, question: str, initial_answer: str) -> FARResult:
        if not question.strip():
            raise ValueError("question must not be empty")
        graph = self.decomposer.decompose(initial_answer)
        requirements: dict[str, tuple[EvidenceRequirement, ...]] = {}
        evidence_map: dict[str, tuple[EvidenceDocument, ...]] = {}
        conflicts: dict[str, tuple[TypedConflict, ...]] = {}
        revision_trace: list[RevisionTrace] = []
        retrieval_trace: list[QueryRetrieval] = []

        for claim in graph.topological_order():
            if not claim.verifiable:
                requirements[claim.claim_id] = ()
                evidence_map[claim.claim_id] = ()
                conflicts[claim.claim_id] = ()
                revision_trace.append(self.revision_engine.revise(claim, (), ()))
                continue
            claim_requirements = self.requirement_assigner.assign(claim)
            requirements[claim.claim_id] = claim_requirements
            queries = self.query_generator.generate(claim, claim_requirements)
            by_id: dict[str, EvidenceDocument] = {}
            for query in queries:
                retrieved = self.retriever.retrieve(query.text, top_k=self.top_k_per_query)
                retrieval_trace.append(
                    QueryRetrieval(query, tuple(item.evidence_id for item in retrieved))
                )
                for item in retrieved:
                    previous = by_id.get(item.evidence_id)
                    if previous is None or item.score > previous.score:
                        by_id[item.evidence_id] = item
            evidence = tuple(
                sorted(by_id.values(), key=lambda item: (-item.score, item.evidence_id))
            )
            evidence_map[claim.claim_id] = evidence

            detected: list[TypedConflict] = []
            seen_conflicts: set[tuple[str, str]] = set()
            detect_many = getattr(self.conflict_detector, "detect_many", None)
            candidate_conflicts = (
                detect_many(claim, evidence, question=question)
                if callable(detect_many)
                else tuple(
                    conflict
                    for item in evidence
                    for conflict in self.conflict_detector.detect(
                        claim,
                        item,
                        question=question,
                    )
                )
            )
            for conflict in candidate_conflicts:
                key = (conflict.evidence_id, conflict.conflict_type.value)
                if key not in seen_conflicts:
                    seen_conflicts.add(key)
                    detected.append(conflict)
            claim_conflicts = tuple(
                sorted(detected, key=lambda item: (-item.confidence, item.evidence_id))
            )
            conflicts[claim.claim_id] = claim_conflicts
            revision_trace.append(self.revision_engine.revise(claim, claim_conflicts, evidence))

        revised_answer = "\n".join(item.after for item in revision_trace)
        return FARResult(
            question=question,
            initial_answer=initial_answer,
            revised_answer=revised_answer,
            claim_graph=graph,
            requirements=requirements,
            evidence_map=evidence_map,
            conflicts=conflicts,
            revision_trace=tuple(revision_trace),
            retrieval_trace=tuple(retrieval_trace),
        )
