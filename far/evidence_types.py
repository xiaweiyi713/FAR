"""Step 2: typed evidence requirements and conflict control signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from .claims import ClaimNode, ClaimType


class EvidenceType(str, Enum):
    TEMPORAL = "temporal"
    ENTITY = "entity"
    NUMERICAL = "numerical"
    CAUSAL = "causal"
    SOURCE_RELIABILITY = "source_reliability"
    DEFINITION = "definition"
    COUNTER_EVIDENCE = "counter_evidence"


@dataclass(frozen=True)
class EvidenceRequirement:
    claim_id: str
    evidence_type: EvidenceType
    rationale: str
    priority: int = 1
    constraints: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.priority < 1:
            raise ValueError("requirement priority must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "evidence_type": self.evidence_type.value,
            "rationale": self.rationale,
            "priority": self.priority,
            "constraints": dict(self.constraints),
        }


@dataclass(frozen=True)
class TypedConflict:
    """A typed control signal connecting one claim to conflicting evidence."""

    claim_id: str
    evidence_id: str
    conflict_type: EvidenceType
    confidence: float
    rationale: str
    strength: str = "strong"
    suggested_revision: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("conflict confidence must be in [0, 1]")
        if self.strength not in {"weak", "strong"}:
            raise ValueError("conflict strength must be weak or strong")

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "evidence_id": self.evidence_id,
            "conflict_type": self.conflict_type.value,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "strength": self.strength,
            "suggested_revision": self.suggested_revision,
            "metadata": dict(self.metadata),
        }


class EvidenceRequirementAssigner:
    """Assign positive evidence needs before retrieval, rather than post-hoc labels."""

    _PRIMARY: ClassVar[dict[ClaimType, EvidenceType]] = {
        ClaimType.TEMPORAL: EvidenceType.TEMPORAL,
        ClaimType.NUMERICAL: EvidenceType.NUMERICAL,
        ClaimType.CAUSAL: EvidenceType.CAUSAL,
        ClaimType.DEFINITIONAL: EvidenceType.DEFINITION,
        ClaimType.COMPARATIVE: EvidenceType.NUMERICAL,
        ClaimType.FACTUAL: EvidenceType.ENTITY,
        ClaimType.INFERENTIAL: EvidenceType.COUNTER_EVIDENCE,
    }

    def assign(self, claim: ClaimNode) -> tuple[EvidenceRequirement, ...]:
        primary = self._PRIMARY[claim.claim_type]
        requirements = [
            EvidenceRequirement(
                claim_id=claim.claim_id,
                evidence_type=primary,
                rationale=f"{claim.claim_type.value} claim requires {primary.value} verification",
                priority=3,
                constraints=self._constraints(claim, primary),
            ),
            EvidenceRequirement(
                claim_id=claim.claim_id,
                evidence_type=EvidenceType.SOURCE_RELIABILITY,
                rationale="prefer attributable and authoritative evidence",
                priority=2,
            ),
            EvidenceRequirement(
                claim_id=claim.claim_id,
                evidence_type=EvidenceType.COUNTER_EVIDENCE,
                rationale="actively test the claim against falsifying evidence",
                priority=3,
            ),
        ]
        deduplicated = {requirement.evidence_type: requirement for requirement in requirements}
        return tuple(deduplicated.values())

    @staticmethod
    def _constraints(claim: ClaimNode, evidence_type: EvidenceType) -> dict[str, Any]:
        if evidence_type is EvidenceType.TEMPORAL:
            return {"time_expressions": list(claim.time_expressions)}
        if evidence_type is EvidenceType.NUMERICAL:
            return {"numbers": list(claim.numbers)}
        if evidence_type is EvidenceType.ENTITY:
            return {"entities": list(claim.entities)}
        return {}
