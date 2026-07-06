"""Fail-closed authorization for Phase B of the preregistered 2+4 study."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bench.build.common import sha256_file
from experiments.ramdocs_round2 import verify_round


def require_phase_b_authorized(
    data_dir: Path,
    round1_dir: Path,
    round2_dir: Path,
    config_path: Path,
) -> dict[str, Any]:
    audit = verify_round(data_dir, round1_dir, round2_dir, config_path)
    if audit.get("valid") is not True or audit.get("gate_a_passed") is not True:
        raise ValueError(f"verified RAMDocs G-A does not authorize Phase B: {audit['errors']}")
    manifest_path = round2_dir / "round_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if any(
        (
            manifest.get("gate_a_passed") is not True,
            manifest.get("phase_b_authorized") is not True,
            manifest.get("stop_rule_triggered") is not False,
            manifest.get("test_accessed") is not False,
            manifest.get("publication_gold") is not False,
            manifest.get("human_iaa") is not False,
        )
    ):
        raise ValueError("RAMDocs Round 2 manifest does not authorize Phase B")
    return {
        "round_manifest_sha256": sha256_file(manifest_path),
        "round1_suite_manifest_sha256": sha256_file(round1_dir / "suite_manifest.json"),
        "config_sha256": sha256_file(config_path),
        "samples": audit.get("samples"),
        "gate_a_passed": True,
        "phase_b_authorized": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--round1-dir", type=Path, required=True)
    parser.add_argument("--round2-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = require_phase_b_authorized(
        args.data_dir,
        args.round1_dir,
        args.round2_dir,
        args.config,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
