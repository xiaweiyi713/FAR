"""Independently verify the WS3 external boundary evidence release."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file
from experiments.boundary import _report_text, compute_boundary_result, evaluate_run
from experiments.protocol_boundary import (
    BOUNDARY_ACTIVE_SHA256,
    CONFIG_SHA256,
    DATASET_ORDER,
    DATASETS,
    METHODS,
    QWEN_DIGEST,
    verify_boundary_protocol,
)
from experiments.protocol_longterm import ROOT

RUN_FILES = {"checkpoint.jsonl", "predictions.jsonl", "run_identity.json", "run_manifest.json"}


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _same_rows_by_sample_id(
    checkpoint: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
) -> bool:
    """Compare finalized rows without requiring checkpoint execution order."""

    checkpoint_by_id = {str(row.get("sample_id")): row for row in checkpoint}
    predictions_by_id = {str(row.get("sample_id")): row for row in predictions}
    return (
        len(checkpoint) == len(predictions)
        and len(checkpoint_by_id) == len(checkpoint)
        and len(predictions_by_id) == len(predictions)
        and checkpoint_by_id == predictions_by_id
    )


def _verify_run(
    path: Path,
    *,
    dataset: str,
    method: str,
    expected: int,
    partial: bool,
) -> tuple[list[str], set[str], str]:
    errors: list[str] = []
    actual_files = (
        {item.name for item in path.iterdir() if item.is_file()} if path.is_dir() else set()
    )
    if actual_files != RUN_FILES:
        errors.append(f"{dataset}/{method}: run file set is not exact")
    try:
        manifest = _object(path / "run_manifest.json")
        identity = _object(path / "run_identity.json")
        predictions = read_jsonl(path / "predictions.jsonl")
        checkpoint = read_jsonl(path / "checkpoint.jsonl")
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return [str(exc)], set(), ""
    ids = {str(row.get("sample_id")) for row in predictions}
    expected_checks = {
        "status": manifest.get("status") == "complete",
        "method": manifest.get("method") == method == identity.get("method"),
        "dataset": identity.get("dataset") == dataset,
        "protocol": identity.get("protocol_fingerprint") == BOUNDARY_ACTIVE_SHA256,
        "split": manifest.get("split") == "dev" == identity.get("split"),
        "partial": bool(manifest.get("partial")) == partial,
        "completed": int(manifest.get("completed", -1)) == expected == len(ids),
        "errors": int(manifest.get("errors", -1)) == 0,
        "prediction_hash": manifest.get("predictions_sha256")
        == sha256_file(path / "predictions.jsonl"),
        "checkpoint": _same_rows_by_sample_id(checkpoint, predictions),
        "signature": manifest.get("run_signature") == identity.get("run_signature"),
        "config": identity.get("config_sha256") == CONFIG_SHA256,
        "data_manifest": identity.get("data_manifest_sha256")
        == DATASETS[dataset]["manifest_sha256"],
        "limit": identity.get("limit") == (5 if partial else None),
        "clean": identity.get("source_revision", {}).get("git_dirty") is False,
        "model": identity.get("llm_runtime", {}).get("ollama_model", {}).get("model")
        == "qwen3.5:9b",
        "digest": identity.get("llm_runtime", {}).get("ollama_model", {}).get("digest")
        == QWEN_DIGEST,
    }
    for key, passed in expected_checks.items():
        if not passed:
            errors.append(f"{dataset}/{method}: run check failed: {key}")
    if len(predictions) != expected or len(checkpoint) != expected or len(ids) != expected:
        errors.append(f"{dataset}/{method}: row count or uniqueness mismatch")
    return errors, ids, str(identity.get("source_revision", {}).get("git_commit", ""))


def verify_release(output_root: Path, report_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    protocol = verify_boundary_protocol()
    if protocol.get("valid") is not True:
        errors.extend(f"protocol: {item}" for item in protocol.get("errors", []))
    try:
        manifest = _object(output_root / "manifest.json")
        result = _object(output_root / "result.json")
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return {
            "schema_version": "far-boundary-release-audit-v1",
            "valid": False,
            "errors": [str(exc)],
            "gate_b_complete": False,
            "global_pass_fail": None,
            "publication_gold": False,
            "human_iaa": False,
            "test_accessed": False,
        }
    commits: set[str] = set()
    for dataset in DATASET_ORDER:
        expected_ids = {
            str(row["id"]) for row in read_jsonl(Path(DATASETS[dataset]["path"]) / "tasks.jsonl")
        }
        calibration_ids: set[str] | None = None
        for method in METHODS:
            run_errors, ids, commit = _verify_run(
                output_root / "calibration" / dataset / method,
                dataset=dataset,
                method=method,
                expected=5,
                partial=True,
            )
            errors.extend(run_errors)
            if calibration_ids is None:
                calibration_ids = ids
            elif ids != calibration_ids:
                errors.append(f"{dataset}: calibration IDs differ across methods")
            commits.add(commit)
            run_errors, ids, commit = _verify_run(
                output_root / "runs" / dataset / method,
                dataset=dataset,
                method=method,
                expected=150,
                partial=False,
            )
            errors.extend(run_errors)
            if ids != expected_ids:
                errors.append(f"{dataset}/{method}: formal IDs do not exactly cover import")
            commits.add(commit)
    commits.discard("")
    if len(commits) != 1:
        errors.append("boundary release mixes source commits")
    else:
        try:
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", next(iter(commits)), "origin/main"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            errors.append("boundary source commit is not on origin/main")
    with tempfile.TemporaryDirectory(prefix="far-boundary-evidence-") as temporary:
        rebuilt = Path(temporary)
        for dataset in DATASET_ORDER:
            for method in METHODS:
                try:
                    destination = rebuilt / dataset / method
                    evaluate_run(
                        dataset,
                        output_root / "runs" / dataset / method / "predictions.jsonl",
                        destination,
                    )
                    for name in ("scores.jsonl", "report.json"):
                        if (destination / name).read_bytes() != (
                            output_root / "evaluations" / dataset / method / name
                        ).read_bytes():
                            errors.append(f"{dataset}/{method}: {name} differs from recomputation")
                except (
                    FileNotFoundError,
                    json.JSONDecodeError,
                    KeyError,
                    TypeError,
                    ValueError,
                ) as exc:
                    errors.append(f"{dataset}/{method}: evaluation failed: {exc}")
    try:
        recomputed = compute_boundary_result(output_root)
        if result != recomputed:
            errors.append("boundary result differs from recomputation")
        report = _report_text(recomputed).encode()
        if (output_root / "boundary_matrix.md").read_bytes() != report:
            errors.append("boundary internal report differs from recomputation")
        if report_path.read_bytes() != report:
            errors.append("boundary external report differs from recomputation")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors.append(f"boundary result recomputation failed: {exc}")
    expected_manifest = {
        "schema_version": "far-boundary-release-v1",
        "protocol_fingerprint": BOUNDARY_ACTIVE_SHA256,
        "source_commit": next(iter(commits)) if len(commits) == 1 else None,
        "gate_b_complete": True,
        "global_pass_fail": None,
        "formal_pipeline_samples": 600,
        "calibration_pipeline_samples": 20,
        "api_cost_usd": 0,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }
    for key, value in expected_manifest.items():
        if manifest.get(key) != value:
            errors.append(f"boundary manifest field mismatch: {key}")
    artifacts = {
        str(path.relative_to(output_root)): sha256_file(path)
        for path in sorted(output_root.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    if manifest.get("artifacts") != artifacts:
        errors.append("boundary artifact inventory or fingerprints mismatch")
    if manifest.get("external_report_sha256") != sha256_file(report_path):
        errors.append("boundary external report fingerprint mismatch")
    return {
        "schema_version": "far-boundary-release-audit-v1",
        "valid": not errors,
        "errors": errors,
        "gate_b_complete": not errors,
        "global_pass_fail": None,
        "required_claim_level": "directional_boundary_mapping",
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("diagnostics/boundary_v1"))
    parser.add_argument("--report", type=Path, default=Path("reports/boundary_matrix.md"))
    args = parser.parse_args()
    result = verify_release(args.output_dir, args.report)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result.get("valid") is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
