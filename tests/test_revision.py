from __future__ import annotations

from far.claims import ClaimNode, ClaimType
from far.evidence_types import EvidenceType, TypedConflict
from far.revision import RevisionAction, TypedRevisionEngine


def test_causal_conflict_downgrades_to_association() -> None:
    claim = ClaimNode("C1", "Exercise causes lower blood pressure", ClaimType.CAUSAL)
    conflict = TypedConflict(
        claim_id="C1",
        evidence_id="E1",
        conflict_type=EvidenceType.CAUSAL,
        confidence=0.9,
        rationale="Observational evidence does not establish causality.",
    )
    trace = TypedRevisionEngine().revise(claim, (conflict,), ())
    assert trace.action is RevisionAction.DOWNGRADE_CAUSAL
    assert "associated with" in trace.after
    assert trace.changed


def test_suggested_revision_is_preserved_exactly() -> None:
    claim = ClaimNode("C1", "Revenue was 20 million", ClaimType.NUMERICAL)
    conflict = TypedConflict(
        claim_id="C1",
        evidence_id="E1",
        conflict_type=EvidenceType.NUMERICAL,
        confidence=1.0,
        rationale="Audited report differs.",
        suggested_revision="Revenue was 18 million.",
    )
    trace = TypedRevisionEngine().revise(claim, (conflict,), ())
    assert trace.after == "Revenue was 18 million."
