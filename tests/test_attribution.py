from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from experiments.attribution import (
    DEV_METHODS,
    classify_failure,
    collection_score,
    component_attribution,
    retrieval_stratum,
    total_variation,
)
from experiments.evidence_attribution import verify_bundle
from experiments.protocol_longterm import ROADMAP_ACTIVE_SHA256, verify_active_roadmap


def _task(*, misinformation: bool = False) -> dict[str, object]:
    return {
        "category": "ambiguity_misinformation" if misinformation else "ambiguity_noise",
        "gold_answers": ["Alpha", "Beta"],
        "wrong_answers": ["Gamma"],
    }


def _score(*, coverage: float = 0.5, exclusion: float = 1.0) -> dict[str, float]:
    return {
        "ramdocs_exact_match": 0.0,
        "gold_answer_coverage": coverage,
        "wrong_answer_exclusion": exclusion,
    }


def _prediction(
    *,
    evidence: tuple[str, ...] = ("correct",),
    conflicts: tuple[str, ...] = (),
    changed: bool = False,
    answer: str = "Alpha",
) -> dict[str, object]:
    return {
        "answer": answer,
        "evidence_ids": list(evidence),
        "predicted_conflict_types": list(conflicts),
        "metadata": {"revision_trace": [{"changed": changed}]},
    }


@pytest.mark.parametrize(
    ("task", "score", "prediction", "expected"),
    [
        (_task(), _score(), _prediction(evidence=("noise",)), "retrieval_miss"),
        (_task(misinformation=True), _score(), _prediction(), "conflict_undetected"),
        (
            _task(),
            _score(),
            _prediction(conflicts=("entity",), changed=True),
            "conflict_detected_revision_wrong",
        ),
        (
            _task(),
            _score(coverage=0.5),
            _prediction(conflicts=("entity",)),
            "answer_set_incomplete",
        ),
        (
            _task(),
            _score(coverage=1.0, exclusion=0.0),
            _prediction(conflicts=("entity",), answer="Alpha Beta Gamma"),
            "answer_set_overfull",
        ),
        (
            _task(),
            _score(coverage=1.0, exclusion=1.0),
            _prediction(conflicts=("entity",), answer="Alpha Beta"),
            "format_em_mismatch",
        ),
    ],
)
def test_failure_bucket_priority_is_exhaustive(
    task: dict[str, object],
    score: dict[str, float],
    prediction: dict[str, object],
    expected: str,
) -> None:
    bucket, signals = classify_failure(
        task=task,
        far_score=score,
        far_prediction=prediction,
        correct_document_ids={"correct"},
    )
    assert bucket == expected
    assert 0.0 <= signals["correct_document_recall"] <= 1.0


def test_collection_score_uses_only_gold_and_wrong_phrase_hits() -> None:
    score = collection_score("Alpha and Gamma", ["Alpha", "Beta"], ["Gamma"])
    assert score["gold_hits"] == 1
    assert score["wrong_hits"] == 1
    assert score["precision"] == 0.5
    assert score["recall"] == 0.5
    assert score["f1"] == 0.5


def test_retrieval_strata_are_exact() -> None:
    assert retrieval_stratum(0.0) == "none"
    assert retrieval_stratum(0.5) == "partial"
    assert retrieval_stratum(1.0) == "complete"
    with pytest.raises(ValueError):
        retrieval_stratum(1.1)


def test_missing_upstream_correct_document_is_retrieval_miss() -> None:
    bucket, signals = classify_failure(
        task=_task(misinformation=True),
        far_score=_score(),
        far_prediction=_prediction(evidence=("noise",)),
        correct_document_ids=set(),
    )
    assert bucket == "retrieval_miss"
    assert signals["correct_document_available"] is False
    assert signals["correct_document_recall"] == 0.0


def test_total_variation_handles_nonmatching_support() -> None:
    assert total_variation({"a": 1.0}, {"b": 1.0}) == 1.0
    assert total_variation({"a": 0.5, "b": 0.5}, {"a": 0.5, "b": 0.5}) == 0.0


def test_component_attribution_freezes_flip_and_gain_paths() -> None:
    sample_ids = {f"D{index}" for index in range(1, 7)}
    scores: dict[str, dict[str, dict[str, object]]] = {}
    predictions: dict[str, dict[str, dict[str, object]]] = {}
    for method in DEV_METHODS:
        scores[method] = {
            sample_id: {
                "sample_id": sample_id,
                "answer_correctness": 0.9 if method == "far" else 0.2,
            }
            for sample_id in sample_ids
        }
        predictions[method] = {
            sample_id: _prediction(conflicts=("entity",), changed=False)
            for sample_id in sample_ids
        }
    predictions["far"]["D6"] = _prediction(conflicts=("entity",), changed=True)
    dispositions = {
        sample_id: "machine_confirmed" if sample_id < "D4" else "machine_disputed"
        for sample_id in sample_ids
    }
    result = component_attribution(scores, predictions, dispositions)
    assert result["typed_minus_untyped_gain_samples"] == 6
    assert result["typed_minus_untyped_gain_paths"] == {
        "detected_no_changed_revision": 5,
        "changed_revision": 1,
        "other": 0,
    }
    assert result["flip_matrix"]["minus_typed_conflict"]["binary_flips"] == {
        "far_only": 6
    }


def test_component_attribution_rejects_misaligned_inputs() -> None:
    scores = {method: {"D1": {"answer_correctness": 1.0}} for method in DEV_METHODS}
    predictions = {method: {"D1": deepcopy(_prediction())} for method in DEV_METHODS}
    scores["minus_boundary_query"] = {}
    with pytest.raises(ValueError):
        component_attribution(scores, predictions, {"D1": "machine_confirmed"})


def test_registered_roadmap_fingerprint_is_active() -> None:
    assert verify_active_roadmap() == ROADMAP_ACTIVE_SHA256


def test_attribution_verifier_fails_closed_without_release(tmp_path: Path) -> None:
    audit = verify_bundle(
        ramdocs_data_dir=tmp_path / "ramdocs",
        round1_dir=tmp_path / "round1",
        round2_dir=tmp_path / "round2",
        solo_suite_dir=tmp_path / "solo",
        machine_rows_path=tmp_path / "machine.jsonl",
        bundle_dir=tmp_path / "missing",
        report_path=tmp_path / "report.md",
    )
    assert audit["valid"] is False
    assert audit["gate_r1_passed"] is False
