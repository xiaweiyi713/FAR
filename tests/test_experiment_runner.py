from __future__ import annotations

from pathlib import Path

import pytest

from eval.run_eval import evaluate
from experiments.run_far import run
from experiments.run_suite import run_suite
from experiments.runner import ROOT, load_benchmark, select_samples
from experiments.validate_results import validate_result_bundle


def test_sample_limit_is_category_balanced_and_test_is_guarded() -> None:
    samples, _ = load_benchmark(ROOT / "bench")
    selected = select_samples(samples, "dev", limit=10, allow_test=False)
    assert {row["category"] for row in selected} == {
        "temporal_shift",
        "numerical_conflict",
        "entity_confusion",
        "causal_overclaim",
        "multi_source_conflict",
    }
    with pytest.raises(ValueError, match="allow-test"):
        select_samples(samples, "test", limit=1, allow_test=False)


def test_runner_resumes_without_duplicates_and_evaluation_is_bound(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config = ROOT / "experiments/configs/offline_smoke.yaml"
    first = run(config, ROOT / "bench", run_dir, limit=5)
    second = run(config, ROOT / "bench", run_dir, limit=5)
    assert first["predictions_sha256"] == second["predictions_sha256"]
    assert first["completed"] == 5
    evaluation_dir = tmp_path / "evaluation"
    evaluate(
        ROOT / "bench/falsirag_bench.jsonl",
        run_dir / "predictions.jsonl",
        evaluation_dir,
        resamples=20,
    )
    assert validate_result_bundle(run_dir, evaluation_dir)["valid"] is True


def test_suite_runs_far_baseline_ablation_and_artifacts(tmp_path: Path) -> None:
    manifest = run_suite(
        ROOT / "experiments/configs/offline_smoke.yaml",
        ROOT / "bench",
        tmp_path / "suite",
        limit=5,
        baselines=("vanilla_rag",),
        ablations=("minus_typed_conflict",),
        resamples=20,
    )
    assert manifest["diagnostic_only"] is True
    assert manifest["methods"] == ["far", "minus_typed_conflict", "vanilla"]
    assert (tmp_path / "suite" / "suite_manifest.json").exists()
    assert (tmp_path / "suite" / "artifacts" / "main_results.csv").exists()
    assert (tmp_path / "suite" / "artifacts" / "ablation_results.csv").exists()
