from __future__ import annotations

import json
from pathlib import Path

from far.experiments.selective_revision_audit import (
    DEFAULT_JSON,
    DEFAULT_MARKDOWN,
    compute_report,
    render_markdown,
    verify_reports,
)


def test_selective_revision_report_is_bounded_and_current() -> None:
    report = compute_report()

    assert report["valid"] is True
    assert report["boundaries"]["model_calls"] == 0
    assert report["boundaries"]["test_accessed"] is False
    assert report["boundaries"]["deployable_selector_evaluated"] is False
    assert report["checks"]["whole_answer_threshold_false_safe"] is True
    assert report["checks"]["confidence_threshold_not_fidelity_improving"] is True
    assert json.loads(DEFAULT_JSON.read_text(encoding="utf-8")) == report
    assert DEFAULT_MARKDOWN.read_text(encoding="utf-8") == render_markdown(report)


def test_selective_revision_reference_envelope_has_little_selection_headroom() -> None:
    report = compute_report()
    envelope = report["reference_arm_choice_envelope"]
    arms = report["fixed_arms"]

    assert arms["preserve"]["answer_soft_f1_ge_0_8"] == 60
    assert arms["typed"]["mean_revision_delta_f1"] > arms["generic"]["mean_revision_delta_f1"]
    assert 0.0 < envelope["gain_over_always_typed"] < 0.02
    assert envelope["deployable"] is False


def test_selective_revision_high_confidence_subset_is_not_higher_fidelity() -> None:
    report = compute_report()
    curve = report["confidence_curves"]["preserve"]
    all_typed = next(row for row in curve if row["threshold"] == 0.0)
    high = next(row for row in curve if row["threshold"] == 0.9)

    assert high["selected_rows"] == 31
    assert (
        high["selected_mean_typed_revision_delta_f1"]
        <= all_typed["selected_mean_typed_revision_delta_f1"]
    )
    assert (
        high["selected_trace_target_complete_rate"]
        <= all_typed["selected_trace_target_complete_rate"]
    )
    assert high["selected_trace_collateral_rate"] >= all_typed["selected_trace_collateral_rate"]


def test_selective_revision_verifier_rejects_boundary_drift(tmp_path: Path) -> None:
    report = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
    report["boundaries"]["deployable_selector_evaluated"] = True
    output_json = tmp_path / "report.json"
    output_markdown = tmp_path / "report.md"
    output_json.write_text(json.dumps(report), encoding="utf-8")
    output_markdown.write_text(DEFAULT_MARKDOWN.read_text(encoding="utf-8"), encoding="utf-8")

    audit = verify_reports(output_json=output_json, output_markdown=output_markdown)

    assert audit["valid"] is False
    assert "JSON report differs from deterministic recomputation" in audit["errors"]
