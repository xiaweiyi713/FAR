"""Score one prediction file with provenance, confidence intervals, and paired tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from eval.metrics import PredictionRecord, aggregate_scores, score_sample
from eval.stats import (
    dependency_cluster_bootstrap_ci,
    mcnemar_exact,
    paired_bootstrap_comparison,
    stratified_bootstrap_ci,
)


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
    aggregate = aggregate_scores(scores)
    interval_metrics = (
        "answer_correctness",
        "unsupported_claim_rate",
        "evidence_precision",
        "counter_evidence_recall",
        "typed_conflict_correct",
        "revision_accuracy",
        "overclaim_reduction",
    )
    intervals = {
        metric: stratified_bootstrap_ci(
            scores,
            metric,
            resamples=resamples,
            seed=seed,
        )
        for metric in interval_metrics
        if any(row.get(metric) is not None for row in scores)
    }
    dependency_intervals = {
        metric: dependency_cluster_bootstrap_ci(
            scores,
            metric,
            resamples=resamples,
            seed=seed,
        )
        for metric in interval_metrics
        if any(row.get(metric) is not None for row in scores)
    }
    comparison = None
    if baseline_scores_path is not None:
        baseline_scores = read_jsonl(baseline_scores_path)
        comparison = {
            metric: paired_bootstrap_comparison(
                baseline_scores,
                scores,
                metric,
                resamples=resamples,
                seed=seed,
            )
            for metric in ("answer_correctness", "revision_accuracy")
        }
        baseline_by_id = {row["sample_id"]: row for row in baseline_scores}
        score_by_id = {row["sample_id"]: row for row in scores}
        ordered_ids = sorted(score_by_id)
        comparison["revision_accuracy_mcnemar"] = mcnemar_exact(
            [bool(baseline_by_id[item]["revision_accuracy"]) for item in ordered_ids],
            [bool(score_by_id[item]["revision_accuracy"]) for item in ordered_ids],
        )
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
        "aggregate": aggregate,
        "confidence_intervals": intervals,
        "dependency_cluster_intervals": dependency_intervals,
        "comparison": comparison,
        "provenance": {
            "benchmark_sha256": sha256_file(benchmark_path),
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
