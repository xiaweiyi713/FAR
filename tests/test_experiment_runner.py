from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from bench.build.build_blind_bundle import build as build_blind_bundle
from eval.run_eval import evaluate
from experiments.build_artifacts import _load_plotting_backend
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
    far_report = json.loads(
        (tmp_path / "suite/evaluations/far/report.json").read_text(encoding="utf-8")
    )
    ablation_report = json.loads(
        (tmp_path / "suite/evaluations/minus_typed_conflict/report.json").read_text(
            encoding="utf-8"
        )
    )
    assert far_report["comparison"]["baseline_method"] == "vanilla_rag"
    assert far_report["comparison"]["candidate_method"] == "far"
    assert ablation_report["comparison"]["baseline_method"] == "far"
    assert ablation_report["comparison"]["candidate_method"] == "far_minus_typed_conflict"
    assert "typed_conflict_f1" in ablation_report["comparison"]["metrics"]
    assert "typed_conflict_f1" in ablation_report["confidence_intervals"]


def test_blind_test_suite_runs_without_loading_or_scoring_gold(tmp_path: Path) -> None:
    data_dir = tmp_path / "blind-data"
    build_blind_bundle(ROOT / "bench", data_dir)
    output_dir = tmp_path / "blind-suite"
    manifest = run_suite(
        ROOT / "experiments/configs/offline_smoke.yaml",
        data_dir,
        output_dir,
        split="test",
        limit=5,
        allow_test=True,
        baselines=("vanilla_rag",),
        ablations=(),
        resamples=20,
    )
    assert manifest["schema_version"] == "far-blind-suite-manifest-v1"
    assert manifest["unscored"] is True
    assert manifest["gold_loaded"] is False
    assert manifest["methods"] == ["far", "vanilla_rag"]
    assert not (data_dir / "falsirag_bench.jsonl").exists()
    assert not (output_dir / "evaluations").exists()
    assert not (output_dir / "artifacts").exists()
    identity = json.loads((output_dir / "runs/far/run_identity.json").read_text(encoding="utf-8"))
    assert identity["benchmark_input"] == "splits/test_inputs.jsonl"
    assert identity["schema_version"] == "far-run-signature-v2"


def test_artifact_builder_explains_missing_eval_extra() -> None:
    with (
        patch(
            "experiments.build_artifacts.importlib.import_module",
            side_effect=ModuleNotFoundError("No module named 'matplotlib'"),
        ),
        pytest.raises(RuntimeError, match="optional eval dependencies"),
    ):
        _load_plotting_backend()
