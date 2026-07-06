"""Audit the preregistered paper-downgrade branch after a second G-A failure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bench.build.common import sha256_file, write_json
from experiments.evidence_2plus4 import verify_ramdocs_round2_release
from experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256, verify_active_protocol


REQUIRED_DISCLOSURES = {
    "round2_result": ("round 2", "g-a"),
    "two_round_stop": ("second", "failed"),
    "boundary_claim": ("applicability-boundary",),
    "phase_b_not_run": ("phase b", "not run"),
    "held_out_not_run": ("held-out", "not run"),
    "non_human_provenance": ("not human inter-annotator agreement",),
    "upstream_labels": ("upstream labels",),
}
FORBIDDEN_CLAIMS = (
    "ramdocs validates an end-to-end advantage",
    "cross-family jury confirms",
    "human inter-annotator agreement confirms",
)


def audit_failure_branch(
    data_dir: Path,
    bundle_dir: Path,
    paper_main: Path,
    paper_status: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        verify_active_protocol()
        release_audit = verify_ramdocs_round2_release(bundle_dir, data_dir)
        manifest = json.loads(
            (bundle_dir / "bundle_manifest.json").read_text(encoding="utf-8")
        )
        analysis = json.loads(
            (bundle_dir / "round2/error_analysis/report.json").read_text(encoding="utf-8")
        )
        paper = paper_main.read_text(encoding="utf-8")
        status = paper_status.read_text(encoding="utf-8")
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "schema_version": "far-ramdocs-round2-failure-readiness-v1",
            "ready": False,
            "errors": [str(exc)],
        }
    if release_audit.get("valid") is not True:
        errors.extend(f"Round 2 release: {item}" for item in release_audit.get("errors", []))
    if any(
        (
            manifest.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256,
            manifest.get("gate_a_passed") is not False,
            manifest.get("stop_rule_triggered") is not True,
            manifest.get("paper_downgrade_required") is not True,
            manifest.get("test_accessed") is not False,
            manifest.get("publication_gold") is not False,
            manifest.get("human_iaa") is not False,
        )
    ):
        errors.append("Round 2 release does not encode the failed-G-A downgrade branch")
    if any(
        (
            analysis.get("gate_a_passed") is not False,
            analysis.get("stop_rule_triggered") is not True,
            analysis.get("paper_downgrade_required") is not True,
            analysis.get("test_accessed") is not False,
            analysis.get("human_iaa") is not False,
        )
    ):
        errors.append("Round 2 error analysis does not encode the downgrade branch")

    combined = f"{paper}\n{status}".lower()
    disclosure_checks = {
        name: all(fragment in combined for fragment in fragments)
        for name, fragments in REQUIRED_DISCLOSURES.items()
    }
    missing = [name for name, present in disclosure_checks.items() if not present]
    if missing:
        errors.append(f"paper downgrade disclosures are missing: {missing}")
    forbidden = [claim for claim in FORBIDDEN_CLAIMS if claim in combined]
    if forbidden:
        errors.append(f"paper contains claims forbidden after failed G-A: {forbidden}")

    return {
        "schema_version": "far-ramdocs-round2-failure-readiness-v1",
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "ready": not errors,
        "study_profile": "typed_conflict_control_applicability_boundary_analysis",
        "gate_a_passed": False,
        "phase_b_run": False,
        "test_accessed": False,
        "publication_gold": False,
        "human_iaa": False,
        "checks": {
            "round2_release_valid": release_audit.get("valid") is True,
            "paper_downgrade_required": manifest.get("paper_downgrade_required") is True,
            "paper_disclosures": disclosure_checks,
            "forbidden_claims_absent": not forbidden,
        },
        "errors": errors,
        "evidence": {
            "bundle_manifest_sha256": sha256_file(bundle_dir / "bundle_manifest.json"),
            "error_analysis_sha256": sha256_file(
                bundle_dir / "round2/error_analysis/report.json"
            ),
            "paper_main_sha256": sha256_file(paper_main),
            "paper_status_sha256": sha256_file(paper_status),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--paper-main", type=Path, default=Path("paper/main.tex"))
    parser.add_argument("--paper-status", type=Path, default=Path("paper/STATUS.md"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_failure_branch(
        args.data_dir,
        args.bundle_dir,
        args.paper_main,
        args.paper_status,
    )
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result.get("ready") is not True:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
