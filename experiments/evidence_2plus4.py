"""Build and verify fingerprinted RAMDocs and jury evidence releases."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.build.common import sha256_file, write_json
from experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256, verify_active_protocol
from experiments.ramdocs_suite import verify_suite


def _owned_replace(output_dir: Path, schema: str, overwrite: bool) -> None:
    if not output_dir.exists() or not any(output_dir.iterdir()):
        output_dir.mkdir(parents=True, exist_ok=True)
        return
    if not overwrite:
        raise FileExistsError(f"{output_dir} exists; pass --overwrite")
    marker = output_dir / "bundle_manifest.json"
    if not marker.is_file():
        raise ValueError("refusing to overwrite a directory without a bundle manifest")
    existing = json.loads(marker.read_text(encoding="utf-8"))
    if existing.get("schema_version") != schema:
        raise ValueError("refusing to overwrite a different evidence bundle schema")
    shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)


def _copy(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "bundle_manifest.json"
    }


def build_ramdocs_release(
    data_dir: Path,
    suite_dir: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    verify_active_protocol()
    source_audit = verify_suite(suite_dir, data_dir)
    if not source_audit["valid"]:
        raise ValueError(f"RAMDocs suite is invalid: {source_audit['errors']}")
    _owned_replace(output_dir, "far-ramdocs-evidence-release-v1", overwrite)
    manifest = json.loads((suite_dir / "suite_manifest.json").read_text(encoding="utf-8"))
    names = ["suite_manifest.json"]
    names.extend(
        f"initial_answers/{name}"
        for name in ("predictions.jsonl", "run_identity.json", "run_manifest.json")
    )
    for method in manifest["methods"]:
        names.extend(
            f"runs/{method}/{name}"
            for name in ("predictions.jsonl", "run_identity.json", "run_manifest.json")
        )
        names.extend(
            f"evaluations/{method}/{name}" for name in ("scores.jsonl", "report.json")
        )
        if method != "far":
            names.append(f"comparisons/far_vs_{method}.json")
    for name in names:
        _copy(suite_dir / name, output_dir / name)
    (output_dir / "README.md").write_text(
        "# RAMDocs external evidence release\n\n"
        "This fingerprinted bundle contains the complete preregistered RAMDocs split "
        "evaluation. RAMDocs supplies upstream labels but is not represented as "
        "independent human IAA or externally held blind evaluation.\n",
        encoding="utf-8",
    )
    bundle = {
        "schema_version": "far-ramdocs-evidence-release-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "study_profile": "external_upstream_labeled_evaluation",
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "split": manifest["split"],
        "samples": manifest["samples"],
        "methods": manifest["methods"],
        "gate_a_passed": manifest["gate_a_passed"],
        "publication_gold": False,
        "human_iaa": False,
        "externally_held": False,
        "files": _files(output_dir),
    }
    write_json(output_dir / "bundle_manifest.json", bundle)
    audit = verify_ramdocs_release(output_dir, data_dir)
    if not audit["valid"]:
        raise ValueError(f"created RAMDocs release is invalid: {audit['errors']}")
    return bundle


def verify_ramdocs_release(bundle_dir: Path, data_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        verify_active_protocol()
        manifest = json.loads((bundle_dir / "bundle_manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return {
            "schema_version": "far-ramdocs-evidence-release-audit-v1",
            "valid": False,
            "errors": [str(exc)],
        }
    if manifest.get("schema_version") != "far-ramdocs-evidence-release-v1":
        errors.append("unsupported RAMDocs evidence release schema")
    expected = manifest.get("files", {})
    if not isinstance(expected, dict) or expected != _files(bundle_dir):
        errors.append("RAMDocs evidence bundle file set or fingerprints differ")
    suite_audit = verify_suite(bundle_dir, data_dir)
    errors.extend(suite_audit.get("errors", []))
    if suite_audit.get("valid") is not True:
        errors.append("embedded RAMDocs suite is invalid")
    if manifest.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256:
        errors.append("RAMDocs evidence release uses a stale protocol")
    if manifest.get("publication_gold") is not False or manifest.get("human_iaa") is not False:
        errors.append("RAMDocs evidence release contains an unsafe provenance claim")
    return {
        "schema_version": "far-ramdocs-evidence-release-audit-v1",
        "valid": not errors,
        "errors": errors,
        "split": manifest.get("split"),
        "samples": manifest.get("samples"),
        "methods": len(manifest.get("methods", [])),
        "gate_a_passed": manifest.get("gate_a_passed"),
        "publication_gold": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build-ramdocs")
    build.add_argument("--data-dir", type=Path, required=True)
    build.add_argument("--suite-dir", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--overwrite", action="store_true")
    verify = subparsers.add_parser("verify-ramdocs")
    verify.add_argument("--data-dir", type=Path, required=True)
    verify.add_argument("--bundle-dir", type=Path, required=True)
    args = parser.parse_args()
    result = (
        build_ramdocs_release(
            args.data_dir,
            args.suite_dir,
            args.output_dir,
            overwrite=args.overwrite,
        )
        if args.command == "build-ramdocs"
        else verify_ramdocs_release(args.bundle_dir, args.data_dir)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "verify-ramdocs" and not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
