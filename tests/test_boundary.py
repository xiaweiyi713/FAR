from __future__ import annotations

import json
from pathlib import Path

from bench.build.common import sha256_file
from experiments.boundary import (
    _calibration_rows,
    _holm,
    _require_boundary_order,
    boundary_score,
)
from experiments.evidence_boundary import verify_release
from experiments.protocol_boundary import verify_boundary_protocol


def _complete_run(root: Path, section: str, dataset: str, method: str, expected: int) -> None:
    directory = root / section / dataset / method
    directory.mkdir(parents=True)
    predictions = directory / "predictions.jsonl"
    predictions.write_text("", encoding="utf-8")
    manifest = {
        "status": "complete",
        "completed": expected,
        "errors": 0,
        "partial": section == "calibration",
        "predictions_sha256": sha256_file(predictions),
    }
    (directory / "run_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True),
        encoding="utf-8",
    )


def test_wikicontradict_boundary_score_requires_both_answers() -> None:
    task = {
        "benchmark": "wikicontradict",
        "reference_answers": ["Alpha City", "Beta Town"],
    }
    partial = boundary_score(task, "Alpha City is reported.")
    complete = boundary_score(
        task,
        "The sources conflict: one reports Alpha City and the other Beta Town.",
    )
    assert partial["boundary_score"] == 0.5
    assert partial["binary_success"] == 0
    assert complete["boundary_score"] == 1.0
    assert complete["binary_success"] == 1
    assert complete["conflict_acknowledged"] == 1


def test_boundary_protocol_and_import_manifests_are_frozen() -> None:
    audit = verify_boundary_protocol()
    assert audit["valid"] is True
    assert audit["test_accessed"] is False
    assert audit["publication_gold"] is False
    assert audit["human_iaa"] is False


def test_google_boundary_score_preserves_correct_answer() -> None:
    task = {
        "benchmark": "google_rag_conflicts",
        "reference_answers": ["42 milligrams"],
    }
    assert boundary_score(task, "42 milligrams")["binary_success"] == 1
    assert boundary_score(task, "84 milligrams")["binary_success"] == 0


def test_holm_adjustment_is_monotone_in_sorted_p_values() -> None:
    adjusted = _holm({"a": 0.01, "b": 0.04})
    assert adjusted == {"a": 0.02, "b": 0.04}


def test_calibration_selection_covers_strata() -> None:
    rows = [
        {"id": f"D{index}", "strata": {"group": str(index % 3)}}
        for index in range(12)
    ]
    selected = _calibration_rows(rows)
    assert len(selected) == 5
    assert {row["strata"]["group"] for row in selected} == {"0", "1", "2"}


def test_boundary_verifier_fails_closed_without_release(tmp_path: Path) -> None:
    audit = verify_release(tmp_path / "missing", tmp_path / "missing.md")
    assert audit["valid"] is False
    assert audit["gate_b_complete"] is False
    assert audit["publication_gold"] is False
    assert audit["human_iaa"] is False
    assert audit["test_accessed"] is False


def test_boundary_formal_requires_both_calibration_arms(tmp_path: Path) -> None:
    _complete_run(tmp_path, "calibration", "wikicontradict", "far", 5)
    try:
        _require_boundary_order(tmp_path, "wikicontradict", calibration=False)
    except ValueError as exc:
        assert "far_minus_typed_conflict" in str(exc)
    else:
        raise AssertionError("formal run started before both calibration arms")


def test_boundary_google_waits_for_wiki_formal_completion(tmp_path: Path) -> None:
    for method in ("far", "far_minus_typed_conflict"):
        _complete_run(tmp_path, "calibration", "rag_conflicts", method, 5)
    try:
        _require_boundary_order(tmp_path, "rag_conflicts", calibration=True)
    except ValueError as exc:
        assert "wikicontradict" in str(exc)
    else:
        raise AssertionError("Google run started before Wiki formal completion")
