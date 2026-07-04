from __future__ import annotations

import json
from pathlib import Path

from experiments.solo_paper_readiness import audit, audit_claim_scope, render_markdown

ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = ROOT / "reports/solo_paper_readiness.json"
REPORT_MD = ROOT / "reports/solo_paper_readiness.md"


def test_relaxed_paper_profile_is_ready_but_not_strict_aaai_ready() -> None:
    report = audit(ROOT)

    assert report["ready"] is True
    assert report["strict_aaai_submission_ready"] is False
    assert all(report["gates"].values())
    assert report["claim_scope"]["checks"]["typed_answer_advantage"] is True
    assert report["claim_scope"]["checks"]["refutation_ablation_not_positive"] is True
    assert report["claim_scope"]["checks"]["boundary_ablation_not_positive"] is True
    assert report["claim_scope"]["checks"]["typed_revision_answer_tradeoff"] is True
    assert (
        report["claim_scope"]["checks"][
            "typed_answer_advantage_same_direction_by_machine_disposition"
        ]
        is True
    )
    assert report["claim_scope"]["label_sensitivity"]["machine_confirmed"]["samples"] == 35
    assert report["claim_scope"]["label_sensitivity"]["machine_disputed"]["samples"] == 25


def test_relaxed_paper_profile_rejects_stale_broad_claims() -> None:
    paper = (ROOT / "paper/main.tex").read_text(encoding="utf-8")
    result = audit_claim_scope(ROOT, paper + "\nPENDING-EMPIRICAL-RUN\n")

    assert result["valid"] is False
    assert result["forbidden_stale_claims"] == ["PENDING-EMPIRICAL-RUN"]


def test_relaxed_paper_profile_requires_negative_ablation_disclosure() -> None:
    paper = (ROOT / "paper/main.tex").read_text(encoding="utf-8")
    paper = paper.replace(
        "Removing refutation queries does not reduce answer correctness",
        "The refutation ablation was performed",
    )
    result = audit_claim_scope(ROOT, paper)

    assert result["valid"] is False
    assert result["missing_required_disclosures"] == [
        "Removing refutation queries does not reduce answer correctness"
    ]


def test_relaxed_profile_never_claims_human_or_external_evidence() -> None:
    report = audit(ROOT)

    assert "human inter-annotator agreement" in report["forbidden_claims"]
    assert "externally held blind test" in report["forbidden_claims"]
    assert "multi-model or external-domain generality" in report["forbidden_claims"]


def test_tracked_relaxed_readiness_reports_are_current() -> None:
    report = audit(ROOT)

    assert json.loads(REPORT_JSON.read_text(encoding="utf-8")) == report
    assert REPORT_MD.read_text(encoding="utf-8") == render_markdown(report)
