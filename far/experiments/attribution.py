"""Deterministic WS1 mechanism attribution over frozen development artifacts.

This module is intentionally model-free.  Its formal build entry point refuses to
run unless the roadmap and implementation match an explicit commit already present
on ``origin/main``.  That makes the analysis-before-look ordering machine-checkable.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from statistics import mean
from typing import Any

from far.bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.eval.ramdocs import normalize_ramdocs_answer
from far.eval.stats import mcnemar_exact, paired_bootstrap_comparison
from far.experiments.protocol_longterm import ROOT, verify_active_roadmap

BUCKET_PRIORITY = (
    "retrieval_miss",
    "conflict_undetected",
    "conflict_detected_revision_wrong",
    "answer_set_incomplete",
    "answer_set_overfull",
    "format_em_mismatch",
)
HYPOTHESIS_IDS = (
    "H-upstream",
    "H-conflict-shape",
    "H-metric",
    "H-component",
)
DEV_METHODS = (
    "far",
    "minus_typed_conflict",
    "minus_typed_revision",
    "minus_refutation_query",
    "minus_boundary_query",
)
FREEZE_PATHS = (
    "docs/PLAN_LONGTERM_OPTIMIZATION.md",
    "experiments/protocol_longterm.py",
    "experiments/attribution.py",
    "experiments/evidence_attribution.py",
    "tests/test_attribution.py",
)
SAMPLE_CORRECTNESS_THRESHOLD = 0.8


def _by_id(rows: Iterable[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        item_id = str(row[key])
        if item_id in result:
            raise ValueError(f"duplicate {key}: {item_id}")
        result[item_id] = row
    return result


def _contains_phrase(container: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    if not phrase or len(phrase) > len(container):
        return False
    return any(
        container[index : index + len(phrase)] == phrase
        for index in range(len(container) - len(phrase) + 1)
    )


def collection_score(
    prediction: str,
    gold_answers: list[str],
    wrong_answers: list[str],
) -> dict[str, float | int]:
    """Return the preregistered descriptive phrase-collection precision/recall/F1."""

    predicted = normalize_ramdocs_answer(prediction)
    gold_hits = sum(
        _contains_phrase(predicted, normalize_ramdocs_answer(answer)) for answer in gold_answers
    )
    wrong_hits = sum(
        _contains_phrase(predicted, normalize_ramdocs_answer(answer)) for answer in wrong_answers
    )
    precision_denominator = gold_hits + wrong_hits
    precision = gold_hits / precision_denominator if precision_denominator else 0.0
    recall = gold_hits / len(gold_answers) if gold_answers else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "gold_hits": gold_hits,
        "wrong_hits": wrong_hits,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _revision_changed(prediction: dict[str, Any]) -> bool:
    metadata = prediction.get("metadata")
    revisions = metadata.get("revision_trace", []) if isinstance(metadata, dict) else []
    return any(isinstance(item, dict) and item.get("changed") is True for item in revisions)


def _conflict_types(prediction: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted({str(item) for item in prediction.get("predicted_conflict_types", [])}))


def correct_document_recall(
    prediction: dict[str, Any],
    correct_document_ids: set[str],
) -> float:
    if not correct_document_ids:
        return 0.0
    retrieved = {str(item) for item in prediction.get("evidence_ids", [])}
    return len(retrieved & correct_document_ids) / len(correct_document_ids)


def classify_failure(
    *,
    task: dict[str, Any],
    far_score: dict[str, Any],
    far_prediction: dict[str, Any],
    correct_document_ids: set[str],
) -> tuple[str, dict[str, Any]]:
    """Assign one both-incorrect RAMDocs case to the earliest frozen failure stage."""

    if float(far_score["ramdocs_exact_match"]) != 0.0:
        raise ValueError("failure classification requires an incorrect FAR prediction")
    retrieval_recall = correct_document_recall(far_prediction, correct_document_ids)
    conflicts = _conflict_types(far_prediction)
    changed = _revision_changed(far_prediction)
    collection = collection_score(
        str(far_prediction.get("answer", "")),
        [str(item) for item in task.get("gold_answers", [])],
        [str(item) for item in task.get("wrong_answers", [])],
    )
    if retrieval_recall == 0.0:
        bucket = "retrieval_miss"
    elif task.get("category") == "ambiguity_misinformation" and not conflicts:
        bucket = "conflict_undetected"
    elif conflicts and changed:
        bucket = "conflict_detected_revision_wrong"
    elif float(far_score["gold_answer_coverage"]) < 1.0:
        bucket = "answer_set_incomplete"
    elif float(far_score["wrong_answer_exclusion"]) < 1.0:
        bucket = "answer_set_overfull"
    else:
        bucket = "format_em_mismatch"
    return bucket, {
        "correct_document_available": bool(correct_document_ids),
        "correct_document_recall": retrieval_recall,
        "conflict_detected": bool(conflicts),
        "predicted_conflict_types": list(conflicts),
        "revision_changed": changed,
        "gold_answer_coverage": float(far_score["gold_answer_coverage"]),
        "wrong_answer_exclusion": float(far_score["wrong_answer_exclusion"]),
        "collection_f1": float(collection["f1"]),
        "gold_hits": int(collection["gold_hits"]),
        "wrong_hits": int(collection["wrong_hits"]),
    }


def retrieval_stratum(value: float) -> str:
    if value == 0.0:
        return "none"
    if value == 1.0:
        return "complete"
    if 0.0 < value < 1.0:
        return "partial"
    raise ValueError("correct-document recall must be in [0, 1]")


def _selected_jsonl(
    path: Path,
    *,
    key: str,
    allowed_ids: set[str],
) -> list[dict[str, Any]]:
    """Parse only selected rows, leaving held-out row payloads uninterpreted."""

    pattern = re.compile(rf'"{re.escape(key)}"\s*:\s*"([^"]+)"')
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            match = pattern.search(raw)
            if match is None or match.group(1) not in allowed_ids:
                continue
            rows.append(json.loads(raw))
    return rows


def _paired_summary(
    sample_ids: list[str],
    baseline: dict[str, dict[str, Any]],
    candidate: dict[str, dict[str, Any]],
    metric: str,
    *,
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    if not sample_ids:
        return {"samples": 0, "metric": metric, "comparison": None, "mcnemar": None}
    baseline_rows = [baseline[sample_id] for sample_id in sample_ids]
    candidate_rows = [candidate[sample_id] for sample_id in sample_ids]
    comparison = paired_bootstrap_comparison(
        baseline_rows,
        candidate_rows,
        metric,
        resamples=resamples,
        seed=seed,
    )
    mcnemar = None
    if metric == "ramdocs_exact_match":
        mcnemar = mcnemar_exact(
            [bool(row[metric]) for row in baseline_rows],
            [bool(row[metric]) for row in candidate_rows],
        )
    return {
        "samples": len(sample_ids),
        "metric": metric,
        "comparison": comparison,
        "mcnemar": mcnemar,
    }


def conflict_type_distribution(predictions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    detected = 0
    for prediction in predictions.values():
        kinds = _conflict_types(prediction)
        detected += bool(kinds)
        if kinds:
            counts.update(kinds)
        else:
            counts["none"] += 1
    total = sum(counts.values())
    return {
        "samples": len(predictions),
        "detected_samples": detected,
        "detection_rate": detected / len(predictions) if predictions else 0.0,
        "counts": dict(sorted(counts.items())),
        "distribution": {key: value / total for key, value in sorted(counts.items())}
        if total
        else {},
    }


def total_variation(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    return 0.5 * sum(abs(float(left.get(key, 0.0)) - float(right.get(key, 0.0))) for key in keys)


def _flip_outcome(candidate: float, baseline: float) -> str:
    pair = (candidate >= SAMPLE_CORRECTNESS_THRESHOLD, baseline >= SAMPLE_CORRECTNESS_THRESHOLD)
    return {
        (True, True): "both_correct",
        (True, False): "far_only",
        (False, True): "comparison_only",
        (False, False): "both_incorrect",
    }[pair]


def component_attribution(
    scores: dict[str, dict[str, dict[str, Any]]],
    predictions: dict[str, dict[str, dict[str, Any]]],
    dispositions: dict[str, str],
) -> dict[str, Any]:
    expected = set(scores["far"])
    if not expected or any(set(scores[method]) != expected for method in DEV_METHODS):
        raise ValueError("dev component scores must share one non-empty sample set")
    if any(set(predictions[method]) != expected for method in DEV_METHODS):
        raise ValueError("dev component predictions must share the score sample set")
    if set(dispositions) != expected:
        raise ValueError("machine disposition rows must exactly cover the dev sample set")

    flips: dict[str, Any] = {}
    for method in DEV_METHODS[1:]:
        counts = Counter(
            _flip_outcome(
                float(scores["far"][sample_id]["answer_correctness"]),
                float(scores[method][sample_id]["answer_correctness"]),
            )
            for sample_id in expected
        )
        deltas = [
            float(scores["far"][sample_id]["answer_correctness"])
            - float(scores[method][sample_id]["answer_correctness"])
            for sample_id in expected
        ]
        flips[method] = {
            "samples": len(expected),
            "binary_flips": dict(sorted(counts.items())),
            "mean_continuous_delta": mean(deltas),
            "positive_delta_samples": sum(delta > 0 for delta in deltas),
            "negative_delta_samples": sum(delta < 0 for delta in deltas),
            "zero_delta_samples": sum(delta == 0 for delta in deltas),
        }

    gain_ids = sorted(
        sample_id
        for sample_id in expected
        if float(scores["far"][sample_id]["answer_correctness"])
        > float(scores["minus_typed_conflict"][sample_id]["answer_correctness"])
    )
    gain_paths: Counter[str] = Counter()
    for sample_id in gain_ids:
        prediction = predictions["far"][sample_id]
        if _revision_changed(prediction):
            gain_paths["changed_revision"] += 1
        elif _conflict_types(prediction):
            gain_paths["detected_no_changed_revision"] += 1
        else:
            gain_paths["other"] += 1

    sensitivity: dict[str, Any] = {}
    for disposition in ("machine_confirmed", "machine_disputed"):
        ids = sorted(sample_id for sample_id, value in dispositions.items() if value == disposition)
        if not ids:
            sensitivity[disposition] = {"samples": 0}
            continue
        far_mean = mean(float(scores["far"][item]["answer_correctness"]) for item in ids)
        untyped_mean = mean(
            float(scores["minus_typed_conflict"][item]["answer_correctness"]) for item in ids
        )
        sensitivity[disposition] = {
            "samples": len(ids),
            "far_answer_correctness": far_mean,
            "untyped_answer_correctness": untyped_mean,
            "typed_minus_untyped": far_mean - untyped_mean,
        }
    return {
        "schema_version": "far-ws1-dev-component-attribution-v1",
        "samples": len(expected),
        "correctness_threshold": SAMPLE_CORRECTNESS_THRESHOLD,
        "flip_matrix": flips,
        "typed_minus_untyped_gain_samples": len(gain_ids),
        "typed_minus_untyped_gain_paths": {
            key: gain_paths.get(key, 0)
            for key in ("detected_no_changed_revision", "changed_revision", "other")
        },
        "machine_disposition_sensitivity": sensitivity,
        "far_conflict_distribution": conflict_type_distribution(predictions["far"]),
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }


def _git_output(args: list[str]) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return completed.stdout


def verify_analysis_freeze(commit: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{7,40}", commit):
        raise ValueError("analysis freeze commit must be a hexadecimal Git commit")
    full_commit = _git_output(["rev-parse", f"{commit}^{{commit}}"]).decode().strip()
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", full_commit, "origin/main"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    files: dict[str, str] = {}
    for relative in FREEZE_PATHS:
        current = ROOT / relative
        committed = _git_output(["show", f"{full_commit}:{relative}"])
        if current.read_bytes() != committed:
            raise ValueError(f"analysis implementation differs from freeze commit: {relative}")
        files[relative] = sha256_file(current)
    return {"commit": full_commit, "files": files}


def _load_dev_components(
    suite_dir: Path,
    machine_rows_path: Path,
) -> tuple[
    dict[str, dict[str, dict[str, Any]]],
    dict[str, dict[str, dict[str, Any]]],
    dict[str, str],
    dict[str, str],
]:
    scores: dict[str, dict[str, dict[str, Any]]] = {}
    predictions: dict[str, dict[str, dict[str, Any]]] = {}
    source_files: dict[str, str] = {}
    for method in DEV_METHODS:
        score_path = suite_dir / "evaluations" / method / "scores.jsonl"
        prediction_path = suite_dir / "runs" / method / "predictions.jsonl"
        scores[method] = _by_id(read_jsonl(score_path), "sample_id")
        predictions[method] = _by_id(read_jsonl(prediction_path), "sample_id")
        source_files[str(score_path)] = sha256_file(score_path)
        source_files[str(prediction_path)] = sha256_file(prediction_path)
    dev_ids = set(scores["far"])
    machine_rows = _selected_jsonl(
        machine_rows_path,
        key="sample_id",
        allowed_ids=dev_ids,
    )
    dispositions = {str(row["sample_id"]): str(row["disposition"]) for row in machine_rows}
    source_files[str(machine_rows_path)] = sha256_file(machine_rows_path)
    return scores, predictions, dispositions, source_files


def compute_attribution(
    *,
    ramdocs_data_dir: Path,
    round1_dir: Path,
    round2_dir: Path,
    solo_suite_dir: Path,
    machine_rows_path: Path,
    resamples: int = 2000,
    seed: int = 1729,
) -> dict[str, Any]:
    verify_active_roadmap()
    dev_tasks_path = ramdocs_data_dir / "splits" / "dev.jsonl"
    corpus_path = ramdocs_data_dir / "corpus.jsonl"
    tasks = _by_id(read_jsonl(dev_tasks_path), "id")
    if len(tasks) != 350 or {str(row.get("split")) for row in tasks.values()} != {"dev"}:
        raise ValueError("WS1 requires exactly the frozen 350 RAMDocs dev tasks")
    allowed_doc_ids = {
        str(doc_id) for task in tasks.values() for doc_id in task.get("document_ids", [])
    }
    corpus = _by_id(
        _selected_jsonl(corpus_path, key="doc_id", allowed_ids=allowed_doc_ids),
        "doc_id",
    )
    if set(corpus) != allowed_doc_ids:
        raise ValueError("dev-only RAMDocs corpus selection is incomplete")
    correct_ids = {
        sample_id: {
            str(doc_id)
            for doc_id in task["document_ids"]
            if corpus[str(doc_id)].get("metadata", {}).get("document_type") == "correct"
        }
        for sample_id, task in tasks.items()
    }
    round_manifest_path = round2_dir / "round_manifest.json"
    round_manifest = json.loads(round_manifest_path.read_text(encoding="utf-8"))
    if (
        round_manifest.get("gate_a_passed") is not False
        or round_manifest.get("stop_rule_triggered") is not True
    ):
        raise ValueError("WS1 requires the frozen failed Round 2 stop decision")
    baseline_method = str(round_manifest["reused_round1_artifacts"]["baseline_method"])
    far_scores_path = round2_dir / "evaluations" / "far" / "scores.jsonl"
    far_predictions_path = round2_dir / "runs" / "far" / "predictions.jsonl"
    baseline_scores_path = round1_dir / "evaluations" / baseline_method / "scores.jsonl"
    baseline_predictions_path = round1_dir / "runs" / baseline_method / "predictions.jsonl"
    far_scores = _by_id(read_jsonl(far_scores_path), "sample_id")
    far_predictions = _by_id(read_jsonl(far_predictions_path), "sample_id")
    baseline_scores = _by_id(read_jsonl(baseline_scores_path), "sample_id")
    baseline_predictions = _by_id(read_jsonl(baseline_predictions_path), "sample_id")
    expected_ids = set(tasks)
    for name, rows in (
        ("far scores", far_scores),
        ("far predictions", far_predictions),
        ("baseline scores", baseline_scores),
        ("baseline predictions", baseline_predictions),
    ):
        if set(rows) != expected_ids:
            raise ValueError(f"{name} do not exactly cover RAMDocs dev")

    per_sample_signals: dict[str, dict[str, Any]] = {}
    buckets: list[dict[str, Any]] = []
    retrieval_groups: dict[str, list[str]] = {key: [] for key in ("none", "partial", "complete")}
    conflict_groups: dict[str, list[str]] = {key: [] for key in ("detected", "not_detected")}
    far_collection: dict[str, dict[str, Any]] = {}
    baseline_collection: dict[str, dict[str, Any]] = {}
    both_incorrect = 0
    for sample_id in sorted(expected_ids):
        task = tasks[sample_id]
        recall = correct_document_recall(far_predictions[sample_id], correct_ids[sample_id])
        retrieval_groups[retrieval_stratum(recall)].append(sample_id)
        detected = bool(_conflict_types(far_predictions[sample_id]))
        conflict_groups["detected" if detected else "not_detected"].append(sample_id)
        far_metric = collection_score(
            str(far_predictions[sample_id].get("answer", "")),
            [str(item) for item in task["gold_answers"]],
            [str(item) for item in task["wrong_answers"]],
        )
        baseline_metric = collection_score(
            str(baseline_predictions[sample_id].get("answer", "")),
            [str(item) for item in task["gold_answers"]],
            [str(item) for item in task["wrong_answers"]],
        )
        far_collection[sample_id] = {
            "sample_id": sample_id,
            "category": task["category"],
            "collection_f1": far_metric["f1"],
        }
        baseline_collection[sample_id] = {
            "sample_id": sample_id,
            "category": task["category"],
            "collection_f1": baseline_metric["f1"],
        }
        per_sample_signals[sample_id] = {
            "correct_document_recall": recall,
            "conflict_detected": detected,
        }
        if (
            float(far_scores[sample_id]["ramdocs_exact_match"]) == 0.0
            and float(baseline_scores[sample_id]["ramdocs_exact_match"]) == 0.0
        ):
            both_incorrect += 1
            bucket, signals = classify_failure(
                task=task,
                far_score=far_scores[sample_id],
                far_prediction=far_predictions[sample_id],
                correct_document_ids=correct_ids[sample_id],
            )
            buckets.append(
                {
                    "sample_id": sample_id,
                    "category": task["category"],
                    "primary_bucket": bucket,
                    "signals": signals,
                }
            )
    if both_incorrect != 226 or len(buckets) != 226:
        raise ValueError("frozen F5 both-incorrect count changed")

    stratified: dict[str, Any] = {
        "schema_version": "far-ws1-stratified-analysis-v1",
        "samples": 350,
        "correct_document_availability": {
            "available": sum(bool(ids) for ids in correct_ids.values()),
            "unavailable": sum(not ids for ids in correct_ids.values()),
        },
        "retrieval": {
            key: _paired_summary(
                ids,
                baseline_scores,
                far_scores,
                "ramdocs_exact_match",
                resamples=resamples,
                seed=seed,
            )
            for key, ids in retrieval_groups.items()
        },
        "conflict_detection": {
            key: _paired_summary(
                ids,
                baseline_scores,
                far_scores,
                "ramdocs_exact_match",
                resamples=resamples,
                seed=seed,
            )
            for key, ids in conflict_groups.items()
        },
        "descriptive_collection_f1": _paired_summary(
            sorted(expected_ids),
            baseline_collection,
            far_collection,
            "collection_f1",
            resamples=resamples,
            seed=seed,
        ),
        "collection_f1_is_gate": False,
        "publication_gold": False,
        "test_accessed": False,
    }

    dev_scores, dev_predictions, dispositions, dev_sources = _load_dev_components(
        solo_suite_dir,
        machine_rows_path,
    )
    components = component_attribution(dev_scores, dev_predictions, dispositions)
    ramdocs_distribution = conflict_type_distribution(far_predictions)
    dev_distribution = components["far_conflict_distribution"]
    variation = total_variation(
        ramdocs_distribution["distribution"],
        dev_distribution["distribution"],
    )
    complete = stratified["retrieval"]["complete"]
    detected = stratified["conflict_detection"]["detected"]
    metric = stratified["descriptive_collection_f1"]
    gain_paths = components["typed_minus_untyped_gain_paths"]
    gain_samples = int(components["typed_minus_untyped_gain_samples"])

    if int(complete["samples"]) < 80:
        upstream_status = "indeterminate"
    else:
        comparison = complete["comparison"]
        upstream_status = (
            "supported"
            if float(comparison["candidate_minus_baseline"]) > 0 and float(comparison["lower"]) > 0
            else "not_supported"
        )
    if (
        int(ramdocs_distribution["detected_samples"]) < 20
        or int(dev_distribution["detected_samples"]) < 20
    ):
        conflict_status = "indeterminate"
    else:
        detected_delta = float(detected["comparison"]["candidate_minus_baseline"])
        conflict_status = (
            "supported"
            if variation >= 0.20
            and float(dev_distribution["detection_rate"])
            - float(ramdocs_distribution["detection_rate"])
            >= 0.15
            and detected_delta <= 0.0
            else "not_supported"
        )
    metric_comparison = metric["comparison"]
    metric_status = (
        "supported"
        if float(metric_comparison["candidate_minus_baseline"]) > 0
        and float(metric_comparison["lower"]) > 0
        else "not_supported"
    )
    if gain_samples < 5:
        component_status = "indeterminate"
    else:
        component_status = (
            "supported"
            if int(gain_paths["detected_no_changed_revision"]) > int(gain_paths["changed_revision"])
            else "not_supported"
        )
    hypotheses = {
        "schema_version": "far-ws1-hypotheses-v1",
        "hypotheses": {
            "H-upstream": {
                "status": upstream_status,
                "complete_retrieval_samples": complete["samples"],
                "comparison": complete["comparison"],
            },
            "H-conflict-shape": {
                "status": conflict_status,
                "total_variation": variation,
                "ramdocs": ramdocs_distribution,
                "dev": dev_distribution,
                "detected_subset_comparison": detected["comparison"],
            },
            "H-metric": {
                "status": metric_status,
                "comparison": metric_comparison,
                "descriptive_only": True,
                "reopens_gate_a": False,
            },
            "H-component": {
                "status": component_status,
                "gain_samples": gain_samples,
                "gain_paths": gain_paths,
            },
        },
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }
    source_files = {
        str(dev_tasks_path): sha256_file(dev_tasks_path),
        str(corpus_path): sha256_file(corpus_path),
        str(round_manifest_path): sha256_file(round_manifest_path),
        str(far_scores_path): sha256_file(far_scores_path),
        str(far_predictions_path): sha256_file(far_predictions_path),
        str(baseline_scores_path): sha256_file(baseline_scores_path),
        str(baseline_predictions_path): sha256_file(baseline_predictions_path),
        **dev_sources,
    }
    bucket_counts = Counter(str(row["primary_bucket"]) for row in buckets)
    return {
        "failure_buckets": buckets,
        "bucket_counts": {key: bucket_counts.get(key, 0) for key in BUCKET_PRIORITY},
        "stratified_analysis": stratified,
        "dev_component_attribution": components,
        "hypotheses": hypotheses,
        "source_files": source_files,
        "baseline_method": baseline_method,
        "resamples": resamples,
        "seed": seed,
    }


def _report_text(result: dict[str, Any]) -> str:
    hypotheses = result["hypotheses"]["hypotheses"]
    bucket_counts = result["bucket_counts"]
    component = result["dev_component_attribution"]
    lines = [
        "# FAR typed conflict control 机制归因 (WS1)",
        "",
        "> 本报告是冻结 dev 制品的零模型调用重分析；不是新金标、真人 IAA、盲测或 G-A 重开。",
        "",
        "## RAMDocs 共同错误的最早失败阶段",
        "",
        "| 主桶 | 数量 |",
        "|---|---:|",
    ]
    lines.extend(f"| `{key}` | {bucket_counts[key]} |" for key in BUCKET_PRIORITY)
    availability = result["stratified_analysis"]["correct_document_availability"]
    lines.extend(
        [
            "",
            "- 上游正确文档可用性: "
            f"available={availability['available']}, unavailable={availability['unavailable']}；"
            "无正确文档题按注册的最早上游失败规则进入 `retrieval_miss`。",
        ]
    )
    if int(bucket_counts["format_em_mismatch"]) > 0:
        lines.extend(
            [
                "",
                "**评分不变量报警: `format_em_mismatch` 非零；这些样本必须逐条披露，"
                "不得静默并入其他桶。**",
            ]
        )
    lines.extend(["", "## 预注册假设结论", "", "| 假设 | 状态 |", "|---|---|"])
    lines.extend(f"| {key} | `{hypotheses[key]['status']}` |" for key in HYPOTHESIS_IDS)
    lines.extend(
        [
            "",
            "## dev 组件归因",
            "",
            "- typed 相对 untyped 的正向连续分数样本: "
            f"{component['typed_minus_untyped_gain_samples']}。",
            "- 增益路径: "
            + ", ".join(
                f"{key}={value}"
                for key, value in component["typed_minus_untyped_gain_paths"].items()
            )
            + "。",
            "- 五臂翻转以 answer_correctness ≥0.8 定义样本正确；连续分数差同时保留。",
            "",
            "## 适用前提",
            "",
            "1. 相关正确证据必须先被检索到；typed control 不能修复零正确文档的检索结果。",
            "2. 冲突形态必须能映射到结构化类型并被检测；不同冲突分布需单独披露。",
            "3. 检出后的修订策略不能抵消检测/查询阶段收益；detection 与 revision 必须分开评估。",
            "4. 全集合 strict 判分与描述性 partial credit 必须并列报告，但后者不得追溯性改写门禁。",
            "",
            "## 结论边界",
            "",
            "这些结论只刻画机器审计 dev 与 upstream-labelled RAMDocs dev 的机制边界。"
            "它们不支持端到端普遍优势、真人金标、外部盲测或多模型泛化声明。",
            "",
        ]
    )
    return "\n".join(lines)


def build_bundle(
    *,
    ramdocs_data_dir: Path,
    round1_dir: Path,
    round2_dir: Path,
    solo_suite_dir: Path,
    machine_rows_path: Path,
    output_dir: Path,
    report_path: Path,
    analysis_freeze_commit: str,
    resamples: int = 2000,
    seed: int = 1729,
) -> dict[str, Any]:
    roadmap = verify_active_roadmap()
    freeze = verify_analysis_freeze(analysis_freeze_commit)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"{output_dir} already exists; WS1 v1 is single-build")
    result = compute_attribution(
        ramdocs_data_dir=ramdocs_data_dir,
        round1_dir=round1_dir,
        round2_dir=round2_dir,
        solo_suite_dir=solo_suite_dir,
        machine_rows_path=machine_rows_path,
        resamples=resamples,
        seed=seed,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    write_jsonl(output_dir / "failure_buckets.jsonl", result["failure_buckets"])
    write_json(output_dir / "stratified_analysis.json", result["stratified_analysis"])
    write_json(
        output_dir / "dev_component_attribution.json",
        result["dev_component_attribution"],
    )
    write_json(output_dir / "hypotheses.json", result["hypotheses"])
    report = _report_text(result)
    (output_dir / "mechanism_attribution.md").write_text(report, encoding="utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    artifact_names = (
        "failure_buckets.jsonl",
        "stratified_analysis.json",
        "dev_component_attribution.json",
        "hypotheses.json",
        "mechanism_attribution.md",
    )
    manifest = {
        "schema_version": "far-ws1-attribution-release-v1",
        "roadmap_fingerprint": roadmap,
        "analysis_freeze": freeze,
        "split": "dev",
        "ramdocs_samples": 350,
        "both_incorrect_samples": 226,
        "bucket_priority": list(BUCKET_PRIORITY),
        "bucket_counts": result["bucket_counts"],
        "hypothesis_statuses": {
            key: result["hypotheses"]["hypotheses"][key]["status"] for key in HYPOTHESIS_IDS
        },
        "baseline_method": result["baseline_method"],
        "statistics": {"resamples": resamples, "seed": seed},
        "source_fingerprints": dict(sorted(result["source_files"].items())),
        "artifacts": {name: sha256_file(output_dir / name) for name in artifact_names},
        "external_report_sha256": sha256_file(report_path),
        "gate_r1_passed": True,
        "model_calls": 0,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
        "reopens_gate_a": False,
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ramdocs-data-dir", type=Path, default=Path("bench/external/ramdocs_v1"))
    parser.add_argument("--round1-dir", type=Path, default=Path("diagnostics/ramdocs_v2/round1"))
    parser.add_argument("--round2-dir", type=Path, default=Path("diagnostics/ramdocs_v2/round2"))
    parser.add_argument(
        "--solo-suite-dir",
        type=Path,
        default=Path("diagnostics/solo_v1/experiments"),
    )
    parser.add_argument(
        "--machine-rows",
        type=Path,
        default=Path("diagnostics/solo_v1/machine_annotation/machine_consensus_rows.jsonl"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("diagnostics/attribution_v1"))
    parser.add_argument("--report", type=Path, default=Path("reports/mechanism_attribution.md"))
    parser.add_argument("--analysis-freeze-commit", required=True)
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1729)
    args = parser.parse_args()
    manifest = build_bundle(
        ramdocs_data_dir=args.ramdocs_data_dir,
        round1_dir=args.round1_dir,
        round2_dir=args.round2_dir,
        solo_suite_dir=args.solo_suite_dir,
        machine_rows_path=args.machine_rows,
        output_dir=args.output_dir,
        report_path=args.report,
        analysis_freeze_commit=args.analysis_freeze_commit,
        resamples=args.resamples,
        seed=args.seed,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
