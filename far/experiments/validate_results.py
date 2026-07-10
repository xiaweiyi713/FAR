"""Reject incomplete, mismatched, non-finite, or provenance-broken result bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from far.bench.build.common import read_jsonl, sha256_file, write_json

_LEAKED_REASONING_MARKERS = ("thinking process:", "<think>", "</think>")


def _finite(value: Any) -> bool:
    if isinstance(value, bool | str) or value is None:
        return True
    if isinstance(value, int | float):
        return math.isfinite(float(value))
    if isinstance(value, dict):
        return all(_finite(item) for item in value.values())
    if isinstance(value, list):
        return all(_finite(item) for item in value)
    return True


def _leaked_reasoning_ids(predictions: list[dict[str, Any]]) -> list[str]:
    leaked = []
    for row in predictions:
        answer = str(row.get("answer", "")).lower()
        if any(marker in answer for marker in _LEAKED_REASONING_MARKERS):
            leaked.append(str(row.get("sample_id", "<unknown>")))
    return sorted(leaked)


def validate_result_bundle(run_dir: Path, evaluation_dir: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    identity = json.loads((run_dir / "run_identity.json").read_text(encoding="utf-8"))
    predictions_path = run_dir / "predictions.jsonl"
    predictions = read_jsonl(predictions_path)
    if manifest.get("status") != "complete":
        errors.append("run manifest status is not complete")
    if manifest.get("errors") != 0:
        errors.append("run manifest records errors")
    if manifest.get("expected") != manifest.get("completed"):
        errors.append("run manifest is not complete for its expected inputs")
    if manifest.get("run_signature") != identity.get("run_signature"):
        errors.append("run signature mismatch")
    if identity.get("schema_version") == "far-run-signature-v2":
        stable = {
            key: value
            for key, value in identity.items()
            if key not in {"run_signature", "created_at", "environment"}
        }
        expected_signature = hashlib.sha256(
            json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if identity.get("run_signature") != expected_signature:
            errors.append("run identity signature is invalid")
    if manifest.get("predictions_sha256") != sha256_file(predictions_path):
        errors.append("prediction fingerprint mismatch")
    if len(predictions) != manifest.get("completed"):
        errors.append("prediction count differs from run manifest")
    if len({row.get("sample_id") for row in predictions}) != len(predictions):
        errors.append("duplicate prediction IDs")
    if any(not _finite(row) for row in predictions):
        errors.append("predictions contain non-finite values")
    leaked_reasoning = _leaked_reasoning_ids(predictions)
    if leaked_reasoning:
        errors.append(
            "predictions contain leaked model reasoning in answer: " + ", ".join(leaked_reasoning)
        )
    report_summary = None
    if evaluation_dir is not None:
        report_path = evaluation_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("provenance", {}).get("predictions_sha256") != sha256_file(predictions_path):
            errors.append("evaluation report points to different predictions")
        if not _finite(report):
            errors.append("evaluation report contains non-finite values")
        report_summary = {"method": report.get("method"), "samples": report.get("samples")}
    return {
        "schema_version": "far-result-validation-v1",
        "valid": not errors,
        "errors": errors,
        "run": {
            "method": manifest.get("method"),
            "samples": len(predictions),
            "partial": manifest.get("partial"),
        },
        "evaluation": report_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--evaluation-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate_result_bundle(args.run_dir, args.evaluation_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.output:
        write_json(args.output, report)
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
