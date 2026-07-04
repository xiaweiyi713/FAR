"""Frozen identifiers and integrity checks for the preregistered 2+4 protocol."""

from __future__ import annotations

from pathlib import Path

from bench.build.common import sha256_file

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "docs" / "PLAN_2PLUS4.md"
PROTOCOL_ORIGINAL_SHA256 = "2cbb2452d2ea1f167a844e63b52bee4e15e3b8bf2adad7feb5dc86dd1d41c7fe"
PROTOCOL_ACTIVE_SHA256 = "0b4c69868339cb018d8a83ada2663dc3047f251e4ea41d09b2ec92dde0f1769b"
SYSTEM_MODEL_FAMILIES = frozenset({"qwen", "mistral", "google"})


def verify_active_protocol() -> str:
    observed = sha256_file(PROTOCOL_PATH)
    if observed != PROTOCOL_ACTIVE_SHA256:
        raise ValueError(
            "2+4 protocol fingerprint changed; record a deviation and update the active fingerprint"
        )
    return observed
