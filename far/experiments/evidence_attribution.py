"""Build or independently verify the frozen WS1 attribution evidence release."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from far.bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.experiments.attribution import (
    BUCKET_PRIORITY,
    HYPOTHESIS_IDS,
    _report_text,
    build_bundle,
    compute_attribution,
    verify_analysis_freeze,
)
from far.experiments.protocol_longterm import ROADMAP_ACTIVE_SHA256, verify_active_roadmap

RELEASE_FILES = {
    "failure_buckets.jsonl",
    "stratified_analysis.json",
    "dev_component_attribution.json",
    "hypotheses.json",
    "mechanism_attribution.md",
    "manifest.json",
}


def _render_recomputed(directory: Path, result: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    write_jsonl(directory / "failure_buckets.jsonl", result["failure_buckets"])
    write_json(directory / "stratified_analysis.json", result["stratified_analysis"])
    write_json(
        directory / "dev_component_attribution.json",
        result["dev_component_attribution"],
    )
    write_json(directory / "hypotheses.json", result["hypotheses"])
    (directory / "mechanism_attribution.md").write_text(
        _report_text(result),
        encoding="utf-8",
    )


def verify_bundle(
    *,
    ramdocs_data_dir: Path,
    round1_dir: Path,
    round2_dir: Path,
    solo_suite_dir: Path,
    machine_rows_path: Path,
    bundle_dir: Path,
    report_path: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        roadmap = verify_active_roadmap()
        manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return {
            "schema_version": "far-ws1-attribution-audit-v1",
            "valid": False,
            "errors": [str(exc)],
            "roadmap_fingerprint": ROADMAP_ACTIVE_SHA256,
            "gate_r1_passed": False,
            "model_calls": 0,
            "publication_gold": False,
            "human_iaa": False,
            "test_accessed": False,
        }
    actual_files = (
        {path.name for path in bundle_dir.iterdir() if path.is_file()}
        if bundle_dir.is_dir()
        else set()
    )
    if actual_files != RELEASE_FILES:
        errors.append("WS1 release file set is not exact")
    expected_fields = {
        "schema_version": "far-ws1-attribution-release-v1",
        "roadmap_fingerprint": ROADMAP_ACTIVE_SHA256,
        "split": "dev",
        "ramdocs_samples": 350,
        "both_incorrect_samples": 226,
        "bucket_priority": list(BUCKET_PRIORITY),
        "gate_r1_passed": True,
        "model_calls": 0,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
        "reopens_gate_a": False,
    }
    for key, value in expected_fields.items():
        if manifest.get(key) != value:
            errors.append(f"manifest field mismatch: {key}")
    if roadmap != manifest.get("roadmap_fingerprint"):
        errors.append("roadmap fingerprint mismatch")
    try:
        freeze_commit = str(manifest["analysis_freeze"]["commit"])
        freeze = verify_analysis_freeze(freeze_commit)
        if freeze != manifest.get("analysis_freeze"):
            errors.append("analysis freeze record mismatch")
        statistics = manifest["statistics"]
        resamples = int(statistics["resamples"])
        seed = int(statistics["seed"])
        recomputed = compute_attribution(
            ramdocs_data_dir=ramdocs_data_dir,
            round1_dir=round1_dir,
            round2_dir=round2_dir,
            solo_suite_dir=solo_suite_dir,
            machine_rows_path=machine_rows_path,
            resamples=resamples,
            seed=seed,
        )
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        subprocess.CalledProcessError,
    ) as exc:
        errors.append(str(exc))
        recomputed = None
    if recomputed is not None:
        bucket_counts = recomputed["bucket_counts"]
        if manifest.get("bucket_counts") != bucket_counts:
            errors.append("failure bucket counts differ from deterministic recomputation")
        statuses = {
            key: recomputed["hypotheses"]["hypotheses"][key]["status"] for key in HYPOTHESIS_IDS
        }
        if manifest.get("hypothesis_statuses") != statuses:
            errors.append("hypothesis statuses differ from deterministic recomputation")
        if manifest.get("source_fingerprints") != dict(sorted(recomputed["source_files"].items())):
            errors.append("source fingerprints differ from deterministic recomputation")
        with tempfile.TemporaryDirectory(prefix="far-ws1-verify-") as temporary:
            recomputed_dir = Path(temporary) / "bundle"
            _render_recomputed(recomputed_dir, recomputed)
            expected_artifacts = manifest.get("artifacts", {})
            if set(expected_artifacts) != RELEASE_FILES - {"manifest.json"}:
                errors.append("manifest artifact set is not exact")
            for name in sorted(RELEASE_FILES - {"manifest.json"}):
                observed_path = bundle_dir / name
                recomputed_path = recomputed_dir / name
                if not observed_path.is_file():
                    continue
                if sha256_file(observed_path) != expected_artifacts.get(name):
                    errors.append(f"artifact fingerprint mismatch: {name}")
                if observed_path.read_bytes() != recomputed_path.read_bytes():
                    errors.append(f"artifact differs from deterministic recomputation: {name}")
    try:
        buckets = read_jsonl(bundle_dir / "failure_buckets.jsonl")
        bucket_ids = [str(row["sample_id"]) for row in buckets]
        bucket_names = [str(row["primary_bucket"]) for row in buckets]
        if len(bucket_ids) != 226 or len(set(bucket_ids)) != 226:
            errors.append("G-R1 failure buckets do not uniquely cover 226 cases")
        if any(name not in BUCKET_PRIORITY for name in bucket_names):
            errors.append("G-R1 contains an unknown failure bucket")
        stratified = json.loads(
            (bundle_dir / "stratified_analysis.json").read_text(encoding="utf-8")
        )
        for key in ("retrieval", "conflict_detection"):
            if sum(int(row["samples"]) for row in stratified[key].values()) != 350:
                errors.append(f"G-R1 {key} strata do not cover 350 dev samples")
        hypotheses = json.loads((bundle_dir / "hypotheses.json").read_text(encoding="utf-8"))
        observed_hypotheses = hypotheses.get("hypotheses", {})
        if set(observed_hypotheses) != set(HYPOTHESIS_IDS):
            errors.append("G-R1 does not report all four preregistered hypotheses")
        allowed_statuses = {"supported", "not_supported", "indeterminate"}
        if any(row.get("status") not in allowed_statuses for row in observed_hypotheses.values()):
            errors.append("G-R1 contains an invalid hypothesis status")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    if not report_path.is_file():
        errors.append("external mechanism attribution report is missing")
    elif sha256_file(report_path) != manifest.get("external_report_sha256"):
        errors.append("external mechanism attribution report fingerprint mismatch")
    elif (bundle_dir / "mechanism_attribution.md").read_bytes() != report_path.read_bytes():
        errors.append("external report differs from the released report")
    return {
        "schema_version": "far-ws1-attribution-audit-v1",
        "valid": not errors,
        "errors": errors,
        "roadmap_fingerprint": ROADMAP_ACTIVE_SHA256,
        "gate_r1_passed": not errors,
        "model_calls": 0,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ramdocs-data-dir", type=Path, default=Path("bench/external/ramdocs_v1"))
    parser.add_argument("--round1-dir", type=Path, default=Path("diagnostics/ramdocs_v2/round1"))
    parser.add_argument("--round2-dir", type=Path, default=Path("diagnostics/ramdocs_v2/round2"))
    parser.add_argument(
        "--solo-suite-dir",
        type=Path,
        default=Path("diagnostics/solo_v1/experiments"),
    )
    parser.add_argument(
        "--machine-rows",
        type=Path,
        default=Path("diagnostics/solo_v1/machine_annotation/machine_consensus_rows.jsonl"),
    )
    parser.add_argument("--bundle-dir", type=Path, default=Path("diagnostics/attribution_v1"))
    parser.add_argument("--report", type=Path, default=Path("reports/mechanism_attribution.md"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    _add_common(build_parser)
    build_parser.add_argument("--analysis-freeze-commit", required=True)
    build_parser.add_argument("--resamples", type=int, default=2000)
    build_parser.add_argument("--seed", type=int, default=1729)
    verify_parser = subparsers.add_parser("verify")
    _add_common(verify_parser)
    args = parser.parse_args()
    if args.command == "build":
        result = build_bundle(
            ramdocs_data_dir=args.ramdocs_data_dir,
            round1_dir=args.round1_dir,
            round2_dir=args.round2_dir,
            solo_suite_dir=args.solo_suite_dir,
            machine_rows_path=args.machine_rows,
            output_dir=args.bundle_dir,
            report_path=args.report,
            analysis_freeze_commit=args.analysis_freeze_commit,
            resamples=args.resamples,
            seed=args.seed,
        )
    else:
        result = verify_bundle(
            ramdocs_data_dir=args.ramdocs_data_dir,
            round1_dir=args.round1_dir,
            round2_dir=args.round2_dir,
            solo_suite_dir=args.solo_suite_dir,
            machine_rows_path=args.machine_rows,
            bundle_dir=args.bundle_dir,
            report_path=args.report,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "verify" and result.get("valid") is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
