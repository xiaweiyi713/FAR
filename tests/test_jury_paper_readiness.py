from __future__ import annotations

from pathlib import Path

from experiments.jury_paper_readiness import audit

ROOT = Path(__file__).resolve().parents[1]


def test_jury_readiness_fails_closed_while_execution_artifacts_are_missing(
    tmp_path: Path,
) -> None:
    report = audit(
        ROOT / "bench/external/ramdocs_v1",
        tmp_path / "ramdocs-dev",
        tmp_path / "jury-consensus.json",
        tmp_path / "jury-labels.json",
        tmp_path / "sensitivity.json",
        tmp_path / "matrix.json",
        tmp_path / "falsirag-seal.json",
        tmp_path / "falsirag-score.json",
        tmp_path / "ramdocs-seal.json",
        tmp_path / "ramdocs-score.json",
        ROOT / "paper/main.tex",
    )
    assert report["ready"] is False
    assert report["human_gate_replaced_for_this_profile"] is True
    assert report["strict_independent_human_profile_ready"] is False
    assert report["can_claim_human_iaa"] is False
    assert report["checks"]["ramdocs_import_valid"] is True
    assert report["checks"]["gate_a_external_passed"] is False


def test_jury_readiness_rejects_human_or_external_claim_upgrade(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    paper.write_text(
        "independent human gold and an externally held blind test "
        "human inter-annotator agreement confirms",
        encoding="utf-8",
    )
    report = audit(
        ROOT / "bench/external/ramdocs_v1",
        tmp_path / "dev",
        tmp_path / "consensus.json",
        tmp_path / "labels.json",
        tmp_path / "sensitivity.json",
        tmp_path / "matrix.json",
        tmp_path / "falsirag.json",
        tmp_path / "falsirag-score.json",
        tmp_path / "ramdocs.json",
        tmp_path / "ramdocs-score.json",
        paper,
    )
    assert report["ready"] is False
    assert set(report["forbidden_claims_found"]) == {
        "independent human gold",
        "human inter-annotator agreement confirms",
        "externally held blind test",
    }
