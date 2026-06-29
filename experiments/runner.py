"""Shared configuration, signatures, checkpointing, and data loading."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.adapters import InMemoryRetriever, VeraLLMAdapter, VeraRetrieverAdapter
from far.models import EvidenceDocument
from far.protocols import TextGenerator

ROOT = Path(__file__).resolve().parents[1]


def load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("experiment config must be a YAML object")
    return value


def load_benchmark(data_dir: Path) -> tuple[list[dict[str, Any]], list[EvidenceDocument]]:
    samples = read_jsonl(data_dir / "falsirag_bench.jsonl")
    documents = [
        EvidenceDocument(
            evidence_id=row["doc_id"],
            text=row["content"],
            title=row["title"],
            source=row["source"],
            date=row.get("date"),
            url=row.get("url"),
            metadata={"synthetic": row.get("synthetic", False)},
        )
        for row in read_jsonl(data_dir / "corpus.jsonl")
    ]
    return samples, documents


def select_samples(
    samples: list[dict[str, Any]],
    split: str,
    *,
    limit: int | None,
    allow_test: bool,
) -> list[dict[str, Any]]:
    if split == "test" and not allow_test:
        raise ValueError("test split requires explicit --allow-test final-reporting authorization")
    selected = sorted((row for row in samples if row["split"] == split), key=lambda row: row["id"])
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        by_category: dict[str, list[dict[str, Any]]] = {}
        for row in selected:
            by_category.setdefault(str(row["category"]), []).append(row)
        balanced: list[dict[str, Any]] = []
        offset = 0
        while len(balanced) < min(limit, len(selected)):
            added = False
            for category in sorted(by_category):
                rows = by_category[category]
                if offset < len(rows) and len(balanced) < limit:
                    balanced.append(rows[offset])
                    added = True
            if not added:
                break
            offset += 1
        selected = balanced
    if not selected:
        raise ValueError(f"split {split!r} selected no samples")
    return selected


def build_retriever(config: dict[str, Any], documents: list[EvidenceDocument]) -> Any:
    name = config.get("retrieval", {}).get("backend", "lexical")
    if name == "lexical":
        return InMemoryRetriever(documents)
    if name == "vera_bm25":
        return VeraRetrieverAdapter.bm25(documents, config.get("retrieval", {}))
    raise ValueError(f"unsupported retrieval backend: {name}")


def build_generator(config: dict[str, Any]) -> TextGenerator | None:
    llm = config.get("llm", {})
    if not llm.get("enabled", False):
        return None
    options = {
        key: value
        for key, value in llm.items()
        if key
        in {
            "provider",
            "model",
            "base_url",
            "temperature",
            "max_tokens",
            "cache_enabled",
            "cache_path",
            "cache_namespace",
        }
    }
    api_env = llm.get("api_key_env")
    if api_env:
        api_key = os.getenv(str(api_env))
        if not api_key:
            raise RuntimeError(f"required API key environment variable is unset: {api_env}")
        options["api_key"] = api_key
    return VeraLLMAdapter(**options)


def _implementation_sha256() -> str:
    digest = hashlib.sha256()
    for package in ("far", "baselines", "eval", "experiments", "bench"):
        for path in sorted((ROOT / package).rglob("*.py")):
            digest.update(str(path.relative_to(ROOT)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def build_run_identity(
    config_path: Path,
    config: dict[str, Any],
    data_dir: Path,
    method: str,
    *,
    split: str,
    limit: int | None,
) -> dict[str, Any]:
    stable = {
        "schema_version": "far-run-signature-v1",
        "method": method,
        "split": split,
        "limit": limit,
        "config_sha256": sha256_file(config_path),
        "benchmark_sha256": sha256_file(data_dir / "falsirag_bench.jsonl"),
        "corpus_sha256": sha256_file(data_dir / "corpus.jsonl"),
        "implementation_sha256": _implementation_sha256(),
        "llm": config.get("llm", {}),
        "retrieval": config.get("retrieval", {}),
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    return {
        **stable,
        "run_signature": hashlib.sha256(encoded).hexdigest(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "packages": {
                name: _package_version(name) for name in ("numpy", "PyYAML", "rank-bm25", "verarag")
            },
        },
    }


class CheckpointWriter:
    def __init__(self, output_dir: Path, identity: dict[str, Any]) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.identity = identity
        self.checkpoint_path = output_dir / "checkpoint.jsonl"
        identity_path = output_dir / "run_identity.json"
        if identity_path.exists():
            existing = json.loads(identity_path.read_text(encoding="utf-8"))
            if existing.get("run_signature") != identity["run_signature"]:
                raise ValueError("output directory belongs to a different run signature")
        else:
            write_json(identity_path, identity)
        self.rows = read_jsonl(self.checkpoint_path) if self.checkpoint_path.exists() else []
        self.completed_ids = {row["sample_id"] for row in self.rows}

    def append(self, row: dict[str, Any]) -> None:
        with self.checkpoint_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.rows.append(row)
        self.completed_ids.add(row["sample_id"])

    def finalize(self, expected_ids: set[str], *, partial: bool) -> dict[str, Any]:
        observed = {row["sample_id"] for row in self.rows}
        missing = sorted(expected_ids - observed)
        errors = [row for row in self.rows if row.get("error")]
        status = "complete" if not missing and not errors else "failed"
        ordered = sorted(self.rows, key=lambda row: row["sample_id"])
        write_jsonl(self.output_dir / "predictions.jsonl", ordered)
        manifest = {
            "schema_version": "far-run-manifest-v1",
            "run_signature": self.identity["run_signature"],
            "method": self.identity["method"],
            "split": self.identity["split"],
            "status": status,
            "partial": partial,
            "expected": len(expected_ids),
            "completed": len(observed),
            "missing_ids": missing,
            "errors": len(errors),
            "predictions_sha256": sha256_file(self.output_dir / "predictions.jsonl"),
        }
        write_json(self.output_dir / "run_manifest.json", manifest)
        if status != "complete":
            raise RuntimeError(f"run failed: {len(missing)} missing, {len(errors)} errors")
        return manifest
