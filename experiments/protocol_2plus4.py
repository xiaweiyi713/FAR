"""Frozen identifiers and integrity checks for the preregistered 2+4 protocol."""

from __future__ import annotations

from pathlib import Path

from bench.build.common import sha256_file

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "docs" / "PLAN_2PLUS4.md"
PROTOCOL_ORIGINAL_SHA256 = "2cbb2452d2ea1f167a844e63b52bee4e15e3b8bf2adad7feb5dc86dd1d41c7fe"
PROTOCOL_PHASE_A_SHA256 = "e0221cfa9569ba089136fd017c1175ad282643c4c773b5f661f42ba95c9d7d00"
PROTOCOL_ACTIVE_SHA256 = "0a5e963166bcb49ff9b417c12690e1af4f642009359c77523080cff9a9d7cad9"
SYSTEM_MODEL_FAMILIES = frozenset({"qwen", "mistral", "google"})


def verify_active_protocol() -> str:
    observed = sha256_file(PROTOCOL_PATH)
    if observed != PROTOCOL_ACTIVE_SHA256:
        raise ValueError(
            "2+4 protocol fingerprint changed; record a deviation and update the active fingerprint"
        )
    return observed
