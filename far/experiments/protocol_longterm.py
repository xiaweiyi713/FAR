"""Frozen identifiers and integrity checks for the post-stop-rule roadmap."""

from __future__ import annotations

from far.bench.build.common import sha256_file
from far.paths import repository_root

ROOT = repository_root()
ROADMAP_PATH = ROOT / "docs" / "PLAN_LONGTERM_OPTIMIZATION.md"
ROADMAP_ACTIVE_SHA256 = "91eb3205fe127271bc5f4882025243d9974a711e311ef074fcbde09aa86e7cf7"
FROZEN_FACT_IDS = tuple(f"F{index}" for index in range(1, 11))


def verify_active_roadmap() -> str:
    observed = sha256_file(ROADMAP_PATH)
    if observed != ROADMAP_ACTIVE_SHA256:
        raise ValueError(
            "long-term roadmap fingerprint changed; record a deviation and update the active "
            "fingerprint before continuing"
        )
    return observed
