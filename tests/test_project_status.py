from __future__ import annotations

import json
from pathlib import Path

from far.experiments.project_status import (
    build_status_snapshot,
    render_markdown,
    verify_status_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
STATUS_JSON = ROOT / "reports/project_status_snapshot.json"
STATUS_MD = ROOT / "reports/project_status_snapshot.md"


def test_project_status_snapshot_matches_tracked_report() -> None:
    generated = build_status_snapshot(ROOT)
    tracked = json.loads(STATUS_JSON.read_text(encoding="utf-8"))

    assert generated == tracked


def test_project_status_keeps_dual_track_claim_boundary() -> None:
    snapshot = build_status_snapshot(ROOT)

    assert snapshot["single_author_machine_audited_diagnostic"]["complete"] is True
    assert snapshot["single_author_machine_audited_paper"]["ready"] is True
    assert snapshot["single_author_machine_audited_paper"]["strict_aaai_submission_ready"] is False
    assert snapshot["strict_aaai_submission"]["ready"] is False
    assert snapshot["evidence"]["solo_release"]["valid"] is True
    assert snapshot["evidence"]["fever_binary"]["valid"] is True
    assert snapshot["evidence"]["review_priority"]["rows"] == 122
    assert snapshot["evidence"]["review_priority"]["dispositions"] == ["machine_disputed"]
    assert snapshot["evidence"]["review_priority"]["publication_gold"] is False
    assert "human_annotation" in snapshot["strict_aaai_submission"]["blockers"]
    assert "trusted_test_scoring" in snapshot["strict_aaai_submission"]["blockers"]


def test_project_status_is_portable_and_reader_facing() -> None:
    json_text = STATUS_JSON.read_text(encoding="utf-8")
    markdown = render_markdown(build_status_snapshot(ROOT))

    assert "/Users/" not in json_text
    assert str(ROOT) not in json_text
    assert STATUS_MD.read_text(encoding="utf-8") == markdown
    assert "must not be described as human gold" in markdown
    assert "submission/evidence.template.json" in markdown


def test_project_status_verifier_accepts_tracked_snapshots() -> None:
    audit = verify_status_snapshot(ROOT, STATUS_JSON, STATUS_MD)

    assert audit["valid"] is True
    assert audit["diagnostic_complete"] is True
    assert audit["errors"] == []


def test_project_status_verifier_rejects_stale_snapshots(tmp_path: Path) -> None:
    stale_json = tmp_path / "project_status_snapshot.json"
    stale_markdown = tmp_path / "project_status_snapshot.md"
    snapshot = json.loads(STATUS_JSON.read_text(encoding="utf-8"))
    snapshot["strict_aaai_submission"]["ready"] = True
    stale_json.write_text(json.dumps(snapshot), encoding="utf-8")
    stale_markdown.write_text("# stale\n", encoding="utf-8")

    audit = verify_status_snapshot(ROOT, stale_json, stale_markdown)

    assert audit["valid"] is False
    assert audit["diagnostic_complete"] is True
    assert len(audit["errors"]) == 2
    assert "JSON snapshot is stale" in audit["errors"][0]
    assert "Markdown snapshot is stale" in audit["errors"][1]


def test_solo_gate_verifies_project_status_snapshot() -> None:
    script = (ROOT / "scripts/solo_diagnostic_check.sh").read_text(encoding="utf-8")

    assert "uv run falsirag-project-status --verify" in script
    assert "tests/test_project_status.py" in script
