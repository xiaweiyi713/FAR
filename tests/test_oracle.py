from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from bench.build.common import read_jsonl
from far.oracle import (
    ANSWER_METRICS,
    OracleConfig,
    OracleValidationError,
    UnsupportedOracleStageError,
    align_by_sample_id,
    apply_oracle,
    canonical_gold_answer,
    label_collisions,
    score_p1_ladder,
)

ROOT = Path(__file__).resolve().parents[1]


def _task(
    sample_id: str,
    gold: list[str],
    wrong: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": sample_id,
        "gold_answers": gold,
        "wrong_answers": wrong or [],
    }


def _prediction(sample_id: str, answer: str) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "answer": answer,
        "metadata": {"revision_trace": [{"changed": False}]},
    }


def _level(result: dict[str, object], name: str) -> dict[str, Any]:
    levels = cast(list[dict[str, Any]], result["levels"])
    return next(level for level in levels if level["name"] == name)


def test_baseline_is_a_deep_copy_and_revision_injects_deduplicated_gold() -> None:
    prediction = _prediction("S1", "Alpha")
    task = _task("S1", ["Alpha", "Beta", "Alpha"], ["Gamma"])
    original_prediction = deepcopy(prediction)
    original_task = deepcopy(task)

    baseline = apply_oracle(prediction, task, OracleConfig())
    revision = apply_oracle(prediction, task, OracleConfig(revision=True))

    assert baseline == prediction
    assert baseline is not prediction
    assert baseline["metadata"] is not prediction["metadata"]
    assert revision["answer"] == "Alpha ; Beta"
    assert canonical_gold_answer(task) == "Alpha ; Beta"
    assert prediction == original_prediction
    assert task == original_task


@pytest.mark.parametrize("stage", ["retrieval", "detection", "action"])
def test_unpropagated_upstream_oracle_stages_fail_closed(stage: str) -> None:
    config = OracleConfig(**{stage: True})
    with pytest.raises(UnsupportedOracleStageError, match="downstream answer replay"):
        apply_oracle(_prediction("S1", "Alpha"), _task("S1", ["Alpha"]), config)


def test_ladder_aligns_by_sample_id_instead_of_row_position() -> None:
    predictions = [_prediction("S1", "Alpha"), _prediction("S2", "Gamma")]
    tasks = [_task("S2", ["Beta"], ["Gamma"]), _task("S1", ["Alpha"], ["Gamma"])]

    result = score_p1_ladder(predictions, tasks)
    baseline = _level(result, "baseline")
    revision = _level(result, "oracle_revision")

    assert baseline["metrics"] == {
        "ramdocs_exact_match": 0.5,
        "gold_answer_coverage": 0.5,
        "wrong_answer_exclusion": 0.5,
    }
    assert revision["metrics"] == {metric: 1.0 for metric in ANSWER_METRICS}
    assert result["causal_attribution"] is False
    assert result["publication_gold"] is False


def test_alignment_rejects_duplicate_and_mismatched_ids() -> None:
    with pytest.raises(OracleValidationError, match="duplicate prediction"):
        align_by_sample_id(
            [_prediction("S1", "Alpha"), _prediction("S1", "Alpha")],
            [_task("S1", ["Alpha"])],
        )
    with pytest.raises(OracleValidationError, match="sample ID mismatch"):
        align_by_sample_id([_prediction("S1", "Alpha")], [_task("S2", ["Alpha"])])


def test_revision_ceiling_reports_unavoidable_gold_wrong_phrase_collisions() -> None:
    task = _task("S1", ["New York City"], ["York"])
    result = score_p1_ladder([_prediction("S1", "irrelevant")], [task])
    revision = _level(result, "oracle_revision")

    assert label_collisions(task) == (
        {
            "gold_answer": "New York City",
            "wrong_answer": "York",
            "reason": "wrong_phrase_within_mandatory_gold",
        },
    )
    assert result["label_collisions"]["samples"] == 1
    assert revision["metrics"] == {
        "ramdocs_exact_match": 0.0,
        "gold_answer_coverage": 1.0,
        "wrong_answer_exclusion": 0.0,
    }
    assert revision["label_feasible_samples"] == 0
    assert revision["label_feasible_metrics"] is None


def test_revision_ceiling_rejects_failures_not_explained_by_label_collision() -> None:
    with pytest.raises(OracleValidationError, match="not explained"):
        score_p1_ladder(
            [_prediction("S1", "irrelevant")],
            [_task("S1", ["New", "York"], ["New York"])],
        )


def test_frozen_far_baseline_is_reproduced_and_revision_ceiling_is_perfect() -> None:
    round1 = ROOT / "diagnostics/ramdocs_v2/round1"
    predictions = read_jsonl(round1 / "runs/far/predictions.jsonl")
    tasks = read_jsonl(ROOT / "bench/external/ramdocs_v1/splits/dev.jsonl")
    report = json.loads((round1 / "evaluations/far/report.json").read_text(encoding="utf-8"))

    result = score_p1_ladder(predictions, tasks)
    baseline = _level(result, "baseline")
    revision = _level(result, "oracle_revision")

    assert result["samples"] == 350
    assert result["label_collisions"]["samples"] == 9
    assert result["label_collisions"]["sample_ids"] == [
        "RAM0131",
        "RAM0139",
        "RAM0173",
        "RAM0204",
        "RAM0243",
        "RAM0266",
        "RAM0336",
        "RAM0364",
        "RAM0453",
    ]
    for metric in ANSWER_METRICS:
        assert baseline["metrics"][metric] == pytest.approx(report["metrics"][metric], abs=1e-12)
        assert revision["label_feasible_metrics"][metric] == 1.0
    assert revision["label_feasible_samples"] == 341
    assert revision["metrics"] == {
        "ramdocs_exact_match": pytest.approx(341 / 350),
        "gold_answer_coverage": 1.0,
        "wrong_answer_exclusion": pytest.approx(341 / 350),
    }
