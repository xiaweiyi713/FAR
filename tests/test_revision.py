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


def test_sentence_final_chinese_causal_marker_is_removed() -> None:
    claim = ClaimNode("C1", "这一结果完全由该因素导致", ClaimType.CAUSAL)
    conflict = TypedConflict(
        claim_id="C1",
        evidence_id="E1",
        conflict_type=EvidenceType.CAUSAL,
        confidence=0.9,
        rationale="Only association is supported.",
    )
    trace = TypedRevisionEngine().revise(claim, (conflict,), ())
    assert "导致" not in trace.after
    assert "相关" in trace.after


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


def test_source_reliability_controls_when_a_low_source_also_has_numeric_conflict() -> None:
    claim = ClaimNode(
        "C1",
        "Revenue was 20 million",
        ClaimType.NUMERICAL,
        source_reliability="low",
    )
    conflicts = (
        TypedConflict(
            claim_id="C1",
            evidence_id="E1",
            conflict_type=EvidenceType.NUMERICAL,
            confidence=0.9,
            rationale="Values differ.",
        ),
        TypedConflict(
            claim_id="C1",
            evidence_id="E1",
            conflict_type=EvidenceType.SOURCE_RELIABILITY,
            confidence=0.8,
            rationale="Official source supersedes an unverified summary.",
        ),
    )
    trace = TypedRevisionEngine().revise(claim, conflicts, ())
    assert trace.action is RevisionAction.PREFER_RELIABLE_SOURCE
