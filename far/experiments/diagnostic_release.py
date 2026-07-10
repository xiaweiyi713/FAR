"""Build and verify a public, non-publication FAR diagnostic evidence bundle."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from far.bench.build.build_blind_bundle import audit_bundle
from far.bench.build.common import sha256_file, write_json
from far.experiments.solo_readiness import ARTIFACT_LABELS, EXPECTED_METHODS, audit
from far.experiments.validate_results import validate_result_bundle

SCHEMA_VERSION = "far-solo-diagnostic-release-v1"
RUN_FILES = ("predictions.jsonl", "run_identity.json", "run_manifest.json")
EVALUATION_FILES = ("report.json", "scores.jsonl")


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _method_run_dir(root: Path, method: str) -> Path:
    label = ARTIFACT_LABELS.get(method, method)
    if method in {
        "vanilla",
        "multi_query_rag",
        "reflective_rag",
        "crag_style_reproduction",
        "self_rag_style_reproduction",
        "counterrefine_style_reproduction",
    }:
        return root / "runs" / "baselines" / label
    return root / "runs" / label


def _prepare_output(output_dir: Path, *, overwrite: bool) -> None:
    if not output_dir.exists():
        output_dir.mkdir(parents=True)
        return
    if not any(output_dir.iterdir()):
        return
    if not overwrite:
        raise FileExistsError(
            "diagnostic release directory must be empty unless --overwrite is used"
        )
    marker = output_dir / "bundle_manifest.json"
    if not marker.is_file() or _json(marker).get("schema_version") != SCHEMA_VERSION:
        raise ValueError("refusing to overwrite a directory not owned by FAR diagnostic release")
    shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)


def _copy(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _readme() -> str:
    return """# FAR single-author diagnostic evidence

This directory is a fingerprinted evidence bundle for the
`single_author_machine_audited_diagnostic` study profile.

It contains the complete 60-sample development predictions, evaluation scores,
reports, tables, figures, and the 300-row machine-label audit used by the public
diagnostic. Run `uv run falsirag-solo-release verify diagnostics/solo_v1` from
the repository root to verify every file and recompute all result-bundle checks.

Rebuild it from the ignored local evidence with:

```bash
uv run falsirag-solo-release build \\
  --data-dir bench \\
  --machine-report outputs/machine_consensus_v1/machine_consensus_report.json \\
  --suite-dir outputs/remote_qwen_six_baseline_suite \\
  --blind-bundle-dir outputs/handoff/falsirag_blind_test_technical_v1 \\
  --output-dir diagnostics/solo_v1 \\
  --overwrite
```

## Interpretation boundary

- These are development-set diagnostics over construction-derived labels.
- The benchmark has machine signals, not independent human gold.
- The test-bundle entry is only a gold-free local technical audit.
- This bundle is not an externally held blind test, human IAA, a multi-model
  result, or publication-ready evidence.
- Nothing here changes or satisfies the strict submission readiness gate.

The machine audit deliberately retains all 122 disputed rows and never rewrites
the construction-derived reference labels from machine agreement.
"""


def _source_artifact_files(suite_dir: Path) -> list[str]:
    artifact_dir = suite_dir / "artifacts"
    manifest = _json(artifact_dir / "artifact_manifest.json")
    if manifest.get("diagnostic_only") is not True:
        raise ValueError("source artifacts are not marked diagnostic-only")
    if manifest.get("publication_ready") is not False:
        raise ValueError("source artifacts incorrectly claim publication readiness")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        raise ValueError("source artifact manifest has no output fingerprints")
    for name, expected in outputs.items():
        path = artifact_dir / str(name)
        if sha256_file(path) != expected:
            raise ValueError(f"source artifact fingerprint mismatch: {name}")
    return ["artifact_manifest.json", *sorted(map(str, outputs))]


def build_solo_release(
    data_dir: Path,
    machine_report: Path,
    suite_dir: Path,
    blind_bundle_dir: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Export the already-audited local evidence without upgrading its claims."""

    readiness = audit(data_dir, machine_report, suite_dir, blind_bundle_dir)
    if readiness.get("complete") is not True:
        raise ValueError(f"solo diagnostic readiness failed: {readiness.get('blockers', [])}")
    artifact_files = _source_artifact_files(suite_dir)
    _prepare_output(output_dir, overwrite=overwrite)

    machine = _json(machine_report)
    machine_rows = machine_report.parent / str(machine["machine_consensus_rows"])
    _copy(machine_report, output_dir / "machine_annotation" / "machine_consensus_report.json")
    _copy(machine_rows, output_dir / "machine_annotation" / "machine_consensus_rows.jsonl")

    _copy(suite_dir / "suite_manifest.json", output_dir / "experiments" / "suite_manifest.json")
    for method in sorted(EXPECTED_METHODS):
        label = ARTIFACT_LABELS.get(method, method)
        source_run = _method_run_dir(suite_dir, method)
        destination_run = _method_run_dir(output_dir / "experiments", method)
        for name in RUN_FILES:
            _copy(source_run / name, destination_run / name)
        source_evaluation = suite_dir / "evaluations" / label
        destination_evaluation = output_dir / "experiments" / "evaluations" / label
        for name in EVALUATION_FILES:
            _copy(source_evaluation / name, destination_evaluation / name)

    for name in artifact_files:
        _copy(suite_dir / "artifacts" / name, output_dir / "experiments" / "artifacts" / name)

    blind_audit = audit_bundle(blind_bundle_dir, allow_technical=True)
    write_json(output_dir / "blind_test" / "technical_audit.json", blind_audit)
    write_json(output_dir / "solo_readiness.json", readiness)
    (output_dir / "README.md").write_text(_readme(), encoding="utf-8")

    files = {
        path.relative_to(output_dir).as_posix(): sha256_file(path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file()
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "study_profile": "single_author_machine_audited_diagnostic",
        "complete": True,
        "publication_ready": False,
        "publication_gold": False,
        "human_annotation_replaced": False,
        "can_report_human_iaa": False,
        "strict_submission_gate_affected": False,
        "samples": {"benchmark": 300, "dev": 60, "gold_free_test_inputs": 58},
        "methods": sorted(EXPECTED_METHODS),
        "files": files,
    }
    write_json(output_dir / "bundle_manifest.json", manifest)
    verified = verify_solo_release(output_dir)
    if verified.get("valid") is not True:
        raise ValueError(f"created diagnostic release failed verification: {verified['errors']}")
    return manifest


def verify_solo_release(bundle_dir: Path) -> dict[str, Any]:
    """Fail closed on missing, extra, stale, or claim-upgrading bundle content."""

    errors: list[str] = []
    try:
        manifest = _json(bundle_dir / "bundle_manifest.json")
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return {
            "schema_version": "far-solo-diagnostic-release-audit-v1",
            "valid": False,
            "errors": [str(exc)],
        }
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported bundle manifest schema")
    required_flags = {
        "complete": True,
        "publication_ready": False,
        "publication_gold": False,
        "human_annotation_replaced": False,
        "can_report_human_iaa": False,
        "strict_submission_gate_affected": False,
    }
    for key, expected in required_flags.items():
        if manifest.get(key) is not expected:
            errors.append(f"unsafe bundle claim flag: {key}")
    expected_files = manifest.get("files")
    if not isinstance(expected_files, dict):
        expected_files = {}
        errors.append("bundle manifest has no file map")
    actual_files = {
        path.relative_to(bundle_dir).as_posix()
        for path in bundle_dir.rglob("*")
        if path.is_file() and path.name != "bundle_manifest.json"
    }
    if set(expected_files) != actual_files:
        errors.append("bundle file set differs from manifest")
    for name, expected in expected_files.items():
        path = bundle_dir / str(name)
        if path.is_symlink():
            errors.append(f"bundle file must not be a symlink: {name}")
        elif path.is_file() and sha256_file(path) != expected:
            errors.append(f"bundle file fingerprint mismatch: {name}")

    try:
        readiness = _json(bundle_dir / "solo_readiness.json")
        if readiness.get("complete") is not True:
            errors.append("embedded solo readiness is incomplete")
        if readiness.get("strict_submission_gate_affected") is not False:
            errors.append("embedded readiness upgrades the strict gate")
        machine = _json(bundle_dir / "machine_annotation" / "machine_consensus_report.json")
        rows = bundle_dir / "machine_annotation" / "machine_consensus_rows.jsonl"
        if sha256_file(rows) != machine.get("machine_consensus_rows_sha256"):
            errors.append("embedded machine-consensus rows fingerprint mismatch")
        if machine.get("publication_gold") is not False:
            errors.append("embedded machine audit claims publication gold")

        suite = _json(bundle_dir / "experiments" / "suite_manifest.json")
        if suite.get("diagnostic_only") is not True or suite.get("allow_test") is not False:
            errors.append("embedded suite is not a dev-only diagnostic")
        for method in sorted(EXPECTED_METHODS):
            label = ARTIFACT_LABELS.get(method, method)
            run_dir = _method_run_dir(bundle_dir / "experiments", method)
            evaluation_dir = bundle_dir / "experiments" / "evaluations" / label
            validation = validate_result_bundle(run_dir, evaluation_dir)
            if not validation["valid"]:
                errors.append(f"{method}: invalid result bundle: {validation['errors']}")
            report_path = evaluation_dir / "report.json"
            report = _json(report_path)
            scores_path = evaluation_dir / "scores.jsonl"
            if report.get("provenance", {}).get("scores_sha256") != sha256_file(scores_path):
                errors.append(f"{method}: scores fingerprint mismatch")
            if suite.get("reports", {}).get(method) != sha256_file(report_path):
                errors.append(f"{method}: suite report fingerprint mismatch")

        artifact_dir = bundle_dir / "experiments" / "artifacts"
        artifact = _json(artifact_dir / "artifact_manifest.json")
        if (
            artifact.get("diagnostic_only") is not True
            or artifact.get("publication_ready") is not False
        ):
            errors.append("embedded artifacts are not marked diagnostic-only")
        for name, expected in artifact.get("outputs", {}).items():
            if sha256_file(artifact_dir / str(name)) != expected:
                errors.append(f"embedded artifact fingerprint mismatch: {name}")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))

    return {
        "schema_version": "far-solo-diagnostic-release-audit-v1",
        "valid": not errors,
        "errors": errors,
        "files": len(expected_files),
        "methods": len(EXPECTED_METHODS),
        "publication_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--data-dir", type=Path, default=Path("bench"))
    build_parser.add_argument("--machine-report", type=Path, required=True)
    build_parser.add_argument("--suite-dir", type=Path, required=True)
    build_parser.add_argument("--blind-bundle-dir", type=Path, required=True)
    build_parser.add_argument("--output-dir", type=Path, required=True)
    build_parser.add_argument("--overwrite", action="store_true")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("bundle_dir", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        result = build_solo_release(
            args.data_dir,
            args.machine_report,
            args.suite_dir,
            args.blind_bundle_dir,
            args.output_dir,
            overwrite=args.overwrite,
        )
    else:
        manifest_path = args.bundle_dir / "bundle_manifest.json"
        manifest = _json(manifest_path) if manifest_path.is_file() else {}
        if manifest.get("schema_version") == "far-ramdocs-evidence-release-v1":
            from far.experiments.evidence_2plus4 import verify_ramdocs_release

            result = verify_ramdocs_release(
                args.bundle_dir,
                Path("bench/external/ramdocs_v1"),
            )
        elif manifest.get("schema_version") == "far-jury-evidence-release-v1":
            from far.experiments.evidence_2plus4 import verify_jury_release

            result = verify_jury_release(args.bundle_dir, Path("bench"))
        else:
            result = verify_solo_release(args.bundle_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "verify" and not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
