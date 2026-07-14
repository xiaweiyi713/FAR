from __future__ import annotations

import json
from pathlib import Path

from far.experiments.revision_trace_audit import (
    DEFAULT_JSON,
    DEFAULT_MARKDOWN,
    audit_row,
    compute_report,
    render_markdown,
    verify_reports,
)

ROOT = Path(__file__).resolve().parents[1]


def _sample() -> dict[str, object]:
    return {
        "id": "example",
        "category": "temporal_shift",
        "initial_answer": "The event happened in 2020.",
        "expected_revision": {
            "action": "correct_temporal",
            "revised_answer": "The event happened in 2021.",
        },
    }


def _prediction(after: str, *, changed: bool = True) -> dict[str, object]:
    trace = {
        "action": "correct_temporal",
        "before": "The event happened in 2020.",
        "after": after,
        "changed": changed,
    }
    return {
        "sample_id": "example",
        "answer": after,
        "revision_action": "correct_temporal",
        "metadata": {"revision_trace": [trace], "primary_revision_trace": trace},
    }


def test_revision_trace_row_distinguishes_exact_and_collateral_edits() -> None:
    exact = audit_row(_sample(), _prediction("The event happened in 2021."))
    collateral = audit_row(
        _sample(),
        _prediction("The event definitely happened in 2021."),
    )

    assert exact["trace_bucket"] == "exact_target"
    assert exact["trace_delta_f1"] == 1.0
    assert exact["trace_target_complete"] == 1.0
    assert collateral["trace_bucket"] == "complete_with_collateral"
    assert 0.0 < collateral["trace_delta_f1"] < 1.0
    assert collateral["trace_collateral_edit"] == 1.0


def test_revision_trace_row_records_changed_flag_drift() -> None:
    row = audit_row(_sample(), _prediction("The event happened in 2021.", changed=False))

    assert row["trace_changed_flag_mismatches"] == 1
    assert row["trace_text_changes"] == 1
    assert row["trace_changed_flags"] == 0


def test_tracked_revision_trace_reports_are_current() -> None:
    report = compute_report()

    assert report["valid"] is True
    assert report["boundaries"]["model_calls"] == 0
    assert report["boundaries"]["test_accessed"] is False
    assert report["checks"]["family_trace_direction_3_of_3"] is True
    assert json.loads(DEFAULT_JSON.read_text(encoding="utf-8")) == report
    assert DEFAULT_MARKDOWN.read_text(encoding="utf-8") == render_markdown(report)


def test_revision_trace_verifier_rejects_report_drift(tmp_path: Path) -> None:
    report = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
    report["boundaries"]["preregistered_primary"] = True
    output_json = tmp_path / "report.json"
    output_markdown = tmp_path / "report.md"
    output_json.write_text(json.dumps(report), encoding="utf-8")
    output_markdown.write_text(DEFAULT_MARKDOWN.read_text(encoding="utf-8"), encoding="utf-8")

    audit = verify_reports(output_json=output_json, output_markdown=output_markdown)

    assert audit["valid"] is False
    assert "JSON report differs from deterministic recomputation" in audit["errors"]
