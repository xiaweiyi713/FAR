"""Independently verify the preregistered WS2 family-dev evidence release."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file
from eval.run_eval import evaluate
from experiments.family_dev import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    _report_text,
    compute_result,
)
from experiments.protocol_family_dev import (
    CORPUS_SHA256,
    DEV_INPUT_SHA256,
    FAMILY_DEV_ACTIVE_SHA256,
    FAMILY_ORDER,
    METHODS,
    MODEL_SPECS,
    verify_family_protocol,
)
from experiments.protocol_longterm import ROOT

RUN_FILES = {"checkpoint.jsonl", "predictions.jsonl", "run_identity.json", "run_manifest.json"}


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
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
    family: str,
    method: str,
    expected: int,
    partial: bool,
    calibration_ids: set[str] | None,
) -> tuple[list[str], set[str], str]:
    errors: list[str] = []
    files = {item.name for item in path.iterdir() if item.is_file()} if path.is_dir() else set()
    if files != RUN_FILES:
        errors.append(f"{path}: run file set is not exact")
    try:
        manifest = _read_object(path / "run_manifest.json")
        identity = _read_object(path / "run_identity.json")
        predictions = read_jsonl(path / "predictions.jsonl")
        checkpoint = read_jsonl(path / "checkpoint.jsonl")
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return [str(exc)], set(), ""
    ids = {str(row.get("sample_id")) for row in predictions}
    expected_method = "far" if method == "far" else "far_minus_typed_conflict"
    checks = {
        "status": manifest.get("status") == "complete",
        "method": manifest.get("method") == expected_method == identity.get("method"),
        "split": manifest.get("split") == "dev" == identity.get("split"),
        "completed": int(manifest.get("completed", -1)) == expected == len(ids),
        "partial": bool(manifest.get("partial")) == partial,
        "errors": int(manifest.get("errors", -1)) == 0,
        "predictions": manifest.get("predictions_sha256")
        == sha256_file(path / "predictions.jsonl"),
        "checkpoint": _same_rows_by_sample_id(checkpoint, predictions),
        "run_signature": manifest.get("run_signature") == identity.get("run_signature"),
        "config": identity.get("config_sha256") == MODEL_SPECS[family]["config_sha256"],
        "dev_input": identity.get("benchmark_input_sha256") == DEV_INPUT_SHA256,
        "corpus": identity.get("corpus_sha256") == CORPUS_SHA256,
        "limit": identity.get("limit") == (5 if partial else None),
        "clean": identity.get("source_revision", {}).get("git_dirty") is False,
        "model": identity.get("llm_runtime", {}).get("ollama_model", {}).get("model")
        == MODEL_SPECS[family]["model"],
        "digest": identity.get("llm_runtime", {}).get("ollama_model", {}).get("digest")
        == MODEL_SPECS[family]["digest"],
    }
    for key, passed in checks.items():
        if not passed:
            errors.append(f"{family}/{method}: run check failed: {key}")
    if len(predictions) != expected or len(checkpoint) != expected or len(ids) != expected:
        errors.append(f"{family}/{method}: row count or uniqueness mismatch")
    if any(str(row.get("sample_id", "")).startswith("RAM") for row in predictions):
        errors.append(f"{family}/{method}: RAMDocs row found in family-dev release")
    if calibration_ids is not None and ids != calibration_ids:
        errors.append(f"{family}/{method}: calibration sample IDs differ across arms/families")
    return errors, ids, str(identity.get("source_revision", {}).get("git_commit", ""))


def verify_release(output_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    protocol = verify_family_protocol()
    if protocol.get("valid") is not True:
        errors.extend(f"protocol: {item}" for item in protocol.get("errors", []))
    try:
        manifest = _read_object(output_root / "manifest.json")
        observed_result = _read_object(output_root / "result.json")
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return {
            "schema_version": "far-family-dev-release-audit-v1",
            "valid": False,
            "errors": [str(exc)],
            "gate_f_passed": False,
            "gate_p_completed": False,
            "publication_gold": False,
            "human_iaa": False,
            "test_accessed": False,
        }
    calibration_ids: set[str] | None = None
    formal_ids = {str(row["id"]) for row in read_jsonl(ROOT / "bench" / "splits" / "dev.jsonl")}
    commits: set[str] = set()
    for family in FAMILY_ORDER:
        family_manifest_path = output_root / "family_manifests" / f"{family}.json"
        try:
            family_manifest = _read_object(family_manifest_path)
            if (
                family_manifest.get("protocol_fingerprint") != FAMILY_DEV_ACTIVE_SHA256
                or family_manifest.get("family") != family
                or family_manifest.get("digest") != MODEL_SPECS[family]["digest"]
                or family_manifest.get("formal_pipeline_samples") != 120
                or family_manifest.get("calibration_pipeline_samples") != 10
                or family_manifest.get("test_accessed") is not False
            ):
                errors.append(f"{family}: family completion manifest mismatch")
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            errors.append(str(exc))
        for method in METHODS:
            run_errors, ids, commit = _verify_run(
                output_root / "calibration" / family / method,
                family=family,
                method=method,
                expected=5,
                partial=True,
                calibration_ids=calibration_ids,
            )
            errors.extend(run_errors)
            if calibration_ids is None and ids:
                calibration_ids = ids
            commits.add(commit)
            run_errors, ids, commit = _verify_run(
                output_root / "runs" / family / method,
                family=family,
                method=method,
                expected=60,
                partial=False,
                calibration_ids=None,
            )
            errors.extend(run_errors)
            if ids != formal_ids:
                errors.append(f"{family}/{method}: formal IDs do not exactly equal dev")
            commits.add(commit)
    commits.discard("")
    if len(commits) != 1:
        errors.append("family-dev release mixes source commits")
    else:
        commit = next(iter(commits))
        try:
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", commit, "origin/main"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            errors.append("family-dev source commit is not on origin/main")
    dev_path = ROOT / "bench" / "splits" / "dev.jsonl"
    with tempfile.TemporaryDirectory(prefix="far-family-dev-verify-") as temporary:
        temporary_root = Path(temporary)
        for family in FAMILY_ORDER:
            for method in METHODS:
                recomputed_dir = temporary_root / family / method
                try:
                    evaluate(
                        dev_path,
                        output_root / "runs" / family / method / "predictions.jsonl",
                        recomputed_dir,
                        resamples=BOOTSTRAP_RESAMPLES,
                        seed=BOOTSTRAP_SEED,
                        benchmark_manifest_path=ROOT / "bench" / "manifest.json",
                    )
                    for name in ("scores.jsonl", "report.json"):
                        if (recomputed_dir / name).read_bytes() != (
                            output_root / "evaluations" / family / method / name
                        ).read_bytes():
                            errors.append(f"{family}/{method}: {name} differs from recomputation")
                except (
                    FileNotFoundError,
                    json.JSONDecodeError,
                    KeyError,
                    TypeError,
                    ValueError,
                ) as exc:
                    errors.append(f"{family}/{method}: evaluation recomputation failed: {exc}")
    try:
        recomputed_result = compute_result(output_root)
        if recomputed_result != observed_result:
            errors.append("family-dev result differs from deterministic recomputation")
        expected_report = _report_text(recomputed_result).encode()
        if (output_root / "family_dev_report.md").read_bytes() != expected_report:
            errors.append("family-dev report differs from deterministic recomputation")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors.append(f"family-dev result recomputation failed: {exc}")
    expected_manifest = {
        "schema_version": "far-family-dev-release-v1",
        "protocol_fingerprint": FAMILY_DEV_ACTIVE_SHA256,
        "gate_p_completed": True,
        "adequately_powered": False,
        "required_claim_level": "directional_reproduction",
        "formal_pipeline_samples": 360,
        "calibration_pipeline_samples": 30,
        "api_cost_usd": 0,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }
    for key, value in expected_manifest.items():
        if manifest.get(key) != value:
            errors.append(f"family-dev manifest field mismatch: {key}")
    actual_artifacts = {
        str(path.relative_to(output_root)): sha256_file(path)
        for path in sorted(output_root.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    if manifest.get("artifacts") != actual_artifacts:
        errors.append("family-dev artifact inventory or fingerprints mismatch")
    if manifest.get("result_sha256") != sha256_file(output_root / "result.json"):
        errors.append("family-dev result fingerprint mismatch")
    if manifest.get("report_sha256") != sha256_file(output_root / "family_dev_report.md"):
        errors.append("family-dev report fingerprint mismatch")
    return {
        "schema_version": "far-family-dev-release-audit-v1",
        "valid": not errors,
        "errors": errors,
        "gate_f_passed": observed_result.get("primary", {}).get("gate_f_passed", False),
        "direction_consistent": observed_result.get("primary", {}).get(
            "direction_consistent", False
        ),
        "gate_p_completed": not errors,
        "required_claim_level": "directional_reproduction",
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("diagnostics/family_dev_v1"),
    )
    args = parser.parse_args()
    result = verify_release(args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result.get("valid") is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
