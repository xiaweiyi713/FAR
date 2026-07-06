"""Frozen identities and fail-closed checks for the WS2 family-dev study."""

from __future__ import annotations

import json
import subprocess
from typing import Any, cast

from bench.build.common import sha256_file
from experiments.protocol_longterm import (
    ROADMAP_ACTIVE_SHA256,
    ROOT,
    verify_active_roadmap,
)
from experiments.runner import load_config

FAMILY_DEV_PLAN = ROOT / "docs" / "PLAN_FAMILY_DEV.md"
FAMILY_DEV_ACTIVE_SHA256 = "5acc611bf8bb79740a996cc7bc9bd262bc55a661373f070670da19f7aa48433b"
DEV_INPUT_SHA256 = "63db7916ef42d3da7e70fe977471a6958afec2a760bcad3d43526052ecd5dff3"
CORPUS_SHA256 = "cca5f62db0fbb51e1bae8111ea85fe169fba7be5a8e63847a9c1c048cdae25cd"
POWER_MANIFEST_SHA256 = "d67740f2ec3a143e6efe61d4a973558ab4b74578ab021279c5f69e0f4205fce3"
MODEL_SPECS: dict[str, dict[str, str]] = {
    "mistral": {
        "model": "mistral:7b-instruct",
        "digest": "6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf",
        "config": "experiments/configs/mistral_open.yaml",
        "config_sha256": "31035391d672883e2d6f347ca3acd937cd91f2c345e960695292be88774d4b5b",
        "smoke": "diagnostics/model_smoke_2plus4/mistral.json",
    },
    "google": {
        "model": "gemma2:9b",
        "digest": "ff02c3702f322b9e075e9568332d96c0a7028002f1a5a056e0a6784320a4db0b",
        "config": "experiments/configs/gemma_open.yaml",
        "config_sha256": "2c348c6a530b31d5154b992e9f111528b81d78541ea40b48e121e6c1511098e1",
        "smoke": "diagnostics/model_smoke_2plus4/google.json",
    },
    "meta": {
        "model": "llama3.1:8b",
        "digest": "46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e",
        "config": "experiments/configs/llama_open.yaml",
        "config_sha256": "127eff6e860dc81b1252a8d8507fe499da4b5bad1e095097686f3c696e6f4090",
        "smoke": "diagnostics/model_smoke_2plus4/meta.json",
    },
}
FAMILY_ORDER = ("mistral", "google", "meta")
METHODS = ("far", "minus_typed_conflict")


def _shared_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = cast(dict[str, Any], json.loads(json.dumps(config)))
    llm = normalized["llm"]
    for key in ("model", "cache_path", "cache_namespace"):
        llm.pop(key, None)
    return normalized


def verify_family_protocol() -> dict[str, Any]:
    errors: list[str] = []
    try:
        roadmap = verify_active_roadmap()
        if roadmap != ROADMAP_ACTIVE_SHA256:
            errors.append("long-term roadmap fingerprint mismatch")
    except ValueError as exc:
        errors.append(str(exc))
    if sha256_file(FAMILY_DEV_PLAN) != FAMILY_DEV_ACTIVE_SHA256:
        errors.append("family-dev preregistration fingerprint mismatch")
    if sha256_file(ROOT / "bench" / "splits" / "dev.jsonl") != DEV_INPUT_SHA256:
        errors.append("family-dev dev input fingerprint mismatch")
    if sha256_file(ROOT / "bench" / "corpus.jsonl") != CORPUS_SHA256:
        errors.append("family-dev corpus fingerprint mismatch")
    power_manifest = ROOT / "diagnostics" / "power_v1" / "manifest.json"
    if sha256_file(power_manifest) != POWER_MANIFEST_SHA256:
        errors.append("family-dev G-P manifest fingerprint mismatch")
    try:
        power = json.loads(power_manifest.read_text(encoding="utf-8"))
        if (
            power.get("gate_p_completed") is not True
            or power.get("adequately_powered") is not False
            or power.get("required_claim_level") != "directional_reproduction"
            or power.get("test_accessed") is not False
        ):
            errors.append("family-dev G-P disposition mismatch")
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        errors.append(f"family-dev G-P manifest invalid: {exc}")
    configs: dict[str, dict[str, Any]] = {}
    for family, spec in MODEL_SPECS.items():
        config_path = ROOT / spec["config"]
        if sha256_file(config_path) != spec["config_sha256"]:
            errors.append(f"{family} config fingerprint mismatch")
        config = load_config(config_path)
        configs[family] = config
        if config.get("llm", {}).get("model") != spec["model"]:
            errors.append(f"{family} config model mismatch")
        try:
            smoke = json.loads((ROOT / spec["smoke"]).read_text(encoding="utf-8"))
            if smoke.get("model") != spec["model"]:
                errors.append(f"{family} smoke model mismatch")
            if smoke.get("model_record", {}).get("digest") != spec["digest"]:
                errors.append(f"{family} smoke digest mismatch")
            if smoke.get("benchmark_data_accessed") is not False:
                errors.append(f"{family} smoke accessed benchmark data")
        except (FileNotFoundError, json.JSONDecodeError, AttributeError) as exc:
            errors.append(f"{family} smoke record invalid: {exc}")
    if configs:
        reference = _shared_config(configs[FAMILY_ORDER[0]])
        for family in FAMILY_ORDER[1:]:
            if _shared_config(configs[family]) != reference:
                errors.append(f"{family} config differs beyond model/cache identity")
    return {
        "schema_version": "far-family-dev-protocol-audit-v1",
        "valid": not errors,
        "errors": errors,
        "protocol_fingerprint": FAMILY_DEV_ACTIVE_SHA256,
        "roadmap_fingerprint": ROADMAP_ACTIVE_SHA256,
        "power_manifest_sha256": POWER_MANIFEST_SHA256,
        "families": list(FAMILY_ORDER),
        "methods": list(METHODS),
        "split": "dev",
        "samples": 60,
        "required_claim_level": "directional_reproduction",
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }


def require_clean_pushed_source() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise ValueError("formal family-dev run requires a clean Git worktree")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "origin/main"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return commit
