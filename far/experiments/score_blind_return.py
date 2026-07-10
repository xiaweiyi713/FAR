"""Validate and score one externally returned blind-test suite exactly once."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from far.bench.annotations import validate_annotation_evidence
from far.bench.build.common import read_jsonl, sha256_file, write_json
from far.bench.build.validate_bench import validate as validate_benchmark
from far.eval.run_eval import evaluate
from far.experiments.build_artifacts import build as build_artifacts
from far.experiments.submission_readiness import (
    BLIND_METHODS,
    MODEL_SPECS,
    REPORT_METHODS,
    ROOT,
    _json,
    _reject_template_path,
    _run_dir,
    _source_commit,
    _validate_identity_binding,
)
from far.experiments.validate_results import validate_result_bundle


def _validate_annotation(data_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    report = _json(data_dir / "annotation_report.json")
    manifest = _json(data_dir / "manifest.json")
    rows = read_jsonl(data_dir / "falsirag_bench.jsonl")
    validation = validate_benchmark(data_dir)
    validate_annotation_evidence(data_dir)
    if report.get("adjudicated") is not True or report.get("agreement_gate_passed") is not True:
        raise ValueError("adjudicated annotation and kappa gates must pass before test scoring")
    if not str(report.get("adjudicator_id", "")).strip():
        raise ValueError("annotation report has no adjudicator ID")
    if not rows or any(row.get("annotation_status") != "adjudicated" for row in rows):
        raise ValueError("test scoring data contains non-adjudicated rows")
    annotators = report.get("annotators")
    kappas = report.get("mean_kappas")
    if not isinstance(annotators, list) or len(set(map(str, annotators))) < 2:
        raise ValueError("annotation report has fewer than two distinct reviewers")
    if not isinstance(kappas, dict) or not kappas or min(map(float, kappas.values())) < 0.6:
        raise ValueError("annotation report has a mean kappa below 0.60")
    if not validation["candidate_ready"]:
        raise ValueError(f"adjudicated benchmark validation failed: {validation['errors']}")
    return report, manifest


def _validate_attestation(
    attestation: dict[str, Any],
    *,
    model_id: str,
    bundle_manifest_sha: str,
    return_manifest_sha: str,
    frozen_commit: str,
) -> None:
    if attestation.get("schema_version") != "far-blind-test-attestation-v1":
        raise ValueError("unsupported blind-test attestation schema")
    custodian = str(attestation.get("custodian_id", "")).strip()
    scorer = str(attestation.get("scorer_id", "")).strip()
    if not custodian or not scorer or custodian == scorer:
        raise ValueError("custodian and trusted scorer must be distinct named roles")
    required = {
        "one_shot": True,
        "externally_held": True,
        "gold_loaded_by_custodian": False,
        "all_failures_reported": True,
    }
    failed = [field for field, value in required.items() if attestation.get(field) is not value]
    if failed:
        raise ValueError(f"blind-test attestation is incomplete: {failed}")
    if attestation.get("frozen_commit") != frozen_commit:
        raise ValueError("attestation and returned runs have different frozen commits")
    if attestation.get("bundle_manifest_sha256") != bundle_manifest_sha:
        raise ValueError("attestation is not bound to this blind bundle")
    returns = attestation.get("return_manifest_sha256")
    if not isinstance(returns, dict) or returns.get(model_id) != return_manifest_sha:
        raise ValueError("attestation is not bound to this model return")
    if not str(attestation.get("completed_at", "")).strip():
        raise ValueError("blind-test completion timestamp is missing")


def score(
    data_dir: Path,
    blind_bundle_dir: Path,
    return_dir: Path,
    attestation_path: Path,
    output_dir: Path,
    *,
    model_id: str,
    resamples: int = 2000,
    seed: int = 1729,
) -> dict[str, Any]:
    if model_id not in MODEL_SPECS:
        raise ValueError(f"unsupported formal model ID: {model_id}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("blind scoring output directory must be empty")
    annotation_report, source_manifest = _validate_annotation(data_dir)
    annotation_evidence_sha = str(
        source_manifest.get("annotation", {}).get("evidence_manifest_sha256", "")
    )
    bundle_manifest_path = blind_bundle_dir / "blind_bundle_manifest.json"
    bundle_manifest = _json(bundle_manifest_path)
    return_manifest_path = return_dir / "suite_manifest.json"
    return_manifest = _json(return_manifest_path)
    if bundle_manifest.get("gold_included") is not False:
        raise ValueError("handoff bundle is not gold-free")
    if return_manifest.get("schema_version") != "far-blind-suite-manifest-v1":
        raise ValueError("return directory is not a blind suite")
    bundle_rows = read_jsonl(blind_bundle_dir / "splits/test_inputs.jsonl")
    adjudicated_test_ids = {
        str(row["id"])
        for row in read_jsonl(data_dir / "falsirag_bench.jsonl")
        if row.get("split") == "test"
    }
    expected_config_sha = sha256_file(ROOT / MODEL_SPECS[model_id])
    checks = {
        "split": return_manifest.get("split") == "test",
        "unscored": return_manifest.get("unscored") is True,
        "gold": return_manifest.get("gold_loaded") is False,
        "complete": return_manifest.get("limit") is None
        and return_manifest.get("diagnostic_only") is False,
        "methods": set(return_manifest.get("methods", [])) == BLIND_METHODS,
        "input": return_manifest.get("blind_input_sha256")
        == sha256_file(blind_bundle_dir / "splits/test_inputs.jsonl"),
        "corpus": return_manifest.get("corpus_sha256")
        == sha256_file(blind_bundle_dir / "corpus.jsonl"),
        "source_corpus": bundle_manifest.get("source_corpus_sha256")
        == sha256_file(data_dir / "corpus.jsonl"),
        "bundle_count": bundle_manifest.get("samples") == len(bundle_rows),
        "test_ids": {str(row.get("id")) for row in bundle_rows} == adjudicated_test_ids,
        "config": return_manifest.get("config_sha256") == expected_config_sha,
    }
    failed = sorted(key for key, passed in checks.items() if not passed)
    if failed:
        raise ValueError(f"blind return failed checks: {failed}")
    commits: set[str] = set()
    for label in BLIND_METHODS:
        run_dir = _run_dir(return_dir, label)
        validation = validate_result_bundle(run_dir)
        if not validation["valid"]:
            raise ValueError(f"invalid returned run {label}: {validation['errors']}")
        _validate_identity_binding(
            run_dir,
            config_sha256=expected_config_sha,
            benchmark_sha256=sha256_file(blind_bundle_dir / "splits/test_inputs.jsonl"),
            corpus_sha256=sha256_file(blind_bundle_dir / "corpus.jsonl"),
            split="test",
        )
        commits.add(_source_commit(run_dir))
    if len(commits) != 1:
        raise ValueError("returned runs do not share one frozen clean commit")
    frozen_commit = next(iter(commits))
    _reject_template_path(attestation_path, "blind-test attestation")
    attestation = _json(attestation_path)
    _validate_attestation(
        attestation,
        model_id=model_id,
        bundle_manifest_sha=sha256_file(bundle_manifest_path),
        return_manifest_sha=sha256_file(return_manifest_path),
        frozen_commit=frozen_commit,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    evaluations = output_dir / "evaluations"
    final_manifest = dict(source_manifest)
    final_manifest["publication_ready"] = True
    final_manifest["publication_blockers"] = []
    final_manifest["blind_test"] = {
        "status": "completed",
        "externally_held": True,
        "one_shot": True,
        "gold_loaded_by_custodian": False,
        "custodian_id": attestation["custodian_id"],
        "scorer_id": attestation["scorer_id"],
        "completed_at": attestation["completed_at"],
        "frozen_commit": frozen_commit,
        "bundle_manifest_sha256": sha256_file(bundle_manifest_path),
        "return_manifest_sha256": sha256_file(return_manifest_path),
        "attestation_sha256": sha256_file(attestation_path),
    }
    finalized_manifest_path = output_dir / "finalized_benchmark_manifest.json"
    write_json(finalized_manifest_path, final_manifest)

    benchmark_path = data_dir / "falsirag_bench.jsonl"
    report_paths: dict[str, Path] = {}
    vanilla_run = _run_dir(return_dir, "vanilla")
    vanilla_report = evaluate(
        benchmark_path,
        vanilla_run / "predictions.jsonl",
        evaluations / "vanilla",
        resamples=resamples,
        seed=seed,
        benchmark_manifest_path=finalized_manifest_path,
    )
    del vanilla_report
    report_paths["vanilla"] = evaluations / "vanilla" / "report.json"
    vanilla_scores = evaluations / "vanilla" / "scores.jsonl"

    far_run = _run_dir(return_dir, "far")
    far_report = evaluate(
        benchmark_path,
        far_run / "predictions.jsonl",
        evaluations / "far",
        resamples=resamples,
        seed=seed,
        baseline_scores_path=vanilla_scores,
        benchmark_manifest_path=finalized_manifest_path,
    )
    report_paths["far"] = evaluations / "far" / "report.json"
    far_scores = evaluations / "far" / "scores.jsonl"

    for label in sorted(REPORT_METHODS - {"far", "vanilla"}):
        baseline = far_scores if label.startswith("minus_") else vanilla_scores
        run_dir = _run_dir(return_dir, label)
        evaluate(
            benchmark_path,
            run_dir / "predictions.jsonl",
            evaluations / label,
            resamples=resamples,
            seed=seed,
            baseline_scores_path=baseline,
            benchmark_manifest_path=finalized_manifest_path,
        )
        validation = validate_result_bundle(run_dir, evaluations / label)
        if not validation["valid"]:
            raise RuntimeError(
                f"scored returned run is invalid for {label}: {validation['errors']}"
            )
        report_paths[label] = evaluations / label / "report.json"
    for label in ("far", "vanilla"):
        validation = validate_result_bundle(_run_dir(return_dir, label), evaluations / label)
        if not validation["valid"]:
            raise RuntimeError(
                f"scored returned run is invalid for {label}: {validation['errors']}"
            )

    artifact_manifest = build_artifacts(
        report_paths,
        {"far": far_run / "predictions.jsonl"},
        output_dir / "artifacts",
        require_publication_ready=True,
        require_test_only=True,
    )
    if artifact_manifest.get("publication_ready") is not True:
        raise RuntimeError("scored blind-test artifacts are not publication-ready")
    manifest = {
        "schema_version": "far-scored-blind-suite-manifest-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_id": model_id,
        "split": "test",
        "samples": len(bundle_rows),
        "publication_ready": True,
        "frozen_commit": frozen_commit,
        "benchmark_sha256": sha256_file(benchmark_path),
        "finalized_benchmark_manifest_sha256": sha256_file(finalized_manifest_path),
        "annotation_report_sha256": sha256_file(data_dir / "annotation_report.json"),
        "annotation_evidence_manifest_sha256": annotation_evidence_sha,
        "annotation_gate_passed": annotation_report["agreement_gate_passed"],
        "blind_bundle_manifest_sha256": sha256_file(bundle_manifest_path),
        "return_suite_manifest_sha256": sha256_file(return_manifest_path),
        "attestation_sha256": sha256_file(attestation_path),
        "methods": sorted(REPORT_METHODS),
        "reports": {label: sha256_file(path) for label, path in sorted(report_paths.items())},
        "artifact_manifest_sha256": sha256_file(
            output_dir / "artifacts" / "artifact_manifest.json"
        ),
        "far_summary": far_report["aggregate"]["metrics"],
    }
    write_json(output_dir / "scored_suite_manifest.json", manifest)
    shutil.copy2(attestation_path, output_dir / "blind_test_attestation.json")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--blind-bundle-dir", type=Path, required=True)
    parser.add_argument("--return-dir", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1729)
    args = parser.parse_args()
    manifest = score(
        args.data_dir,
        args.blind_bundle_dir,
        args.return_dir,
        args.attestation,
        args.output_dir,
        model_id=args.model_id,
        resamples=args.resamples,
        seed=args.seed,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
