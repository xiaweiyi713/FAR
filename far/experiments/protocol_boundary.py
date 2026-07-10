"""Frozen identities for the WS3 external boundary mapping study."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from far.bench.build.common import sha256_file
from far.experiments.protocol_longterm import ROADMAP_ACTIVE_SHA256, ROOT, verify_active_roadmap
from far.experiments.runner import load_config
from far.paths import experiment_config_dir

BOUNDARY_PLAN = ROOT / "docs" / "PLAN_BOUNDARY_MAPPING.md"
BOUNDARY_ACTIVE_SHA256 = "a8aa260aec7b92f2d51bc4c14ce78b0f355b2b61e543c5ace0cff52c5c1d34a3"
QWEN_DIGEST = "6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7"
CONFIG_PATH = experiment_config_dir() / "qwen_boundary.yaml"
CONFIG_SHA256 = "d3a36b59d02eb4c086e87445d0757d466a25e9f3d2428d4bdc9a36bae9acc979"
DATASETS: dict[str, dict[str, Any]] = {
    "wikicontradict": {
        "kind": "wiki",
        "path": ROOT / "bench" / "external" / "wikicontradict_v1",
        "manifest_sha256": "b3b3b80c44600579e15cfe4e9071040cfd99cc3d49ed716ee9dd603435a07765",
    },
    "rag_conflicts": {
        "kind": "conflicts",
        "path": ROOT / "bench" / "external" / "rag_conflicts_v1",
        "manifest_sha256": "ec12941a2e98461219858d56a6a07545ba4d5ac70eca96dac2f6148b4ccb86e5",
    },
}
DATASET_ORDER = ("wikicontradict", "rag_conflicts")
METHODS = ("far", "far_minus_typed_conflict")


def verify_boundary_protocol() -> dict[str, Any]:
    errors: list[str] = []
    try:
        verify_active_roadmap()
    except ValueError as exc:
        errors.append(str(exc))
    if BOUNDARY_ACTIVE_SHA256 == "UNREGISTERED":
        errors.append("boundary protocol is not registered")
    elif sha256_file(BOUNDARY_PLAN) != BOUNDARY_ACTIVE_SHA256:
        errors.append("boundary preregistration fingerprint mismatch")
    if sha256_file(CONFIG_PATH) != CONFIG_SHA256:
        errors.append("boundary config fingerprint mismatch")
    config = load_config(CONFIG_PATH)
    if config.get("llm", {}).get("model") != "qwen3.5:9b":
        errors.append("boundary config model mismatch")
    for name, spec in DATASETS.items():
        path = Path(spec["path"])
        if sha256_file(path / "manifest.json") != spec["manifest_sha256"]:
            errors.append(f"{name} import manifest fingerprint mismatch")
        try:
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            if (
                manifest.get("kind") != spec["kind"]
                or manifest.get("samples") != 150
                or manifest.get("split") != "dev"
                or manifest.get("test_accessed") is not False
            ):
                errors.append(f"{name} import manifest field mismatch")
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            errors.append(f"{name} import manifest invalid: {exc}")
    return {
        "schema_version": "far-boundary-protocol-audit-v1",
        "valid": not errors,
        "errors": errors,
        "protocol_fingerprint": BOUNDARY_ACTIVE_SHA256,
        "roadmap_fingerprint": ROADMAP_ACTIVE_SHA256,
        "datasets": list(DATASET_ORDER),
        "methods": list(METHODS),
        "samples_per_dataset": 150,
        "required_claim_level": "directional_boundary_mapping",
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }
