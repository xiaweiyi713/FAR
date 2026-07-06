"""Build and verify fingerprinted RAMDocs and jury evidence releases."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.build.common import sha256_file, write_json
from bench.build.jury_adjudication import compile_jury_labels
from bench.build.jury_consensus import verify_jury_consensus
from experiments.jury_rescore import rescore_family
from experiments.jury_sensitivity import build_sensitivity
from experiments.model_matrix import build_matrix
from experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256, verify_active_protocol
from experiments.ramdocs_round2 import verify_round
from experiments.ramdocs_round2_error_analysis import verify_analysis
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
        if path.is_file() and path != root / "bundle_manifest.json"
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
        names.extend(f"evaluations/{method}/{name}" for name in ("scores.jsonl", "report.json"))
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


def build_ramdocs_round2_release(
    data_dir: Path,
    round1_dir: Path,
    round2_dir: Path,
    config_path: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    verify_active_protocol()
    source_audit = verify_round(data_dir, round1_dir, round2_dir, config_path)
    if source_audit.get("valid") is not True:
        raise ValueError(f"RAMDocs Round 2 is invalid: {source_audit.get('errors', [])}")
    decision = json.loads((round2_dir / "round_manifest.json").read_text(encoding="utf-8"))
    if decision.get("gate_a_passed") is False:
        analysis_audit = verify_analysis(
            data_dir,
            round1_dir,
            round2_dir,
            config_path,
            round2_dir / "error_analysis",
        )
        if analysis_audit.get("valid") is not True:
            raise ValueError(
                "failed G-A requires valid Round 2 error analysis: "
                f"{analysis_audit.get('errors', [])}"
            )
    _owned_replace(output_dir, "far-ramdocs-round2-evidence-release-v1", overwrite)
    shutil.copytree(round1_dir, output_dir / "round1", dirs_exist_ok=True)
    shutil.copytree(round2_dir, output_dir / "round2", dirs_exist_ok=True)
    _copy(config_path, output_dir / "round2" / "config.yaml")
    (output_dir / "README.md").write_text(
        "# RAMDocs dev Round 2 evidence release\n\n"
        "This bundle contains the complete frozen Round 1 suite and the dev-only Round 2 "
        "FAR method iteration. The strongest Round 1 baseline and initial answers are reused "
        "by SHA-256. It contains no RAMDocs test result, human IAA, or publication-grade "
        "human gold.\n",
        encoding="utf-8",
    )
    bundle = {
        "schema_version": "far-ramdocs-round2-evidence-release-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "study_profile": "external_upstream_labeled_dev_method_iteration",
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "round": 2,
        "split": "dev",
        "samples": 350,
        "gate_a_passed": decision.get("gate_a_passed"),
        "stop_rule_triggered": decision.get("stop_rule_triggered"),
        "paper_downgrade_required": decision.get("gate_a_passed") is False,
        "test_accessed": False,
        "publication_gold": False,
        "human_iaa": False,
        "externally_held": False,
        "files": _files(output_dir),
    }
    write_json(output_dir / "bundle_manifest.json", bundle)
    audit = verify_ramdocs_round2_release(output_dir, data_dir)
    if audit.get("valid") is not True:
        raise ValueError(f"created RAMDocs Round 2 release is invalid: {audit.get('errors', [])}")
    return bundle


def verify_ramdocs_round2_release(bundle_dir: Path, data_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        verify_active_protocol()
        manifest = json.loads((bundle_dir / "bundle_manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return {
            "schema_version": "far-ramdocs-round2-evidence-release-audit-v1",
            "valid": False,
            "errors": [str(exc)],
        }
    if manifest.get("schema_version") != "far-ramdocs-round2-evidence-release-v1":
        errors.append("unsupported RAMDocs Round 2 evidence release schema")
    if manifest.get("files") != _files(bundle_dir):
        errors.append("RAMDocs Round 2 bundle file set or fingerprints differ")
    audit = verify_round(
        data_dir,
        bundle_dir / "round1",
        bundle_dir / "round2",
        bundle_dir / "round2" / "config.yaml",
    )
    errors.extend(audit.get("errors", []))
    if audit.get("valid") is not True:
        errors.append("embedded RAMDocs Round 2 evidence is invalid")
    if manifest.get("gate_a_passed") is not audit.get("gate_a_passed"):
        errors.append("RAMDocs Round 2 bundle G-A state disagrees with its evidence")
    gate_a_passed = audit.get("gate_a_passed")
    if manifest.get("paper_downgrade_required") is not (gate_a_passed is False):
        errors.append("RAMDocs Round 2 paper downgrade state disagrees with G-A")
    if gate_a_passed is False:
        analysis_audit = verify_analysis(
            data_dir,
            bundle_dir / "round1",
            bundle_dir / "round2",
            bundle_dir / "round2" / "config.yaml",
            bundle_dir / "round2" / "error_analysis",
        )
        errors.extend(analysis_audit.get("errors", []))
        if analysis_audit.get("valid") is not True:
            errors.append("failed G-A bundle lacks valid Round 2 error analysis")
    if manifest.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256:
        errors.append("RAMDocs Round 2 release uses a stale protocol")
    if manifest.get("test_accessed") is not False:
        errors.append("RAMDocs Round 2 release must remain dev-only")
    if manifest.get("publication_gold") is not False or manifest.get("human_iaa") is not False:
        errors.append("RAMDocs Round 2 release contains an unsafe provenance claim")
    return {
        "schema_version": "far-ramdocs-round2-evidence-release-audit-v1",
        "valid": not errors,
        "errors": errors,
        "round": manifest.get("round"),
        "split": manifest.get("split"),
        "samples": manifest.get("samples"),
        "gate_a_passed": manifest.get("gate_a_passed"),
        "stop_rule_triggered": manifest.get("stop_rule_triggered"),
        "paper_downgrade_required": manifest.get("paper_downgrade_required"),
        "publication_gold": False,
    }


def build_jury_release(
    data_dir: Path,
    consensus_dir: Path,
    juror_dirs: dict[str, Path],
    adjudication_dir: Path,
    labels_dir: Path,
    sensitivity_dir: Path,
    suite_dirs: dict[str, Path],
    family_dirs: dict[str, Path],
    matrix_report: Path,
    output_dir: Path,
    *,
    falsirag_test_dir: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    verify_active_protocol()
    if len(juror_dirs) != 3:
        raise ValueError("jury release requires exactly three independent juror bundles")
    if any(
        not juror_id
        or Path(juror_id).name != juror_id
        or not juror_id.replace("-", "").replace("_", "").isalnum()
        for juror_id in juror_dirs
    ):
        raise ValueError("jury release juror IDs must be safe local names")
    if set(suite_dirs) != {"qwen", "mistral", "google"}:
        raise ValueError("jury release requires three preregistered source suites")
    if set(family_dirs) != {"qwen", "mistral", "google"}:
        raise ValueError("jury release requires qwen, mistral, and google family bundles")
    _owned_replace(output_dir, "far-jury-evidence-release-v1", overwrite)
    for source, name in (
        (consensus_dir, "consensus"),
        (adjudication_dir, "author_adjudication"),
        (labels_dir, "labels"),
        (sensitivity_dir, "qwen_sensitivity"),
    ):
        shutil.copytree(source, output_dir / name, dirs_exist_ok=True)
    for juror_id, source in sorted(juror_dirs.items()):
        shutil.copytree(source, output_dir / "jurors" / juror_id, dirs_exist_ok=True)
    for family, source in sorted(suite_dirs.items()):
        shutil.copytree(source, output_dir / "source_suites" / family, dirs_exist_ok=True)
    for family, source in sorted(family_dirs.items()):
        shutil.copytree(
            source,
            output_dir / "model_families" / family,
            dirs_exist_ok=True,
        )
    _copy(matrix_report, output_dir / "model_matrix.json")
    if falsirag_test_dir is not None:
        shutil.copytree(
            falsirag_test_dir,
            output_dir / "falsirag_test",
            dirs_exist_ok=True,
        )
    (output_dir / "README.md").write_text(
        "# FAR 2+4 jury evidence release\n\n"
        "This bundle contains cross-family LLM jury agreement, author-blind "
        "adjudication-derived labels, three-view sensitivity, and jury-gold model "
        "rescoring. `jury_gold` is not independent human gold or human IAA.\n",
        encoding="utf-8",
    )
    matrix = json.loads(matrix_report.read_text(encoding="utf-8"))
    labels = json.loads((labels_dir / "manifest.json").read_text(encoding="utf-8"))
    consensus = json.loads(
        (consensus_dir / "jury_consensus_report.json").read_text(encoding="utf-8")
    )
    manifest = {
        "schema_version": "far-jury-evidence-release-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "study_profile": "cross_family_llm_jury_plus_author_blind_adjudication",
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "gate_k_passed": consensus.get("gate_k_passed"),
        "gate_s_passed": labels.get("gate_s_passed"),
        "phase_b_gate": consensus.get("phase_b_gate"),
        "label_granularity": labels.get("label_granularity"),
        "three_family_claim_ready": matrix.get("three_family_claim_ready"),
        "juror_ids": sorted(juror_dirs),
        "system_families": sorted(family_dirs),
        "jury_gold": True,
        "publication_gold": False,
        "human_iaa": False,
        "externally_held": False,
        "files": _files(output_dir),
    }
    write_json(output_dir / "bundle_manifest.json", manifest)
    audit = verify_jury_release(output_dir, data_dir)
    if not audit["valid"]:
        raise ValueError(f"created jury release is invalid: {audit['errors']}")
    return manifest


def verify_jury_release(bundle_dir: Path, data_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        verify_active_protocol()
        manifest = json.loads((bundle_dir / "bundle_manifest.json").read_text(encoding="utf-8"))
        consensus = json.loads(
            (bundle_dir / "consensus/jury_consensus_report.json").read_text(encoding="utf-8")
        )
        labels = json.loads((bundle_dir / "labels/manifest.json").read_text(encoding="utf-8"))
        sensitivity = json.loads(
            (bundle_dir / "qwen_sensitivity/sensitivity_report.json").read_text(encoding="utf-8")
        )
        matrix = json.loads((bundle_dir / "model_matrix.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return {
            "schema_version": "far-jury-evidence-release-audit-v1",
            "valid": False,
            "errors": [str(exc)],
        }
    if manifest.get("schema_version") != "far-jury-evidence-release-v1":
        errors.append("unsupported jury evidence release schema")
    if manifest.get("files") != _files(bundle_dir):
        errors.append("jury evidence bundle file set or fingerprints differ")
    if manifest.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256:
        errors.append("jury release uses a stale protocol")
    juror_ids = [str(item) for item in manifest.get("juror_ids", [])]
    system_families = [str(item) for item in manifest.get("system_families", [])]
    if len(juror_ids) != 3 or len(set(juror_ids)) != 3:
        errors.append("jury release does not declare exactly three jurors")
    if set(system_families) != {"qwen", "mistral", "google"}:
        errors.append("jury release does not declare the three system families")
    juror_paths = [bundle_dir / "jurors" / juror_id for juror_id in juror_ids]
    if not all(path.is_dir() for path in juror_paths):
        errors.append("jury release is missing juror source directories")
    if consensus.get("gate_k_passed") is not True or consensus.get("zero_fallbacks") is not True:
        errors.append("embedded G-K evidence is not ready")
    if labels.get("gate_s_passed") is not True or labels.get("jury_gold") is not True:
        errors.append("embedded G-S/jury labels are not ready")
    if (
        not isinstance(manifest.get("phase_b_gate"), dict)
        or manifest.get("phase_b_gate") != consensus.get("phase_b_gate")
        or labels.get("phase_b_gate") != consensus.get("phase_b_gate")
    ):
        errors.append("jury release G-A authorization chain is missing or inconsistent")
    if sensitivity.get("schema_version") != "far-jury-label-sensitivity-v1":
        errors.append("embedded label sensitivity report is missing")
    if matrix.get("three_family_claim_ready") is not True:
        errors.append("embedded three-family matrix is not ready")
    try:
        consensus_audit = verify_jury_consensus(
            data_dir,
            juror_paths,
            bundle_dir / "consensus",
        )
        if consensus_audit.get("valid") is not True:
            errors.extend(
                f"jury consensus recomputation: {item}"
                for item in consensus_audit.get("errors", [])
            )
        with tempfile.TemporaryDirectory(prefix="far-jury-release-verify-") as temporary:
            temporary_root = Path(temporary)
            rebuilt_labels_dir = temporary_root / "labels"
            rebuilt_labels = compile_jury_labels(
                bundle_dir / "consensus",
                bundle_dir / "author_adjudication",
                juror_paths,
                rebuilt_labels_dir,
            )
            tracked_labels_path = bundle_dir / "labels" / str(labels["labels_file"])
            rebuilt_labels_path = rebuilt_labels_dir / str(rebuilt_labels["labels_file"])
            if (
                rebuilt_labels != labels
                or rebuilt_labels_path.read_bytes() != tracked_labels_path.read_bytes()
            ):
                errors.append("jury labels differ from consensus/adjudication recomputation")

            rebuilt_family_dirs: dict[str, Path] = {}
            for family in ("qwen", "mistral", "google"):
                rebuilt_dir = temporary_root / "model_families" / family
                rebuilt = rescore_family(
                    data_dir,
                    bundle_dir / "labels",
                    bundle_dir / "source_suites" / family,
                    rebuilt_dir,
                    family=family,
                    split="dev",
                )
                tracked = json.loads(
                    (
                        bundle_dir / "model_families" / family / "matrix_family_manifest.json"
                    ).read_text(encoding="utf-8")
                )
                if rebuilt != tracked:
                    errors.append(f"{family} jury rescore differs from recomputation")
                rebuilt_family_dirs[family] = rebuilt_dir

            rebuilt_sensitivity_dir = temporary_root / "qwen_sensitivity"
            rebuilt_sensitivity = build_sensitivity(
                data_dir,
                bundle_dir / "labels",
                bundle_dir / "consensus",
                bundle_dir / "source_suites" / "qwen",
                rebuilt_sensitivity_dir,
                family="qwen",
            )
            if rebuilt_sensitivity != sensitivity:
                errors.append("Qwen three-view sensitivity differs from recomputation")

            rebuilt_matrix = build_matrix(
                rebuilt_family_dirs,
                temporary_root / "model_matrix.json",
            )
            if rebuilt_matrix != matrix:
                errors.append("three-family model matrix differs from recomputation")
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        errors.append(f"jury evidence recomputation failed: {exc}")
    granularities = {
        consensus.get("active_label_granularity"),
        labels.get("label_granularity"),
        sensitivity.get("label_granularity"),
        matrix.get("label_granularity"),
        manifest.get("label_granularity"),
    }
    if len(granularities) != 1 or next(iter(granularities), None) not in {
        "six_class",
        "binary",
    }:
        errors.append("jury release mixes incompatible label granularities")
    else:
        expected_metric = (
            "conflict_presence_f1" if next(iter(granularities)) == "binary" else "typed_conflict_f1"
        )
        metric_mismatch = matrix.get("conflict_metric") != expected_metric
        sensitivity_mismatch = expected_metric not in sensitivity.get("metrics", [])
        if metric_mismatch or sensitivity_mismatch:
            errors.append("jury release conflict metric does not match label granularity")
    unsafe = any(
        item.get("publication_gold") is not False or item.get("human_iaa") is not False
        for item in (manifest, consensus, labels, sensitivity, matrix)
    )
    if unsafe:
        errors.append("jury release contains an unsafe human-gold claim")
    return {
        "schema_version": "far-jury-evidence-release-audit-v1",
        "valid": not errors,
        "errors": errors,
        "gate_k_passed": manifest.get("gate_k_passed"),
        "gate_s_passed": manifest.get("gate_s_passed"),
        "three_family_claim_ready": manifest.get("three_family_claim_ready"),
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
    build_round2 = subparsers.add_parser("build-ramdocs-round2")
    build_round2.add_argument("--data-dir", type=Path, required=True)
    build_round2.add_argument("--round1-dir", type=Path, required=True)
    build_round2.add_argument("--round2-dir", type=Path, required=True)
    build_round2.add_argument("--config", type=Path, required=True)
    build_round2.add_argument("--output-dir", type=Path, required=True)
    build_round2.add_argument("--overwrite", action="store_true")
    verify_round2 = subparsers.add_parser("verify-ramdocs-round2")
    verify_round2.add_argument("--data-dir", type=Path, required=True)
    verify_round2.add_argument("--bundle-dir", type=Path, required=True)
    build_jury = subparsers.add_parser("build-jury")
    build_jury.add_argument("--data-dir", type=Path, required=True)
    build_jury.add_argument("--consensus-dir", type=Path, required=True)
    build_jury.add_argument(
        "--juror-dir", action="append", nargs=2, metavar=("JUROR_ID", "PATH"), required=True
    )
    build_jury.add_argument("--adjudication-dir", type=Path, required=True)
    build_jury.add_argument("--labels-dir", type=Path, required=True)
    build_jury.add_argument("--sensitivity-dir", type=Path, required=True)
    build_jury.add_argument(
        "--suite-dir", action="append", nargs=2, metavar=("FAMILY", "PATH"), required=True
    )
    build_jury.add_argument(
        "--family-dir", action="append", nargs=2, metavar=("FAMILY", "PATH"), required=True
    )
    build_jury.add_argument("--matrix-report", type=Path, required=True)
    build_jury.add_argument("--falsirag-test-dir", type=Path)
    build_jury.add_argument("--output-dir", type=Path, required=True)
    build_jury.add_argument("--overwrite", action="store_true")
    verify_jury = subparsers.add_parser("verify-jury")
    verify_jury.add_argument("--data-dir", type=Path, required=True)
    verify_jury.add_argument("--bundle-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build-ramdocs":
        result = build_ramdocs_release(
            args.data_dir,
            args.suite_dir,
            args.output_dir,
            overwrite=args.overwrite,
        )
    elif args.command == "verify-ramdocs":
        result = verify_ramdocs_release(args.bundle_dir, args.data_dir)
    elif args.command == "build-ramdocs-round2":
        result = build_ramdocs_round2_release(
            args.data_dir,
            args.round1_dir,
            args.round2_dir,
            args.config,
            args.output_dir,
            overwrite=args.overwrite,
        )
    elif args.command == "verify-ramdocs-round2":
        result = verify_ramdocs_round2_release(args.bundle_dir, args.data_dir)
    elif args.command == "build-jury":
        result = build_jury_release(
            args.data_dir,
            args.consensus_dir,
            {str(juror_id): Path(path) for juror_id, path in args.juror_dir},
            args.adjudication_dir,
            args.labels_dir,
            args.sensitivity_dir,
            {str(family): Path(path) for family, path in args.suite_dir},
            {str(family): Path(path) for family, path in args.family_dir},
            args.matrix_report,
            args.output_dir,
            falsirag_test_dir=args.falsirag_test_dir,
            overwrite=args.overwrite,
        )
    else:
        result = verify_jury_release(args.bundle_dir, args.data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command.startswith("verify-") and not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
