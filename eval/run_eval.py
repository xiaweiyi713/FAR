"""Score one prediction file with provenance, confidence intervals, and paired tests."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from eval.metrics import PredictionRecord, aggregate_scores, score_sample
from eval.stats import (
    dependency_cluster_bootstrap_ci,
    dependency_cluster_typed_conflict_f1_ci,
    mcnemar_exact,
    paired_bootstrap_comparison,
    paired_typed_conflict_f1_comparison,
    stratified_bootstrap_ci,
    stratified_typed_conflict_f1_ci,
)

ROW_METRICS = (
    "answer_correctness",
    "answer_exact_match",
    "unsupported_claim_rate",
    "evidence_precision",
    "evidence_recall",
    "counter_evidence_recall",
    "conflict_detected",
    "typed_conflict_correct",
    "revision_action_correct",
    "revision_accuracy",
    "overclaim_reduction",
)

BINARY_SUCCESS_METRICS = (
    "answer_exact_match",
    "conflict_detected",
    "typed_conflict_correct",
    "revision_action_correct",
    "revision_accuracy",
)


def _publication_context(
    benchmark_path: Path,
    samples: dict[str, dict[str, Any]],
    predictions: list[PredictionRecord],
) -> dict[str, Any]:
    manifest_path = benchmark_path.parent / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    )
    annotation_counts = Counter(
        str(samples[item.sample_id].get("annotation_status", "missing")) for item in predictions
    )
    manifest_ready = bool(manifest and manifest.get("publication_ready"))
    rows_adjudicated = bool(annotation_counts) and set(annotation_counts) == {"adjudicated"}
    reasons = []
    if manifest is None:
        reasons.append("benchmark manifest is missing")
    elif not manifest_ready:
        reasons.append("benchmark manifest is not publication-ready")
    if not rows_adjudicated:
        reasons.append("scored rows are not all adjudicated")
    return {
        "ready": manifest_ready and rows_adjudicated,
        "benchmark_manifest": str(manifest_path) if manifest_path.exists() else None,
        "benchmark_manifest_sha256": (
            sha256_file(manifest_path) if manifest_path.exists() else None
        ),
        "annotation_status_counts": dict(sorted(annotation_counts.items())),
        "reasons": reasons,
    }


def _validate_comparison_input(
    baseline_scores_path: Path,
    baseline_scores: list[dict[str, Any]],
    candidate_scores: list[dict[str, Any]],
    *,
    benchmark_sha256: str,
) -> tuple[str, str]:
    if not baseline_scores:
        raise ValueError("baseline score file must not be empty")
    baseline_ids = [str(row["sample_id"]) for row in baseline_scores]
    candidate_ids = [str(row["sample_id"]) for row in candidate_scores]
    if len(set(baseline_ids)) != len(baseline_ids):
        raise ValueError("baseline score file contains duplicate sample IDs")
    if set(baseline_ids) != set(candidate_ids):
        raise ValueError("baseline and candidate scores must contain identical sample IDs")
    baseline_by_id = {str(row["sample_id"]): row for row in baseline_scores}
    candidate_by_id = {str(row["sample_id"]): row for row in candidate_scores}
    for sample_id in sorted(baseline_by_id):
        for field in ("category", "split", "dependency_group"):
            if baseline_by_id[sample_id].get(field) != candidate_by_id[sample_id].get(field):
                raise ValueError(f"comparison metadata mismatch for {sample_id}: {field}")
    baseline_methods = {str(row["method"]) for row in baseline_scores}
    candidate_methods = {str(row["method"]) for row in candidate_scores}
    if len(baseline_methods) != 1 or len(candidate_methods) != 1:
        raise ValueError("comparison score files must each contain exactly one method")

    baseline_report_path = baseline_scores_path.parent / "report.json"
    if not baseline_report_path.exists():
        raise ValueError("baseline scores require a sibling fingerprint-bound report.json")
    baseline_report = json.loads(baseline_report_path.read_text(encoding="utf-8"))
    provenance = baseline_report.get("provenance", {})
    if provenance.get("scores_sha256") != sha256_file(baseline_scores_path):
        raise ValueError("baseline report scores fingerprint mismatch")
    if provenance.get("benchmark_sha256") != benchmark_sha256:
        raise ValueError("baseline report was evaluated against a different benchmark")
    return next(iter(baseline_methods)), next(iter(candidate_methods))


def evaluate(
    benchmark_path: Path,
    predictions_path: Path,
    output_dir: Path,
    *,
    resamples: int = 2000,
    seed: int = 1729,
    baseline_scores_path: Path | None = None,
) -> dict[str, Any]:
    samples = {row["id"]: row for row in read_jsonl(benchmark_path)}
    prediction_rows = read_jsonl(predictions_path)
    predictions = [PredictionRecord.from_dict(row) for row in prediction_rows]
    if len({item.sample_id for item in predictions}) != len(predictions):
        raise ValueError("prediction IDs must be unique")
    unknown = {item.sample_id for item in predictions} - set(samples)
    if unknown:
        raise ValueError(f"predictions contain unknown sample IDs: {sorted(unknown)}")
    methods = {item.method for item in predictions}
    if len(methods) != 1:
        raise ValueError("one evaluation report may contain exactly one method")
    scores = [score_sample(samples[item.sample_id], item) for item in predictions]
    publication = _publication_context(benchmark_path, samples, predictions)
    aggregate = aggregate_scores(scores)
    intervals = {
        metric: stratified_bootstrap_ci(
            scores,
            metric,
            resamples=resamples,
            seed=seed,
        )
        for metric in ROW_METRICS
        if any(row.get(metric) is not None for row in scores)
    }
    intervals["typed_conflict_f1"] = stratified_typed_conflict_f1_ci(
        scores,
        resamples=resamples,
        seed=seed,
    )
    dependency_intervals = {
        metric: dependency_cluster_bootstrap_ci(
            scores,
            metric,
            resamples=resamples,
            seed=seed,
        )
        for metric in ROW_METRICS
        if any(row.get(metric) is not None for row in scores)
    }
    dependency_intervals["typed_conflict_f1"] = dependency_cluster_typed_conflict_f1_ci(
        scores,
        resamples=resamples,
        seed=seed,
    )
    comparison = None
    if baseline_scores_path is not None:
        baseline_scores = read_jsonl(baseline_scores_path)
        benchmark_fingerprint = sha256_file(benchmark_path)
        baseline_method, candidate_method = _validate_comparison_input(
            baseline_scores_path,
            baseline_scores,
            scores,
            benchmark_sha256=benchmark_fingerprint,
        )
        paired_metrics = {
            metric: paired_bootstrap_comparison(
                baseline_scores,
                scores,
                metric,
                resamples=resamples,
                seed=seed,
                higher_is_better=metric != "unsupported_claim_rate",
            )
            for metric in ROW_METRICS
            if any(
                baseline_row.get(metric) is not None and candidate_row.get(metric) is not None
                for baseline_row, candidate_row in zip(
                    sorted(baseline_scores, key=lambda row: str(row["sample_id"])),
                    sorted(scores, key=lambda row: str(row["sample_id"])),
                    strict=True,
                )
            )
        }
        paired_metrics["typed_conflict_f1"] = paired_typed_conflict_f1_comparison(
            baseline_scores,
            scores,
            resamples=resamples,
            seed=seed,
        )
        baseline_by_id = {row["sample_id"]: row for row in baseline_scores}
        score_by_id = {row["sample_id"]: row for row in scores}
        ordered_ids = sorted(score_by_id)
        comparison = {
            "baseline_method": baseline_method,
            "candidate_method": candidate_method,
            "baseline_scores_sha256": sha256_file(baseline_scores_path),
            "metrics": paired_metrics,
            "mcnemar": {
                metric: mcnemar_exact(
                    [bool(baseline_by_id[item][metric]) for item in ordered_ids],
                    [bool(score_by_id[item][metric]) for item in ordered_ids],
                )
                for metric in BINARY_SUCCESS_METRICS
            },
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    scores_path = output_dir / "scores.jsonl"
    write_jsonl(scores_path, scores)
    run_manifest_path = predictions_path.parent / "run_manifest.json"
    run_manifest = (
        json.loads(run_manifest_path.read_text(encoding="utf-8"))
        if run_manifest_path.exists()
        else None
    )
    report = {
        "schema_version": "falsirag-evaluation-report-v1",
        "method": next(iter(methods)),
        "samples": len(scores),
        "split_counts": aggregate.get("by_category")
        and {key: sum(row["split"] == key for row in scores) for key in ("train", "dev", "test")},
        "partial": bool(run_manifest and run_manifest.get("partial")),
        "publication_ready": publication["ready"],
        "publication": publication,
        "aggregate": aggregate,
        "confidence_intervals": intervals,
        "dependency_cluster_intervals": dependency_intervals,
        "comparison": comparison,
        "provenance": {
            "benchmark_sha256": sha256_file(benchmark_path),
            "benchmark_manifest_sha256": publication["benchmark_manifest_sha256"],
            "predictions_sha256": sha256_file(predictions_path),
            "scores_sha256": sha256_file(scores_path),
            "run_signature": run_manifest.get("run_signature") if run_manifest else None,
        },
    }
    write_json(output_dir / "report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--baseline-scores", type=Path)
    args = parser.parse_args()
    report = evaluate(
        args.benchmark,
        args.predictions,
        args.output_dir,
        resamples=args.resamples,
        seed=args.seed,
        baseline_scores_path=args.baseline_scores,
    )
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
