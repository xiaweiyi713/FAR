from __future__ import annotations

import json
from pathlib import Path

from far.experiments.repository_maintenance import audit, render_markdown, verify_outputs

ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = ROOT / "reports/repository_maintenance.json"
REPORT_MD = ROOT / "reports/repository_maintenance.md"


def test_repository_maintenance_reports_match_current_tree() -> None:
    expected = audit(ROOT)

    assert json.loads(REPORT_JSON.read_text(encoding="utf-8")) == expected
    assert REPORT_MD.read_text(encoding="utf-8") == render_markdown(expected)


def test_repository_maintenance_verifier_accepts_tracked_reports() -> None:
    result = verify_outputs(ROOT, REPORT_JSON, REPORT_MD)

    assert result["valid"] is True
    assert result["maintenance_valid"] is True
    assert result["errors"] == []


def test_repository_maintenance_verifier_rejects_stale_reports(tmp_path: Path) -> None:
    stale_json = tmp_path / "repository_maintenance.json"
    stale_markdown = tmp_path / "repository_maintenance.md"
    report = audit(ROOT)
    report["tracked_files"]["count"] = 0
    stale_json.write_text(json.dumps(report), encoding="utf-8")
    stale_markdown.write_text("# stale\n", encoding="utf-8")

    result = verify_outputs(ROOT, stale_json, stale_markdown)

    assert result["valid"] is False
    assert result["maintenance_valid"] is True
    assert len(result["errors"]) == 2
    assert "JSON maintenance report is stale" in result["errors"][0]
    assert "Markdown maintenance report is stale" in result["errors"][1]
