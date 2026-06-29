"""Step 4: conflict-type-specific answer revision with an auditable trace."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

from .claims import ClaimNode
from .evidence_types import EvidenceType, TypedConflict
from .models import EvidenceDocument
from .protocols import TextGenerator


class RevisionAction(str, Enum):
    KEEP = "keep"
    CORRECT_TEMPORAL = "correct_temporal"
    REQUALIFY_ENTITY = "requalify_entity"
    REPLACE_NUMERICAL = "replace_numerical"
    DOWNGRADE_CAUSAL = "downgrade_causal_to_correlation"
    PREFER_RELIABLE_SOURCE = "prefer_reliable_source"
    CLARIFY_DEFINITION = "clarify_definition"
    RETRACT = "retract"
    QUALIFY_UNCERTAINTY = "qualify_uncertainty"


@dataclass(frozen=True)
class RevisionTrace:
    claim_id: str
    before: str
    after: str
    action: RevisionAction
    conflict_types: tuple[EvidenceType, ...]
    evidence_ids: tuple[str, ...]
    rationale: str
    confidence: float

    @property
    def changed(self) -> bool:
        return self.before != self.after

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "before": self.before,
            "after": self.after,
            "action": self.action.value,
            "conflict_types": [item.value for item in self.conflict_types],
            "evidence_ids": list(self.evidence_ids),
            "rationale": self.rationale,
            "confidence": self.confidence,
            "changed": self.changed,
        }


class TypedRevisionEngine:
    """Apply deterministic typed policies; optional LLM rewriting belongs above this layer."""

    _PRIORITY: ClassVar[dict[EvidenceType, int]] = {
        EvidenceType.COUNTER_EVIDENCE: 100,
        EvidenceType.SOURCE_RELIABILITY: 95,
        EvidenceType.ENTITY: 90,
        EvidenceType.NUMERICAL: 80,
        EvidenceType.TEMPORAL: 70,
        EvidenceType.CAUSAL: 60,
        EvidenceType.DEFINITION: 50,
    }

    def revise(
        self,
        claim: ClaimNode,
        conflicts: tuple[TypedConflict, ...],
        evidence: tuple[EvidenceDocument, ...],
    ) -> RevisionTrace:
        if not conflicts:
            rationale = (
                "No typed conflict was detected; the claim is retained, but failure to retrieve "
                "counter-evidence is not treated as proof."
            )
            return RevisionTrace(
                claim_id=claim.claim_id,
                before=claim.text,
                after=claim.text,
                action=RevisionAction.KEEP,
                conflict_types=(),
                evidence_ids=tuple(item.evidence_id for item in evidence),
                rationale=rationale,
                confidence=0.75 if evidence else 0.4,
            )

        ordered = sorted(
            conflicts,
            key=lambda item: (self._PRIORITY[item.conflict_type], item.confidence),
            reverse=True,
        )
        controlling = ordered[0]
        action = self._action(controlling)
        after = self._rewrite(claim.text, controlling, action)
        return RevisionTrace(
            claim_id=claim.claim_id,
            before=claim.text,
            after=after,
            action=action,
            conflict_types=tuple(dict.fromkeys(item.conflict_type for item in ordered)),
            evidence_ids=tuple(dict.fromkeys(item.evidence_id for item in ordered)),
            rationale="; ".join(dict.fromkeys(item.rationale for item in ordered)),
            confidence=max(item.confidence for item in ordered),
        )

    @staticmethod
    def _action(conflict: TypedConflict) -> RevisionAction:
        if conflict.conflict_type is EvidenceType.COUNTER_EVIDENCE:
            return (
                RevisionAction.RETRACT
                if conflict.strength == "strong"
                else RevisionAction.QUALIFY_UNCERTAINTY
            )
        return {
            EvidenceType.TEMPORAL: RevisionAction.CORRECT_TEMPORAL,
            EvidenceType.ENTITY: RevisionAction.REQUALIFY_ENTITY,
            EvidenceType.NUMERICAL: RevisionAction.REPLACE_NUMERICAL,
            EvidenceType.CAUSAL: RevisionAction.DOWNGRADE_CAUSAL,
            EvidenceType.SOURCE_RELIABILITY: RevisionAction.PREFER_RELIABLE_SOURCE,
            EvidenceType.DEFINITION: RevisionAction.CLARIFY_DEFINITION,
        }[conflict.conflict_type]

    def _rewrite(
        self,
        text: str,
        conflict: TypedConflict,
        action: RevisionAction,
    ) -> str:
        if conflict.suggested_revision:
            return conflict.suggested_revision.strip()
        if action is RevisionAction.DOWNGRADE_CAUSAL:
            return self._downgrade_causal(text)
        if action is RevisionAction.RETRACT:
            return f"The available counter-evidence refutes this claim: {text}"
        if action is RevisionAction.QUALIFY_UNCERTAINTY:
            return f"Evidence is mixed, so this claim remains uncertain: {text}"
        qualifiers = {
            RevisionAction.CORRECT_TEMPORAL: (
                "The reported timeline is disputed and requires date-specific correction"
            ),
            RevisionAction.REQUALIFY_ENTITY: "The entity scope is ambiguous and must be narrowed",
            RevisionAction.REPLACE_NUMERICAL: (
                "The reported value conflicts with retrieved measurements"
            ),
            RevisionAction.PREFER_RELIABLE_SOURCE: (
                "Lower-reliability sources disagree with authoritative evidence"
            ),
            RevisionAction.CLARIFY_DEFINITION: (
                "This statement depends on the operational definition used"
            ),
        }
        return f"{qualifiers[action]}: {text}"

    @staticmethod
    def _downgrade_causal(text: str) -> str:
        caused_by = re.match(r"^(.+?)(?:完全)?由(.+?)(?:导致|造成|引起)$", text)
        if caused_by:
            return f"{caused_by.group(1)}与{caused_by.group(2)}相关，但现有证据不足以确认因果关系"
        chinese = re.match(r"^(.+?)(?:导致|造成|引起)(.*)$", text)
        if chinese:
            target = chinese.group(2).strip()
            if target:
                return f"{chinese.group(1)}与{target}相关，但现有证据不足以确认因果关系"
            return f"{chinese.group(1)}存在相关性，但现有证据不足以确认因果关系"
        rewritten = re.sub(
            r"\b(?:causes?|caused|results? in|led to|leads to)\b",
            "is associated with",
            text,
            flags=re.I,
        )
        if rewritten != text:
            return f"{rewritten}; the retrieved evidence does not establish causality"
        return f"An association is reported, but causality is not established: {text}"


class LLMTypedRevisionEngine(TypedRevisionEngine):
    """Use the model only to realize a typed policy selected by deterministic control."""

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
            f"Original claim: {claim.text}\nRequired revision action: {policy_trace.action.value}\n"
            f"Typed conflicts: {', '.join(item.value for item in policy_trace.conflict_types)}\n"
            f"Evidence:\n{context}\nRewrite only the claim. Preserve supported content, apply the "
            "required action, and do not add facts absent from evidence."
        )
        try:
            revised = self.generator.complete(
                prompt,
                system_prompt="Perform the specified evidence-grounded typed revision.",
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
            conflict_types=policy_trace.conflict_types,
            evidence_ids=policy_trace.evidence_ids,
            rationale=f"{policy_trace.rationale}; typed policy realized by the configured LLM",
            confidence=policy_trace.confidence,
        )
