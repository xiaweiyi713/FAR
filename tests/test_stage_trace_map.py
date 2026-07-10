from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.stage_trace_map import (
    BUCKETS,
    FAR_TRACE_METHODS,
    METHODS,
    answer_changed,
    build_reports,
    classify_trace_cell,
    cluster_bootstrap_difference,
    compute_stage_trace_map,
    report_text,
    verify_reports,
)

ROOT = Path(__file__).resolve().parents[1]
RAMDOCS = ROOT / "bench/external/ramdocs_v1"
ROUND1 = ROOT / "diagnostics/ramdocs_v2/round1"


def _prediction(answer: str, evidence_ids: list[str]) -> dict[str, object]:
    return {"answer": answer, "evidence_ids": evidence_ids}


@pytest.mark.parametrize(
    ("prediction", "score", "initial", "expected"),
    [
        (_prediction("Alpha", []), {"ramdocs_exact_match": 1.0}, "Beta", "correct"),
        (
            _prediction("Beta", ["noise"]),
            {"ramdocs_exact_match": 0.0},
            "Beta",
            "retrieval_unscorable",
        ),
        (
            _prediction("Beta", ["noise"]),
            {"ramdocs_exact_match": 0.0},
            "Beta",
            "retrieval_miss",
        ),
        (
            _prediction("Beta [correct]", ["correct"]),
            {"ramdocs_exact_match": 0.0},
            "Beta",
            "post_retrieval_unchanged_wrong",
        ),
        (
            _prediction("Gamma", ["correct"]),
            {"ramdocs_exact_match": 0.0},
            "Beta",
            "post_retrieval_changed_wrong",
        ),
    ],
)
def test_trace_cells_are_exhaustive_and_citation_aware(
    prediction: dict[str, object],
    score: dict[str, float],
    initial: str,
    expected: str,
) -> None:
    correct_document_ids = set() if expected == "retrieval_unscorable" else {"correct"}
    cell = classify_trace_cell(
        prediction=prediction,
        score=score,
        initial_answer=initial,
        correct_document_ids=correct_document_ids,
    )

    assert cell["bucket"] == expected
    assert cell["bucket"] in BUCKETS


def test_answer_change_ignores_citations_but_not_content() -> None:
    assert answer_changed("Alpha", "Alpha [D1]") is False
    assert answer_changed("Alpha", "Beta [D1]") is True


def test_cluster_bootstrap_keeps_all_methods_per_sample() -> None:
    cells = {
        "S1": {method: "post_retrieval_changed_wrong" for method in METHODS},
        "S2": {method: "retrieval_miss" for method in METHODS},
    }

    result = cluster_bootstrap_difference(cells, resamples=20, seed=1729)

    assert result["estimate"] == 0.0
    assert result["clusters"] == 2
    assert result["methods_per_cluster"] == 8
    with pytest.raises(ValueError, match="all frozen methods"):
        cluster_bootstrap_difference({"S1": {"far": "correct"}}, resamples=2, seed=1)


def test_frozen_round1_trace_map_is_exhaustive_and_capability_aware() -> None:
    result = compute_stage_trace_map(
        ramdocs_data_dir=RAMDOCS,
        round1_dir=ROUND1,
        resamples=20,
        seed=1729,
    )

    assert result["samples"] == 350
    assert result["sample_method_cells"] == 2800
    assert result["methods"] == list(METHODS)
    assert result["causal_attribution"] is False
    assert result["publication_gold"] is False
    assert result["test_accessed"] is False
    for method in METHODS:
        assert sum(result["method_map"][method]["counts"].values()) == 350
        assert set(result["method_map"][method]["counts"]) == set(BUCKETS)
        expected_trace = method in FAR_TRACE_METHODS
        assert result["capability_matrix"][method]["typed_conflict_signal"] is expected_trace
        assert result["capability_matrix"][method]["claim_level_revision_trace"] is expected_trace
    assert set(result["far_trace_details"]) == set(FAR_TRACE_METHODS)
    assert all(
        result["method_map"][method]["counts"]["retrieval_unscorable"] <= 2 for method in METHODS
    )
    assert "not a causal oracle ladder" in report_text(result)


def test_reports_verify_by_deterministic_recomputation(tmp_path: Path) -> None:
    output_json = tmp_path / "stage_trace_map.json"
    output_report = tmp_path / "stage_trace_map.md"
    built = build_reports(
        ramdocs_data_dir=RAMDOCS,
        round1_dir=ROUND1,
        output_json=output_json,
        output_report=output_report,
        resamples=20,
        seed=1729,
    )

    audit = verify_reports(
        ramdocs_data_dir=RAMDOCS,
        round1_dir=ROUND1,
        output_json=output_json,
        output_report=output_report,
    )
    assert built["statistics"] == {"resamples": 20, "seed": 1729}
    assert audit["valid"] is True

    tampered = json.loads(output_json.read_text(encoding="utf-8"))
    tampered["causal_attribution"] = True
    output_json.write_text(json.dumps(tampered), encoding="utf-8")
    audit = verify_reports(
        ramdocs_data_dir=RAMDOCS,
        round1_dir=ROUND1,
        output_json=output_json,
        output_report=output_report,
    )
    assert audit["valid"] is False
    assert "deterministic recomputation" in audit["errors"][0]


def test_tracked_stage_trace_reports_verify() -> None:
    audit = verify_reports(
        ramdocs_data_dir=RAMDOCS,
        round1_dir=ROUND1,
        output_json=ROOT / "reports/stage_trace_map.json",
        output_report=ROOT / "reports/stage_trace_map.md",
    )

    assert audit["valid"] is True
