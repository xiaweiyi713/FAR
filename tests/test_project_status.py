from __future__ import annotations

import json
from pathlib import Path

from experiments.project_status import build_status_snapshot, render_markdown

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
