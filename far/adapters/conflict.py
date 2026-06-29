"""Conflict detection adapters: transparent offline rules and VeraRAG reuse."""

from __future__ import annotations

import re
from typing import Any, ClassVar, Protocol

from ..claims import ClaimNode, ClaimType
from ..evidence_types import EvidenceType, TypedConflict
from ..models import EvidenceDocument


class ConflictDetector(Protocol):
    def detect(
        self,
        claim: ClaimNode,
        evidence: EvidenceDocument,
    ) -> tuple[TypedConflict, ...]: ...


class HeuristicConflictDetector:
    """High-precision rules suitable for offline runs; no hidden model calls."""

    _NUMBER = re.compile(
        r"(?<![A-Za-z0-9_.,])[+-]?\d+(?:[.,]\d+)*(?:%|％|万|亿|million|billion)?",
        re.I,
    )
    _TIME = re.compile(r"(?:19|20)\d{2}(?:[-年/]\d{1,2})?(?:[-月/]\d{1,2})?日?", re.I)
    _CAUSAL_DENIAL = re.compile(
        r"仅.{0,5}相关|只是相关|不能证明因果|并非因果|第三.{0,3}因素|"
        r"correlation (?:only|not causation)|does not (?:establish|prove) caus|confound(?:er|ing)",
        re.I,
    )
    _REFUTE = re.compile(
        r"\b(?:false|incorrect|wrong|refut(?:e|es|ed)|contrary|not true)\b|"
        r"错误|不正确|并非如此|事实并非|反例|予以否认",
        re.I,
    )
    _DEFINITION = re.compile(
        r"定义不同|口径不同|does not mean|alternative definition|operational definition", re.I
    )
    _ENTITY = re.compile(
        r"主体不同|并非同一|母公司|子公司|namesake|different entit|subsidiary|parent company", re.I
    )

    def __init__(self, *, allow_oracle_metadata: bool = False) -> None:
        self.allow_oracle_metadata = allow_oracle_metadata

    def detect(
        self,
        claim: ClaimNode,
        evidence: EvidenceDocument,
    ) -> tuple[TypedConflict, ...]:
        if self.allow_oracle_metadata:
            seeded = self._from_metadata(claim, evidence)
            if seeded is not None:
                return (seeded,)

        text = evidence.text
        conflict_type: EvidenceType | None = None
        rationale = ""
        confidence = 0.0

        if claim.claim_type is ClaimType.CAUSAL and self._CAUSAL_DENIAL.search(text):
            conflict_type = EvidenceType.CAUSAL
            rationale = (
                "Evidence explicitly limits the claim to association or identifies confounding."
            )
            confidence = 0.92
        elif self._ENTITY.search(text):
            conflict_type = EvidenceType.ENTITY
            rationale = "Evidence distinguishes the named entity or organizational scope."
            confidence = 0.86
        elif self._DEFINITION.search(text):
            conflict_type = EvidenceType.DEFINITION
            rationale = "Evidence uses or identifies a materially different definition."
            confidence = 0.85
        elif self._numeric_conflict(claim, text):
            conflict_type = EvidenceType.NUMERICAL
            rationale = "Evidence reports a different value for the claim's measurement."
            confidence = 0.82
        elif self._temporal_conflict(claim, text):
            conflict_type = EvidenceType.TEMPORAL
            rationale = "Evidence reports a different date or temporal version."
            confidence = 0.82
        elif self._REFUTE.search(text):
            conflict_type = EvidenceType.COUNTER_EVIDENCE
            rationale = "Evidence explicitly rejects or supplies a counterexample to the claim."
            confidence = 0.88

        if conflict_type is None:
            return ()
        return (
            TypedConflict(
                claim_id=claim.claim_id,
                evidence_id=evidence.evidence_id,
                conflict_type=conflict_type,
                confidence=confidence,
                rationale=rationale,
                strength="strong" if confidence >= 0.85 else "weak",
            ),
        )

    def _from_metadata(
        self,
        claim: ClaimNode,
        evidence: EvidenceDocument,
    ) -> TypedConflict | None:
        raw_type = evidence.metadata.get("conflict_type")
        refutes = evidence.metadata.get("refutes_claim")
        if raw_type is None and refutes not in {claim.claim_id, claim.text, True}:
            return None
        aliases = {
            "temporal_conflict": EvidenceType.TEMPORAL,
            "temporal": EvidenceType.TEMPORAL,
            "entity_mismatch": EvidenceType.ENTITY,
            "entity": EvidenceType.ENTITY,
            "numeric_conflict": EvidenceType.NUMERICAL,
            "numerical": EvidenceType.NUMERICAL,
            "causal_conflict": EvidenceType.CAUSAL,
            "causal": EvidenceType.CAUSAL,
            "source_disagreement": EvidenceType.SOURCE_RELIABILITY,
            "source_reliability": EvidenceType.SOURCE_RELIABILITY,
            "definitional_conflict": EvidenceType.DEFINITION,
            "definition": EvidenceType.DEFINITION,
            "refute": EvidenceType.COUNTER_EVIDENCE,
            "counter_evidence": EvidenceType.COUNTER_EVIDENCE,
        }
        conflict_type = aliases.get(str(raw_type), EvidenceType.COUNTER_EVIDENCE)
        return TypedConflict(
            claim_id=claim.claim_id,
            evidence_id=evidence.evidence_id,
            conflict_type=conflict_type,
            confidence=float(evidence.metadata.get("conflict_confidence", 1.0)),
            rationale=str(
                evidence.metadata.get("conflict_rationale", "Gold/demo conflict metadata.")
            ),
            strength=str(evidence.metadata.get("strength", "strong")),
            suggested_revision=(
                str(evidence.metadata["suggested_revision"])
                if evidence.metadata.get("suggested_revision")
                else None
            ),
            metadata={"oracle_metadata": True},
        )

    def _numeric_conflict(self, claim: ClaimNode, text: str) -> bool:
        if not claim.numbers:
            return False
        evidence_numbers = set(self._NUMBER.findall(text))
        claim_numbers = set(claim.numbers)
        return bool(evidence_numbers and claim_numbers.isdisjoint(evidence_numbers))

    def _temporal_conflict(self, claim: ClaimNode, text: str) -> bool:
        if not claim.time_expressions:
            return False
        evidence_times = set(self._TIME.findall(text))
        claim_times = set(claim.time_expressions)
        return bool(evidence_times and claim_times.isdisjoint(evidence_times))


class VeraConflictDetector:
    """Reuse VeraRAG's layered conflict graph while returning FAR control signals."""

    _TYPE_MAP: ClassVar[dict[str, EvidenceType]] = {
        "refute": EvidenceType.COUNTER_EVIDENCE,
        "numeric_conflict": EvidenceType.NUMERICAL,
        "temporal_conflict": EvidenceType.TEMPORAL,
        "entity_mismatch": EvidenceType.ENTITY,
        "source_disagreement": EvidenceType.SOURCE_RELIABILITY,
        "definitional_conflict": EvidenceType.DEFINITION,
        "scope_conflict": EvidenceType.DEFINITION,
        "causal_conflict": EvidenceType.CAUSAL,
        "granularity_conflict": EvidenceType.DEFINITION,
    }

    def __init__(self, config: dict[str, Any] | None = None, builder: Any | None = None) -> None:
        if builder is None:
            try:
                from src.evidence.conflict_graph import ConflictGraphBuilder
            except ImportError as exc:
                raise RuntimeError("VeraRAG is required for VeraConflictDetector") from exc
            safe_config = dict(config or {})
            conflict_config = dict(safe_config.get("conflict_graph", {}))
            conflict_config.setdefault("enable_nli", False)
            safe_config["conflict_graph"] = conflict_config
            builder = ConflictGraphBuilder(safe_config)
        self.builder = builder

    def detect(
        self,
        claim: ClaimNode,
        evidence: EvidenceDocument,
    ) -> tuple[TypedConflict, ...]:
        try:
            from src.utils.data_structures import Claim, Evidence
            from src.utils.data_structures import ClaimType as VeraClaimType
        except ImportError as exc:
            raise RuntimeError("VeraRAG data structures are unavailable") from exc
        type_map = {
            ClaimType.FACTUAL: VeraClaimType.FACTUAL,
            ClaimType.NUMERICAL: VeraClaimType.NUMERICAL,
            ClaimType.TEMPORAL: VeraClaimType.TEMPORAL,
            ClaimType.CAUSAL: VeraClaimType.CAUSAL,
            ClaimType.COMPARATIVE: VeraClaimType.COMPARATIVE,
            ClaimType.DEFINITIONAL: VeraClaimType.DEFINITIONAL,
            ClaimType.INFERENTIAL: VeraClaimType.UNCERTAINTY,
        }
        source_claim_id = f"far:{claim.claim_id}"
        evidence_claim_id = f"far-evidence:{evidence.evidence_id}"
        claim_evidence = Evidence(
            evidence_id=f"claim:{claim.claim_id}",
            source="far_initial_answer",
            title="Initial answer claim",
            text_span=claim.text,
            claims=[
                Claim(
                    claim_id=source_claim_id,
                    claim=claim.text,
                    claim_type=type_map[claim.claim_type],
                    entities=list(claim.entities),
                    numbers=list(claim.numbers),
                    time_expressions=list(claim.time_expressions),
                )
            ],
        )
        retrieved_evidence = Evidence(
            evidence_id=evidence.evidence_id,
            source=evidence.source,
            title=evidence.title,
            text_span=evidence.text,
            date=evidence.date,
            url=evidence.url,
            claims=[
                Claim(
                    claim_id=evidence_claim_id,
                    claim=evidence.text,
                    claim_type=type_map[claim.claim_type],
                )
            ],
        )
        graph = self.builder.build_graph([claim_evidence, retrieved_evidence], use_llm=False)
        conflicts: list[TypedConflict] = []
        for edge in graph.get_conflicts():
            if {edge.source_id, edge.target_id} != {source_claim_id, evidence_claim_id}:
                continue
            conflict_type = self._TYPE_MAP.get(edge.conflict_type.value)
            if conflict_type is None:
                continue
            conflicts.append(
                TypedConflict(
                    claim_id=claim.claim_id,
                    evidence_id=evidence.evidence_id,
                    conflict_type=conflict_type,
                    confidence=float(edge.confidence),
                    rationale=edge.rationale or edge.resolver_strategy or "VeraRAG detector",
                    strength="strong" if edge.confidence >= 0.75 else "weak",
                    metadata={"resolver_strategy": edge.resolver_strategy},
                )
            )
        return tuple(conflicts)
