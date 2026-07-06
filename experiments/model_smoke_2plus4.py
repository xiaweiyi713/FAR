"""Verify the three local-model smoke records required by the 2+4 protocol."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from bench.build.common import sha256_file
from experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256, verify_active_protocol

ROOT = Path(__file__).resolve().parents[1]
MODEL_SPECS = {
    "mistral": ("mistral:7b-instruct", "experiments/configs/mistral_open.yaml"),
    "google": ("gemma2:9b", "experiments/configs/gemma_open.yaml"),
    "meta": ("llama3.1:8b", "experiments/configs/jury_llama.yaml"),
}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def verify_smoke_records(output_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        verify_active_protocol()
    except ValueError as exc:
        errors.append(str(exc))

    expected_files = {f"{family}.json" for family in MODEL_SPECS}
    actual_files = (
        {path.name for path in output_dir.iterdir() if path.is_file() and path.suffix == ".json"}
        if output_dir.is_dir()
        else set()
    )
    if actual_files != expected_files:
        errors.append("model smoke file set must be exactly mistral/google/meta JSON records")

    records: dict[str, dict[str, Any]] = {}
    for family, (model, config_path) in MODEL_SPECS.items():
        path = output_dir / f"{family}.json"
        try:
            record = _read_json(path)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            errors.append(str(exc))
            continue
        records[family] = record
        expected = {
            "schema_version": "far-2plus4-local-model-smoke-v1",
            "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
            "model_family": family,
            "model": model,
            "config_path": config_path,
            "config_sha256": sha256_file(ROOT / config_path),
            "smoke_passed": True,
            "benchmark_data_accessed": False,
            "publication_gold": False,
            "human_iaa": False,
        }
        for key, value in expected.items():
            if record.get(key) != value:
                errors.append(f"{family} smoke field mismatch: {key}")
        try:
            created_at = datetime.fromisoformat(str(record["created_at"]))
            if created_at.tzinfo is None:
                raise ValueError("timestamp lacks timezone")
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"{family} smoke created_at is invalid: {exc}")
        model_record = record.get("model_record")
        if not isinstance(model_record, dict):
            errors.append(f"{family} smoke lacks Ollama model provenance")
        else:
            recorded_name = model_record.get("name") or model_record.get("model")
            if recorded_name != model:
                errors.append(f"{family} Ollama model name mismatch")
            if not _DIGEST.fullmatch(str(model_record.get("digest", ""))):
                errors.append(f"{family} Ollama model digest is invalid")
        if "SMOKE_OK" not in str(record.get("response", "")):
            errors.append(f"{family} smoke response lacks SMOKE_OK")

    return {
        "schema_version": "far-2plus4-local-model-smoke-audit-v1",
        "valid": not errors,
        "errors": errors,
        "families": sorted(records),
        "records": {
            family: sha256_file(output_dir / f"{family}.json") for family in sorted(records)
        },
        "benchmark_data_accessed": False,
        "publication_gold": False,
        "human_iaa": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/mnt/d/FAR-outputs/model_smoke_2plus4"),
    )
    args = parser.parse_args()
    audit = verify_smoke_records(args.output_dir)
    print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    if audit.get("valid") is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
