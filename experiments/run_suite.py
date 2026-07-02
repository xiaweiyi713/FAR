"""Run a complete FAR experiment suite for one config and split."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.build.common import sha256_file, write_json
from eval.run_eval import evaluate
from experiments.ablations import ABLATION_NAMES
from experiments.build_artifacts import build as build_artifacts
from experiments.run_baselines import BASELINE_NAMES
from experiments.run_baselines import run as run_baselines
from experiments.run_far import run as run_far
from experiments.runner import ROOT
from experiments.validate_results import validate_result_bundle

DEFAULT_ABLATIONS = tuple(name for name in ABLATION_NAMES if name != "full")


def _load_existing_run(
    run_dir: Path,
    *,
    expected_method: str,
    config_path: Path,
    data_dir: Path,
    split: str | None,
    limit: int | None,
) -> dict[str, Any]:
    manifest_path = run_dir / "run_manifest.json"
    identity_path = run_dir / "run_identity.json"
    if not manifest_path.is_file() or not identity_path.is_file():
        raise FileNotFoundError(f"reports-only run is incomplete: {run_dir}")
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    identity: dict[str, Any] = json.loads(identity_path.read_text(encoding="utf-8"))
    expected_split = split or str(manifest.get("split", ""))
    checks = {
        "status": manifest.get("status") == "complete",
        "method": manifest.get("method") == expected_method == identity.get("method"),
        "split": manifest.get("split") == expected_split == identity.get("split"),
        "limit": identity.get("limit") == limit,
        "partial": bool(manifest.get("partial")) == (limit is not None),
        "signature": manifest.get("run_signature") == identity.get("run_signature"),
        "config": identity.get("config_sha256") == sha256_file(config_path),
        "benchmark": identity.get("benchmark_input_sha256")
        == sha256_file(
            data_dir
            / ("splits/test_inputs.jsonl" if expected_split == "test" else "falsirag_bench.jsonl")
        ),
        "corpus": identity.get("corpus_sha256") == sha256_file(data_dir / "corpus.jsonl"),
    }
    failed = sorted(key for key, passed in checks.items() if not passed)
    if failed:
        raise ValueError(f"reports-only run identity mismatch for {run_dir}: {failed}")
    return manifest


def _evaluate_and_validate(
    benchmark_path: Path,
    run_dir: Path,
    evaluation_dir: Path,
    *,
    resamples: int,
    seed: int,
    baseline_scores_path: Path | None = None,
) -> dict[str, Any]:
    report = evaluate(
        benchmark_path,
        run_dir / "predictions.jsonl",
        evaluation_dir,
        resamples=resamples,
        seed=seed,
        baseline_scores_path=baseline_scores_path,
    )
    validation = validate_result_bundle(run_dir, evaluation_dir)
    if not validation["valid"]:
        raise RuntimeError(f"{run_dir}: invalid result bundle: {validation['errors']}")
    return report


def run_suite(
    config_path: Path,
    data_dir: Path,
    output_dir: Path,
    *,
    split: str | None = None,
    limit: int | None = None,
    allow_test: bool = False,
    baselines: tuple[str, ...] = BASELINE_NAMES,
    ablations: tuple[str, ...] = DEFAULT_ABLATIONS,
    resamples: int = 2000,
    seed: int = 1729,
    reports_only: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    benchmark_path = data_dir / "falsirag_bench.jsonl"
    runs_dir = output_dir / "runs"
    evaluations_dir = output_dir / "evaluations"

    if reports_only:
        far_manifest = _load_existing_run(
            runs_dir / "far",
            expected_method="far",
            config_path=config_path,
            data_dir=data_dir,
            split=split,
            limit=limit,
        )
        run_manifests: dict[str, dict[str, Any]] = {"far": far_manifest}
        for ablation in ablations:
            if ablation == "full":
                continue
            run_manifests[ablation] = _load_existing_run(
                runs_dir / ablation,
                expected_method=f"far_{ablation}",
                config_path=config_path,
                data_dir=data_dir,
                split=split,
                limit=limit,
            )
        baseline_manifests = [
            _load_existing_run(
                runs_dir / "baselines" / baseline,
                expected_method=baseline,
                config_path=config_path,
                data_dir=data_dir,
                split=split,
                limit=limit,
            )
            for baseline in baselines
        ]
    else:
        far_manifest = run_far(
            config_path,
            data_dir,
            runs_dir / "far",
            split=split,
            limit=limit,
            allow_test=allow_test,
        )
        run_manifests = {"far": far_manifest}
        for ablation in ablations:
            if ablation == "full":
                continue
            manifest = run_far(
                config_path,
                data_dir,
                runs_dir / ablation,
                ablation=ablation,
                split=split,
                limit=limit,
                allow_test=allow_test,
            )
            run_manifests[ablation] = manifest

        baseline_manifests = run_baselines(
            config_path,
            data_dir,
            runs_dir / "baselines",
            methods=baselines,
            split=split,
            limit=limit,
            allow_test=allow_test,
        )
    for manifest in baseline_manifests:
        run_manifests[str(manifest["method"])] = manifest

    if far_manifest["split"] == "test":
        blind_input_path = data_dir / "splits" / "test_inputs.jsonl"
        manifest = {
            "schema_version": "far-blind-suite-manifest-v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "config": str(config_path),
            "config_sha256": sha256_file(config_path),
            "blind_input_sha256": sha256_file(blind_input_path),
            "corpus_sha256": sha256_file(data_dir / "corpus.jsonl"),
            "split": "test",
            "limit": limit,
            "allow_test": allow_test,
            "unscored": True,
            "gold_loaded": False,
            "diagnostic_only": limit is not None,
            "reports_only": reports_only,
            "methods": sorted(run_manifests),
            "run_manifests": {
                label: {
                    "method": run_manifest["method"],
                    "run_signature": run_manifest["run_signature"],
                    "predictions_sha256": run_manifest["predictions_sha256"],
                    "completed": run_manifest["completed"],
                    "partial": run_manifest["partial"],
                }
                for label, run_manifest in sorted(run_manifests.items())
            },
            "reports": {},
            "artifact_manifest": None,
        }
        write_json(output_dir / "suite_manifest.json", manifest)
        return manifest

    reports: dict[str, Path] = {}
    far_report = _evaluate_and_validate(
        benchmark_path,
        runs_dir / "far",
        evaluations_dir / "far",
        resamples=resamples,
        seed=seed,
    )
    reports["far"] = evaluations_dir / "far" / "report.json"
    far_score_path = evaluations_dir / "far" / "scores.jsonl"

    baseline_score_path: Path | None = None
    if "vanilla_rag" in baselines:
        vanilla_report = _evaluate_and_validate(
            benchmark_path,
            runs_dir / "baselines" / "vanilla_rag",
            evaluations_dir / "vanilla_rag",
            resamples=resamples,
            seed=seed,
        )
        del vanilla_report
        reports["vanilla"] = evaluations_dir / "vanilla_rag" / "report.json"
        baseline_score_path = evaluations_dir / "vanilla_rag" / "scores.jsonl"

    for baseline in baselines:
        if baseline == "vanilla_rag":
            continue
        _evaluate_and_validate(
            benchmark_path,
            runs_dir / "baselines" / baseline,
            evaluations_dir / baseline,
            resamples=resamples,
            seed=seed,
            baseline_scores_path=baseline_score_path,
        )
        reports[baseline] = evaluations_dir / baseline / "report.json"

    # Re-evaluate FAR against vanilla when possible so paired comparison is present.
    if baseline_score_path is not None:
        far_report = _evaluate_and_validate(
            benchmark_path,
            runs_dir / "far",
            evaluations_dir / "far",
            resamples=resamples,
            seed=seed,
            baseline_scores_path=baseline_score_path,
        )

    for ablation in ablations:
        if ablation == "full":
            continue
        _evaluate_and_validate(
            benchmark_path,
            runs_dir / ablation,
            evaluations_dir / ablation,
            resamples=resamples,
            seed=seed,
            baseline_scores_path=far_score_path,
        )
        reports[ablation] = evaluations_dir / ablation / "report.json"

    artifact_manifest = build_artifacts(
        reports,
        {"far": runs_dir / "far" / "predictions.jsonl"},
        output_dir / "artifacts",
        overwrite=True,
    )
    manifest = {
        "schema_version": "far-suite-manifest-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "benchmark_sha256": sha256_file(benchmark_path),
        "split": far_manifest["split"],
        "limit": limit,
        "allow_test": allow_test,
        "diagnostic_only": bool(limit is not None) or bool(artifact_manifest["diagnostic_only"]),
        "reports_only": reports_only,
        "methods": sorted(reports),
        "run_manifests": {
            label: {
                "method": manifest["method"],
                "run_signature": manifest["run_signature"],
                "predictions_sha256": manifest["predictions_sha256"],
                "completed": manifest["completed"],
                "partial": manifest["partial"],
            }
            for label, manifest in sorted(run_manifests.items())
        },
        "reports": {label: sha256_file(path) for label, path in sorted(reports.items())},
        "artifact_manifest": sha256_file(output_dir / "artifacts" / "artifact_manifest.json"),
        "far_summary": far_report["aggregate"]["metrics"],
    }
    write_json(output_dir / "suite_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "experiments/configs/offline_smoke.yaml",
    )
    parser.add_argument("--data-dir", type=Path, default=ROOT / "bench")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "dev", "test"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--allow-test", action="store_true")
    parser.add_argument("--baseline", choices=BASELINE_NAMES, action="append")
    parser.add_argument("--ablation", choices=ABLATION_NAMES, action="append")
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument(
        "--reports-only",
        action="store_true",
        help="validate existing prediction runs and rebuild reports/artifacts without inference",
    )
    args = parser.parse_args()
    selected_ablations = tuple(args.ablation or DEFAULT_ABLATIONS)
    selected_baselines = tuple(args.baseline or BASELINE_NAMES)
    manifest = run_suite(
        args.config,
        args.data_dir,
        args.output_dir,
        split=args.split,
        limit=args.limit,
        allow_test=args.allow_test,
        baselines=selected_baselines,
        ablations=selected_ablations,
        resamples=args.resamples,
        seed=args.seed,
        reports_only=args.reports_only,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
