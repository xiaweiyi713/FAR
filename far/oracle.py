"""Fail-closed stage interventions over frozen RAMDocs predictions.

Phase P1 deliberately supports only an unchanged baseline and a gold-answer
label-injection ceiling. Retrieval, detection, and action interventions are not
valid until their changed state is replayed through downstream stages to produce
a new answer; silently scoring metadata-only edits would create circular evidence.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from far.eval.ramdocs import normalize_ramdocs_answer, score_ramdocs_answer

STAGES = ("retrieval", "detection", "action", "revision")
ANSWER_METRICS = (
    "ramdocs_exact_match",
    "gold_answer_coverage",
    "wrong_answer_exclusion",
)


class OracleValidationError(ValueError):
    """Raised when inputs or a computed ceiling violate the frozen P1 protocol."""


class UnsupportedOracleStageError(NotImplementedError):
    """Raised when a stage lacks downstream answer replay."""


@dataclass(frozen=True)
class OracleConfig:
    """Cumulative stage switches reserved by the preregistered protocol."""

    retrieval: bool = False
    detection: bool = False
    action: bool = False
    revision: bool = False

    @property
    def enabled_stages(self) -> tuple[str, ...]:
        return tuple(stage for stage in STAGES if bool(getattr(self, stage)))


@dataclass(frozen=True)
class OracleLevel:
    """One named P1 intervention level."""

    name: str
    config: OracleConfig


P1_LADDER = (
    OracleLevel("baseline", OracleConfig()),
    OracleLevel("oracle_revision", OracleConfig(revision=True)),
)


def _row_identifier(row: Mapping[str, Any], *, role: str) -> str:
    identifiers = [
        (key, str(row[key]).strip()) for key in ("sample_id", "id") if row.get(key) is not None
    ]
    if not identifiers or not identifiers[0][1]:
        raise OracleValidationError(f"{role} row is missing a non-empty sample identifier")
    if any(value != identifiers[0][1] for _, value in identifiers[1:]):
        raise OracleValidationError(f"{role} row has conflicting sample_id and id")
    return identifiers[0][1]


def _index_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    role: str,
) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        sample_id = _row_identifier(row, role=role)
        if sample_id in indexed:
            raise OracleValidationError(f"duplicate {role} sample identifier: {sample_id}")
        indexed[sample_id] = row
    if not indexed:
        raise OracleValidationError(f"{role} rows must not be empty")
    return indexed


def align_by_sample_id(
    predictions: Iterable[Mapping[str, Any]],
    tasks: Iterable[Mapping[str, Any]],
) -> tuple[tuple[Mapping[str, Any], Mapping[str, Any]], ...]:
    """Return prediction/task pairs aligned by ID, rejecting any set mismatch."""

    prediction_by_id = _index_rows(predictions, role="prediction")
    task_by_id = _index_rows(tasks, role="task")
    prediction_ids = set(prediction_by_id)
    task_ids = set(task_by_id)
    if prediction_ids != task_ids:
        missing_predictions = sorted(task_ids - prediction_ids)
        missing_tasks = sorted(prediction_ids - task_ids)
        raise OracleValidationError(
            "sample ID mismatch: "
            f"missing predictions={missing_predictions[:10]}, missing tasks={missing_tasks[:10]}"
        )
    return tuple(
        (prediction_by_id[sample_id], task_by_id[sample_id]) for sample_id in sorted(task_ids)
    )


def _answer_list(task: Mapping[str, Any], key: str) -> list[str]:
    raw = task.get(key)
    if not isinstance(raw, list):
        raise OracleValidationError(f"task {key} must be a list")
    answers: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise OracleValidationError(f"task {key} must contain non-empty strings")
        answers.append(item.strip())
    return answers


def canonical_gold_answer(task: Mapping[str, Any]) -> str:
    """Build the frozen, order-preserving gold-answer label injection."""

    gold_answers = _answer_list(task, "gold_answers")
    if not gold_answers:
        raise OracleValidationError("task gold_answers must not be empty")
    return " ; ".join(dict.fromkeys(gold_answers))


def _contains_phrase(container: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    if not phrase or len(phrase) > len(container):
        return False
    return any(
        container[index : index + len(phrase)] == phrase
        for index in range(len(container) - len(phrase) + 1)
    )


def label_collisions(task: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    """Return unavoidable normalized wrong-within-mandatory-gold collisions."""

    collisions: dict[tuple[str, str], dict[str, str]] = {}
    for gold in _answer_list(task, "gold_answers"):
        normalized_gold = normalize_ramdocs_answer(gold)
        for wrong in _answer_list(task, "wrong_answers"):
            if _contains_phrase(normalized_gold, normalize_ramdocs_answer(wrong)):
                collisions[(gold, wrong)] = {
                    "gold_answer": gold,
                    "wrong_answer": wrong,
                    "reason": "wrong_phrase_within_mandatory_gold",
                }
    return tuple(collisions[key] for key in sorted(collisions))


def apply_oracle(
    prediction: Mapping[str, Any],
    task: Mapping[str, Any],
    config: OracleConfig,
) -> dict[str, Any]:
    """Apply a valid P1 intervention without mutating either input.

    Retrieval, detection, and action fail closed because P1 has no downstream
    replay implementation. This guard is the key protection against producing a
    metadata-only ladder whose answer score cannot change by construction.
    """

    prediction_id = _row_identifier(prediction, role="prediction")
    task_id = _row_identifier(task, role="task")
    if prediction_id != task_id:
        raise OracleValidationError(
            f"prediction/task sample identifier mismatch: {prediction_id} != {task_id}"
        )
    unsupported = tuple(
        stage for stage in ("retrieval", "detection", "action") if getattr(config, stage)
    )
    if unsupported:
        raise UnsupportedOracleStageError(
            "downstream answer replay is required for oracle stages: " + ", ".join(unsupported)
        )

    output = deepcopy(dict(prediction))
    if config.revision:
        output["answer"] = canonical_gold_answer(task)
    return output


def _score_prediction(
    prediction: Mapping[str, Any],
    task: Mapping[str, Any],
) -> dict[str, float]:
    answer = prediction.get("answer")
    if not isinstance(answer, str):
        raise OracleValidationError("prediction answer must be a string")
    return score_ramdocs_answer(
        answer,
        _answer_list(task, "gold_answers"),
        _answer_list(task, "wrong_answers"),
    )


def score_p1_ladder(
    predictions: Iterable[Mapping[str, Any]],
    tasks: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Score the preregistered baseline and revision label-injection ceiling."""

    aligned = align_by_sample_id(predictions, tasks)
    levels: list[dict[str, Any]] = []
    previous_metrics: dict[str, float] | None = None
    collision_details: list[dict[str, Any]] = []
    for level in P1_LADDER:
        totals = {metric: 0.0 for metric in ANSWER_METRICS}
        feasible_totals = {metric: 0.0 for metric in ANSWER_METRICS}
        feasible_samples = 0
        unexplained_ceiling_ids: list[str] = []
        for prediction, task in aligned:
            transformed = apply_oracle(prediction, task, level.config)
            scores = _score_prediction(transformed, task)
            for metric in ANSWER_METRICS:
                totals[metric] += float(scores[metric])
            if level.config.revision:
                sample_id = _row_identifier(task, role="task")
                sample_collisions = label_collisions(task)
                perfect = all(float(scores[metric]) == 1.0 for metric in ANSWER_METRICS)
                if sample_collisions:
                    collision_details.append(
                        {"sample_id": sample_id, "pairs": list(sample_collisions)}
                    )
                    expected_collision_score = (
                        float(scores["ramdocs_exact_match"]) == 0.0
                        and float(scores["gold_answer_coverage"]) == 1.0
                        and float(scores["wrong_answer_exclusion"]) == 0.0
                    )
                    if not expected_collision_score:
                        unexplained_ceiling_ids.append(sample_id)
                elif not perfect:
                    unexplained_ceiling_ids.append(sample_id)
                else:
                    feasible_samples += 1
                    for metric in ANSWER_METRICS:
                        feasible_totals[metric] += float(scores[metric])
        metrics = {metric: totals[metric] / len(aligned) for metric in ANSWER_METRICS}
        delta = (
            None
            if previous_metrics is None
            else {metric: metrics[metric] - previous_metrics[metric] for metric in ANSWER_METRICS}
        )
        level_result: dict[str, Any] = {
            "name": level.name,
            "config": asdict(level.config),
            "metrics": metrics,
            "delta_from_previous": delta,
        }
        if level.config.revision:
            level_result["label_feasible_samples"] = feasible_samples
            level_result["label_feasible_metrics"] = (
                {metric: feasible_totals[metric] / feasible_samples for metric in ANSWER_METRICS}
                if feasible_samples
                else None
            )
        levels.append(level_result)
        if unexplained_ceiling_ids:
            raise OracleValidationError(
                "revision label-injection ceiling failures are not explained by an "
                "unavoidable label collision for sample IDs: "
                f"{unexplained_ceiling_ids[:10]}"
            )
        previous_metrics = metrics

    collision_details.sort(key=lambda item: str(item["sample_id"]))
    return {
        "schema_version": "far-oracle-p1-ladder-v1",
        "samples": len(aligned),
        "levels": levels,
        "causal_attribution": False,
        "publication_gold": False,
        "label_source": "ramdocs_upstream_answers_and_document_types",
        "label_collisions": {
            "samples": len(collision_details),
            "sample_ids": [item["sample_id"] for item in collision_details],
            "details": collision_details,
        },
    }
