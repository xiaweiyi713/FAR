"""Build and independently verify the portable no-human TMLR paper release."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "far-solo-paper-release-bundle-v2"
ARCHIVE_ROOT = "far-solo-paper-release"
DEFAULT_CHECKSUM_MANIFEST = Path("build/solo-paper-release/release-checksums.json")
DEFAULT_ARCHIVE = Path("build/solo-paper-release/far-solo-paper-release.tar.gz")
DEFAULT_STANDALONE_VERIFIER = Path("build/solo-paper-release/verify_solo_paper_release.py")
SOLO_PAPER_RELEASE_ARTIFACT_ROLES = frozenset(
    {
        "benchmark_validation_report",
        "cyclonedx_sbom",
        "sdist",
        "secret_scan_report",
        "solo_paper_readiness_json",
        "solo_paper_readiness_markdown",
        "tmlr_paper_pdf",
        "tmlr_source_lock",
        "wheel",
    }
)
TMLR_STYLE_COMMIT = "7bf90efe3a0debbba703c05c43f3ff7e4d4a2992"
BOUNDARY_FLAGS = {
    "paper_profile_ready": True,
    "strict_submission_ready": False,
    "human_review": False,
    "human_adjudication": False,
    "human_iaa": False,
    "external_blindness": False,
    "publication_gold": False,
}
ALLOWED_CLAIM = (
    "Across eight RAMDocs development methods, errors concentrate after retrieved evidence "
    "and answer transformation; FAR shows a narrower machine-audited typed-control signal "
    "whose transport and ontology stability are explicitly bounded."
)
REQUIRED_LIMITATIONS = (
    "labels are not human-validated gold",
    "evaluation is not externally blind",
    "the broad baseline delta ranking is Qwen-only and does not establish multi-model generality",
    "refutation and boundary query ablations do not support positive marginal claims",
    "typed revision trades lower answer correctness for non-zero revision behavior",
    "revision-delta metrics are post-hoc lexical diagnostics, not semantic correctness",
    "revision traces frequently miss the construction target or add collateral edits",
    "selective revision feasibility is post-hoc and does not evaluate a deployable selector",
    "raw baseline revision delta exceeds FAR despite zero typed action-conditioned delta",
    "FEVER binary transfer shows no paired accuracy gain",
    "machine-disposition sensitivity is post-hoc and not independent label validation",
    "cross-method trace attribution does not identify detection or action causal gaps",
    "P5 uses upstream-labelled development evidence and H3 remains uncertain",
    "P6-M is machine-panel sensitivity, not population type mappability",
    "the strict human P6 analysis was not completed",
)
FORBIDDEN_CLAIMS = (
    "human inter-annotator agreement",
    "human adjudication",
    "externally held blind test",
    "publication-grade benchmark gold",
    "positive marginal contribution from every FAR component",
    "multi-model or external-domain generality",
    "H3 equivalence or H4 confirmation",
    "P6-M as human review, human adjudication, or human IAA",
    "population mappability estimated from the 15 machine-consensus rows",
)
READINESS_GATES = {
    "claim_scope_matches_observed_ablations": True,
    "frozen_fever_negative_transfer_disclosed": True,
    "tracked_registered_p5_report": True,
    "tracked_solo_evidence": True,
    "tracked_stage_trace_map": True,
    "verified_p6m_negative_stability_audit": True,
    "verified_post_hoc_family_revision_delta": True,
    "verified_post_hoc_revision_trace_fidelity": True,
    "verified_post_hoc_selective_revision_feasibility": True,
}
CLAIM_SCOPE_CHECKS = frozenset(
    {
        "boundary_ablation_not_positive",
        "far_exceeds_all_six_baselines_on_answer",
        "raw_baseline_delta_exceeds_far",
        "refutation_ablation_delta_exceeds_far",
        "refutation_ablation_not_positive",
        "typed_answer_advantage",
        "typed_answer_advantage_same_direction_by_machine_disposition",
        "typed_conflict_f1_advantage",
        "typed_conflict_revision_delta_advantage",
        "typed_conflict_typed_delta_advantage",
        "typed_revision_accuracy_advantage",
        "typed_revision_answer_tradeoff",
        "typed_revision_delta_advantage",
    }
)
CLAIM_SCOPE_OBSERVED_KEYS = frozenset(
    {
        "best_baseline_revision_delta_f1",
        "far_answer_correctness",
        "far_revision_delta_f1",
        "far_typed_revision_delta_f1",
        "minus_boundary_answer_correctness",
        "minus_refutation_answer_correctness",
        "minus_refutation_revision_delta_f1",
        "minus_typed_revision_answer_correctness",
        "minus_typed_revision_revision_accuracy",
        "minus_typed_revision_revision_delta_f1",
        "typed_minus_untyped_answer_correctness",
        "typed_minus_untyped_conflict_f1",
        "typed_minus_untyped_revision_accuracy",
        "typed_minus_untyped_revision_delta_f1",
        "typed_minus_untyped_typed_revision_delta_f1",
    }
)
FAMILY_DELTA_CHECKS = {
    "frozen_release_valid": True,
    "post_hoc_boundary": True,
    "raw_direction_recurs": True,
    "typed_direction_recurs": True,
}
TRACE_FIDELITY_CHECKS = {
    "absolute_fidelity_bounded": True,
    "deterministic_report_valid": True,
    "family_trace_direction_recurs": True,
    "post_hoc_boundary": True,
    "typed_trace_direction_positive_but_hit_not_improved": True,
}
TRACE_FIDELITY_BOUNDARIES = {
    "causal_attribution": False,
    "construction_reference_dependent": True,
    "human_iaa": False,
    "human_review": False,
    "model_calls": 0,
    "post_hoc": True,
    "preregistered_primary": False,
    "publication_gold": False,
    "semantic_correctness": False,
    "test_accessed": False,
}
SELECTIVE_REVISION_CHECKS = {
    "confidence_not_fidelity_selector": True,
    "deterministic_report_valid": True,
    "post_hoc_non_policy_boundary": True,
    "selection_headroom_bounded": True,
    "whole_answer_gate_invalidated": True,
}
SELECTIVE_REVISION_BOUNDARIES = {
    "counterfactual_policy_effect": False,
    "deployable_selector_evaluated": False,
    "human_iaa": False,
    "human_review": False,
    "independent_arm_runs": True,
    "model_calls": 0,
    "post_hoc": True,
    "preregistered_primary": False,
    "preserve_output_generated": False,
    "prospective_confidence_calibration": False,
    "publication_gold": False,
    "reference_dependent": True,
    "registered_policy_utility": False,
    "semantic_correctness": False,
    "test_accessed": False,
}
READINESS_TOP_LEVEL_KEYS = frozenset(
    {
        "allowed_claim",
        "claim_scope",
        "evidence",
        "forbidden_claims",
        "gates",
        "ready",
        "required_limitations",
        "schema_version",
        "strict_aaai_submission_ready",
        "study_profile",
    }
)
SUPPORT_PATHS = {
    "release_checksums": f"{ARCHIVE_ROOT}/release-checksums.json",
    "readme": f"{ARCHIVE_ROOT}/README.md",
    "standalone_verifier": f"{ARCHIVE_ROOT}/verify_solo_paper_release.py",
}
MANIFEST_PATH = f"{ARCHIVE_ROOT}/bundle-manifest.json"
MAX_ARCHIVE_MEMBERS = 64
MAX_COMPRESSED_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_PACKAGE_MEMBERS = 4096
MAX_PACKAGE_EXPANDED_BYTES = 512 * 1024 * 1024


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verifier_bytes() -> bytes:
    return Path(__file__).read_bytes()


def _readme() -> bytes:
    return b"""# FAR no-human TMLR paper release

This portable archive contains the complete `solo-paper` checksum profile:
the wheel, source distribution, CycloneDX SBOM, benchmark and redacted secret
scan reports, JSON and Markdown paper-readiness reports, the active anonymous
TMLR PDF, and its source lock.

Verify the archive with the paired standard-library-only sidecar; no FAR
checkout, package installation, network, or model runtime is required:

```bash
python -I verify_solo_paper_release.py verify \\
  --archive far-solo-paper-release.tar.gz
```

The verifier reads only itself and this archive. It requires its embedded copy
to be byte-identical, then rejects missing or extra members, links, unsafe
paths, hash changes, source-lock mismatches, and any upgrade to human review,
adjudication, IAA, external blindness, publication gold, or strict submission
readiness. This is a machine-audited development paper release, not a
strict-human or externally blind publication package.
"""


def _tar_info(name: str, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = 0o644
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def _write_archive(
    archive: Path,
    source_files: dict[str, Path],
    generated_files: dict[str, bytes],
) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as temporary:
        tar_path = Path(temporary.name)
    try:
        with tarfile.open(tar_path, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for name in sorted(set(source_files) | set(generated_files)):
                if name in source_files:
                    path = source_files[name]
                    with path.open("rb") as handle:
                        tar.addfile(_tar_info(name, path.stat().st_size), handle)
                else:
                    payload = generated_files[name]
                    with tempfile.SpooledTemporaryFile() as handle:
                        handle.write(payload)
                        handle.seek(0)
                        tar.addfile(_tar_info(name, len(payload)), handle)
        with (
            tar_path.open("rb") as raw,
            archive.open("wb") as destination,
            gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=destination,
                compresslevel=9,
                mtime=0,
            ) as compressed,
        ):
            shutil.copyfileobj(raw, compressed, length=1024 * 1024)
    finally:
        tar_path.unlink(missing_ok=True)


def _safe_original_path(raw: Any) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError("release artifact path is missing")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe release artifact path: {raw}")
    return raw


def _artifact_archive_path(role: str, original_path: str) -> str:
    filename = PurePosixPath(original_path).name
    if not filename:
        raise ValueError(f"release artifact has no filename: {original_path}")
    return f"{ARCHIVE_ROOT}/artifacts/{role}/{filename}"


def _build_inventory(
    root: Path,
    checksum_path: Path,
) -> tuple[dict[str, Any], dict[str, Path], dict[str, bytes]]:
    from far.experiments.generate_release_checksums import (
        SOLO_PAPER_RELEASE_ARTIFACT_ROLES as CANONICAL_SOLO_PAPER_ROLES,
    )
    from far.experiments.generate_release_checksums import validate_checksum_manifest

    if SOLO_PAPER_RELEASE_ARTIFACT_ROLES != CANONICAL_SOLO_PAPER_ROLES:
        raise ValueError("standalone solo-paper roles differ from the checksum profile")
    audit = validate_checksum_manifest(
        checksum_path,
        project_root=root,
        required_profile="solo-paper",
    )
    if not audit.valid:
        raise ValueError(f"solo-paper checksum audit failed: {list(audit.errors)}")
    checksums = _json(checksum_path)
    revision = checksums.get("source_revision")
    if (
        not isinstance(revision, dict)
        or not re.fullmatch(r"[0-9a-f]{40}", str(revision.get("git_commit", "")))
        or revision.get("git_dirty") is not False
    ):
        raise ValueError("solo-paper bundle requires a clean 40-hex Git source revision")

    artifacts: list[dict[str, Any]] = []
    source_files: dict[str, Path] = {}
    observed_roles: set[str] = set()
    for item in checksums.get("artifacts", []):
        if not isinstance(item, dict):
            raise ValueError("release checksum artifact must be an object")
        role = item.get("role")
        if not isinstance(role, str) or role not in SOLO_PAPER_RELEASE_ARTIFACT_ROLES:
            raise ValueError(f"unexpected solo-paper artifact role: {role!r}")
        if role in observed_roles:
            raise ValueError(f"duplicate solo-paper artifact role: {role}")
        observed_roles.add(role)
        original_path = _safe_original_path(item.get("path"))
        source = root / original_path
        archive_path = _artifact_archive_path(role, original_path)
        entry = {
            "role": role,
            "original_path": original_path,
            "archive_path": archive_path,
            "bytes": item.get("bytes"),
            "sha256": item.get("sha256"),
        }
        if entry["bytes"] != source.stat().st_size or entry["sha256"] != sha256_file(source):
            raise ValueError(f"artifact changed after checksum validation: {role}")
        artifacts.append(entry)
        source_files[archive_path] = source
    if observed_roles != set(SOLO_PAPER_RELEASE_ARTIFACT_ROLES):
        missing = sorted(set(SOLO_PAPER_RELEASE_ARTIFACT_ROLES) - observed_roles)
        raise ValueError(f"solo-paper checksum roles are incomplete: {missing}")

    checksum_bytes = checksum_path.read_bytes()
    readme_bytes = _readme()
    verifier_bytes = _verifier_bytes()
    support_files = [
        {
            "role": "release_checksums",
            "archive_path": SUPPORT_PATHS["release_checksums"],
            "bytes": len(checksum_bytes),
            "sha256": _sha256_bytes(checksum_bytes),
        },
        {
            "role": "readme",
            "archive_path": SUPPORT_PATHS["readme"],
            "bytes": len(readme_bytes),
            "sha256": _sha256_bytes(readme_bytes),
        },
        {
            "role": "standalone_verifier",
            "archive_path": SUPPORT_PATHS["standalone_verifier"],
            "bytes": len(verifier_bytes),
            "sha256": _sha256_bytes(verifier_bytes),
        },
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "release_profile": "solo-paper",
        "study_profile": "single_author_machine_audited_paper",
        "source_revision": revision,
        "boundary_flags": BOUNDARY_FLAGS,
        "artifact_count": len(artifacts),
        "artifacts": sorted(artifacts, key=lambda item: str(item["role"])),
        "support_files": support_files,
    }
    generated_files = {
        MANIFEST_PATH: _json_bytes(manifest),
        SUPPORT_PATHS["release_checksums"]: checksum_bytes,
        SUPPORT_PATHS["readme"]: readme_bytes,
        SUPPORT_PATHS["standalone_verifier"]: verifier_bytes,
    }
    return manifest, source_files, generated_files


def pack_bundle(
    project_root: Path,
    checksum_manifest: Path,
    archive: Path,
    standalone_verifier: Path | None = None,
) -> dict[str, Any]:
    """Create a deterministic portable archive from a valid clean-commit profile."""

    root = project_root.resolve()
    checksum_path = checksum_manifest
    if not checksum_path.is_absolute():
        checksum_path = root / checksum_path
    manifest, source_files, generated_files = _build_inventory(root, checksum_path)
    _write_archive(archive, source_files, generated_files)
    verification = verify_bundle(archive)
    if verification.get("valid") is not True:
        raise ValueError(
            f"created solo-paper archive failed verification: {verification['errors']}"
        )
    verifier_bytes = generated_files[SUPPORT_PATHS["standalone_verifier"]]
    if standalone_verifier is not None:
        standalone_verifier.parent.mkdir(parents=True, exist_ok=True)
        standalone_verifier.write_bytes(verifier_bytes)
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": True,
        "archive": str(archive),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": sha256_file(archive),
        "artifact_count": manifest["artifact_count"],
        "source_revision": manifest["source_revision"],
        "boundary_flags": manifest["boundary_flags"],
        "standalone_verifier": (
            str(standalone_verifier) if standalone_verifier is not None else None
        ),
        "standalone_verifier_bytes": len(verifier_bytes),
        "standalone_verifier_sha256": _sha256_bytes(verifier_bytes),
    }


def _member_payloads(archive: Path) -> tuple[dict[str, bytes], list[str]]:
    errors: list[str] = []
    payloads: dict[str, bytes] = {}
    if archive.is_file() and archive.stat().st_size > MAX_COMPRESSED_BYTES:
        return {}, ["archive compressed size exceeds the safety limit"]
    try:
        with tarfile.open(archive, mode="r|gz") as tar:
            names: set[str] = set()
            member_count = 0
            total_bytes = 0
            for member in tar:
                member_count += 1
                if member_count > MAX_ARCHIVE_MEMBERS:
                    errors.append("archive contains too many members")
                    break
                if member.name in names:
                    errors.append("archive contains duplicate member names")
                names.add(member.name)
                path = PurePosixPath(member.name)
                if (
                    not member.isfile()
                    or path.is_absolute()
                    or ".." in path.parts
                    or not path.parts
                    or path.parts[0] != ARCHIVE_ROOT
                ):
                    errors.append(f"unsafe archive member: {member.name}")
                    continue
                if member.size < 0 or member.size > MAX_MEMBER_BYTES:
                    errors.append(f"archive member is too large: {member.name}")
                    break
                if total_bytes + member.size > MAX_TOTAL_BYTES:
                    errors.append("archive expanded size exceeds the safety limit")
                    break
                total_bytes += member.size
                extracted = tar.extractfile(member)
                if extracted is None:
                    errors.append(f"archive member is unreadable: {member.name}")
                    continue
                payload = extracted.read()
                if len(payload) != member.size:
                    errors.append(f"archive member is truncated: {member.name}")
                    continue
                payloads[member.name] = payload
    except (EOFError, OSError, tarfile.TarError, zlib.error) as exc:
        errors.append(str(exc))
    return payloads, errors


def _parse_json_payload(payloads: dict[str, bytes], path: str) -> Any:
    return json.loads(payloads[path].decode("utf-8"))


def _verify_manifest_shape(manifest: Any, errors: list[str]) -> tuple[list[Any], list[Any]]:
    if not isinstance(manifest, dict):
        errors.append("bundle manifest must be a JSON object")
        return [], []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported solo-paper bundle schema")
    if manifest.get("release_profile") != "solo-paper":
        errors.append("bundle release profile is not solo-paper")
    if manifest.get("study_profile") != "single_author_machine_audited_paper":
        errors.append("bundle study profile is unsafe")
    if manifest.get("boundary_flags") != BOUNDARY_FLAGS:
        errors.append("bundle boundary flags were upgraded or changed")
    revision = manifest.get("source_revision")
    if (
        not isinstance(revision, dict)
        or set(revision) != {"git_commit", "git_dirty"}
        or not re.fullmatch(r"[0-9a-f]{40}", str(revision.get("git_commit", "")))
        or revision.get("git_dirty") is not False
    ):
        errors.append("bundle source revision is not a clean 40-hex Git commit")
    artifacts = manifest.get("artifacts")
    supports = manifest.get("support_files")
    if not isinstance(artifacts, list):
        errors.append("bundle artifact list is missing")
        artifacts = []
    if not isinstance(supports, list):
        errors.append("bundle support-file list is missing")
        supports = []
    if manifest.get("artifact_count") != len(artifacts):
        errors.append("bundle artifact count mismatch")
    return artifacts, supports


def _verify_entry(
    entry: Any,
    payloads: dict[str, bytes],
    errors: list[str],
    *,
    support: bool = False,
) -> tuple[str | None, str | None]:
    if not isinstance(entry, dict):
        errors.append("bundle inventory entry must be an object")
        return None, None
    role = entry.get("role")
    path = entry.get("archive_path")
    if not isinstance(role, str) or not isinstance(path, str):
        errors.append("bundle inventory entry is missing role or archive path")
        return None, None
    if not support:
        original = entry.get("original_path")
        try:
            canonical_path = _artifact_archive_path(role, _safe_original_path(original))
        except ValueError as exc:
            errors.append(str(exc))
            canonical_path = None
        if path != canonical_path:
            errors.append(f"noncanonical archive path for role: {role}")
    payload = payloads.get(path)
    if payload is None:
        errors.append(f"archive member is missing: {path}")
        return role, path
    if entry.get("bytes") != len(payload):
        errors.append(f"archive member size mismatch: {path}")
    if entry.get("sha256") != _sha256_bytes(payload):
        errors.append(f"archive member fingerprint mismatch: {path}")
    return role, path


def _verify_standalone_identity(payloads: dict[str, bytes], errors: list[str]) -> None:
    if __package__ not in {None, ""}:
        return
    if sys.flags.isolated != 1:
        errors.append("standalone verifier must run in Python isolated mode (-I)")
    loaded_far_modules = sorted(
        name for name in sys.modules if name == "far" or name.startswith("far.")
    )
    if loaded_far_modules:
        errors.append("standalone verifier loaded FAR package modules")
    try:
        executing_verifier = _verifier_bytes()
    except OSError as exc:
        errors.append(f"executing standalone verifier is unreadable: {exc}")
        return
    if payloads.get(SUPPORT_PATHS["standalone_verifier"]) != executing_verifier:
        errors.append("embedded standalone verifier differs from executing verifier")


def _lock_values(payload: bytes) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in payload.decode("utf-8").splitlines():
        key, separator, value = line.partition("=")
        if not separator or not key or key in values:
            raise ValueError("TMLR source lock is malformed")
        values[key] = value
    return values


def _verify_python_archives(payload_by_role: dict[str, bytes], errors: list[str]) -> None:
    wheel = payload_by_role["wheel"]
    try:
        with zipfile.ZipFile(io.BytesIO(wheel)) as package:
            members = package.infolist()
            safe_to_read = True
            if (
                not members
                or not any(not zip_member.is_dir() for zip_member in members)
                or len(members) > MAX_PACKAGE_MEMBERS
            ):
                errors.append("embedded wheel has an invalid member count")
                safe_to_read = False
            expanded = 0
            for zip_member in members:
                path = PurePosixPath(zip_member.filename)
                expanded += zip_member.file_size
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or not path.parts
                    or stat.S_ISLNK(zip_member.external_attr >> 16)
                ):
                    errors.append(f"embedded wheel has an unsafe member: {zip_member.filename}")
                if zip_member.file_size > MAX_MEMBER_BYTES:
                    errors.append(f"embedded wheel member is too large: {zip_member.filename}")
                    safe_to_read = False
                if expanded > MAX_PACKAGE_EXPANDED_BYTES:
                    errors.append("embedded wheel expanded size exceeds the safety limit")
                    safe_to_read = False
                    break
            if safe_to_read and package.testzip() is not None:
                errors.append("embedded wheel has a corrupt member")
    except (
        EOFError,
        NotImplementedError,
        OSError,
        RuntimeError,
        zipfile.BadZipFile,
        zlib.error,
    ) as exc:
        errors.append(f"embedded wheel is not a valid ZIP archive: {exc}")

    sdist = payload_by_role["sdist"]
    try:
        with tarfile.open(fileobj=io.BytesIO(sdist), mode="r|gz") as package:
            count = 0
            file_count = 0
            expanded = 0
            for tar_member in package:
                count += 1
                path = PurePosixPath(tar_member.name)
                if count > MAX_PACKAGE_MEMBERS:
                    errors.append("embedded source distribution has too many members")
                    break
                if (
                    not (tar_member.isfile() or tar_member.isdir())
                    or path.is_absolute()
                    or ".." in path.parts
                    or not path.parts
                ):
                    errors.append(
                        f"embedded source distribution has an unsafe member: {tar_member.name}"
                    )
                    continue
                if tar_member.isdir():
                    continue
                if tar_member.size < 0 or tar_member.size > MAX_MEMBER_BYTES:
                    errors.append(
                        f"embedded source distribution member is too large: {tar_member.name}"
                    )
                    break
                file_count += 1
                expanded += tar_member.size
                if expanded > MAX_PACKAGE_EXPANDED_BYTES:
                    errors.append(
                        "embedded source distribution expanded size exceeds the safety limit"
                    )
                    break
                extracted = package.extractfile(tar_member)
                if extracted is None or len(extracted.read()) != tar_member.size:
                    errors.append(
                        f"embedded source distribution member is unreadable: {tar_member.name}"
                    )
            if file_count == 0:
                errors.append("embedded source distribution is empty")
    except (EOFError, OSError, tarfile.TarError, zlib.error) as exc:
        errors.append(f"embedded source distribution is not a valid gzip tar: {exc}")


def _verify_semantics(payload_by_role: dict[str, bytes], checksums: Any, errors: list[str]) -> None:
    try:
        readiness = json.loads(payload_by_role["solo_paper_readiness_json"])
        if not isinstance(readiness, dict):
            raise TypeError("paper readiness is not an object")
        if readiness.get("ready") is not True:
            errors.append("embedded paper profile is not ready")
        if readiness.get("schema_version") != "far-solo-paper-readiness-v5":
            errors.append("embedded paper readiness schema is unsupported")
        if readiness.get("strict_aaai_submission_ready") is not False:
            errors.append("embedded paper profile upgrades strict submission readiness")
        if readiness.get("study_profile") != "single_author_machine_audited_paper":
            errors.append("embedded paper readiness has the wrong study profile")
        if set(readiness) != READINESS_TOP_LEVEL_KEYS:
            errors.append("embedded paper readiness has unexpected top-level fields")
        if readiness.get("allowed_claim") != ALLOWED_CLAIM:
            errors.append("embedded paper readiness changed the allowed claim")
        if tuple(readiness.get("required_limitations", ())) != REQUIRED_LIMITATIONS:
            errors.append("embedded paper readiness changed the required limitations")
        if tuple(readiness.get("forbidden_claims", ())) != FORBIDDEN_CLAIMS:
            errors.append("embedded paper readiness changed the forbidden claims")
        if readiness.get("gates") != READINESS_GATES:
            errors.append("embedded paper readiness changed the release gates")
        claim_scope = readiness.get("claim_scope")
        if not isinstance(claim_scope, dict):
            raise TypeError("paper readiness claim scope is not an object")
        claim_checks = claim_scope.get("checks")
        if (
            claim_scope.get("valid") is not True
            or claim_scope.get("missing_required_disclosures") != []
            or claim_scope.get("forbidden_stale_claims") != []
            or not isinstance(claim_checks, dict)
            or set(claim_checks) != CLAIM_SCOPE_CHECKS
            or any(value is not True for value in claim_checks.values())
        ):
            errors.append("embedded paper claim-scope audit is unsafe")
        claim_observed = claim_scope.get("observed")
        if (
            not isinstance(claim_observed, dict)
            or set(claim_observed) != CLAIM_SCOPE_OBSERVED_KEYS
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in claim_observed.values()
            )
        ):
            errors.append("embedded paper claim-scope observations are incomplete")
        elif not (
            claim_observed["typed_minus_untyped_answer_correctness"] > 0
            and claim_observed["typed_minus_untyped_conflict_f1"] > 0
            and claim_observed["typed_minus_untyped_revision_accuracy"] > 0
            and claim_observed["typed_minus_untyped_revision_delta_f1"] > 0
            and claim_observed["typed_minus_untyped_typed_revision_delta_f1"] > 0
            and claim_observed["far_revision_delta_f1"]
            > claim_observed["minus_typed_revision_revision_delta_f1"]
            and claim_observed["best_baseline_revision_delta_f1"]
            > claim_observed["far_revision_delta_f1"]
            and claim_observed["minus_refutation_revision_delta_f1"]
            > claim_observed["far_revision_delta_f1"]
            and claim_observed["minus_refutation_answer_correctness"]
            >= claim_observed["far_answer_correctness"]
            and claim_observed["minus_boundary_answer_correctness"]
            >= claim_observed["far_answer_correctness"]
            and claim_observed["minus_typed_revision_answer_correctness"]
            > claim_observed["far_answer_correctness"]
            and claim_observed["minus_typed_revision_revision_accuracy"] == 0.0
        ):
            errors.append("embedded paper claim-scope observations contradict the audit")
        evidence = readiness.get("evidence")
        if not isinstance(evidence, dict):
            raise TypeError("paper readiness evidence is not an object")
        p6m = evidence.get("p6m_machine_ontology_stability")
        p5 = evidence.get("p5_registered_ablations")
        if not isinstance(p5, dict) or not isinstance(p6m, dict):
            raise TypeError("paper readiness P5/P6-M evidence is not an object")
        if (
            p5.get("valid") is not True
            or p5.get("samples") != 350
            or p5.get("h3_verdict") != "uncertain"
            or p5.get("h5_verdict") != "equivalent"
            or p5.get("raw_outputs_recomputed_by_this_gate") is not False
        ):
            errors.append("embedded P5 verdicts or recomputation boundary are unsafe")
        if (
            p6m.get("valid") is not True
            or p6m.get("schema_version") != "far-p6m-report-audit-v1"
            or p6m.get("study_profile") != "machine_ontology_stability_audit"
            or p6m.get("retrospective") is not True
            or p6m.get("samples") != 217
            or p6m.get("consensus_samples") != 15
            or p6m.get("dispositions") != {"unanimous": 1, "majority": 14, "contested": 202}
            or p6m.get("association_estimable") is not False
        ):
            errors.append("embedded P6-M negative stability result is incomplete")
        for field in (
            "human_annotation_replaced",
            "human_iaa_computed",
            "human_identity_verified",
            "publication_gold",
            "confirmatory_h4",
            "test_accessed",
        ):
            if p6m.get(field) is not False:
                errors.append(f"embedded P6-M boundary is unsafe: {field}")

        family_delta = evidence.get("family_revision_delta_sensitivity")
        if not isinstance(family_delta, dict):
            raise TypeError("paper readiness family revision-delta evidence is not an object")
        if (
            family_delta.get("valid") is not True
            or family_delta.get("schema_version") != "far-family-dev-release-audit-v1"
            or family_delta.get("required_claim_level") != "directional_reproduction"
            or family_delta.get("direction_consistent") is not True
            or family_delta.get("gate_f_passed") is not True
            or family_delta.get("gate_p_completed") is not True
            or family_delta.get("checks") != FAMILY_DELTA_CHECKS
            or family_delta.get("errors") != []
            or family_delta.get("human_iaa") is not False
            or family_delta.get("publication_gold") is not False
            or family_delta.get("test_accessed") is not False
        ):
            errors.append("embedded family revision-delta evidence is incomplete")
        family_post_hoc = family_delta.get("post_hoc_revision_delta")
        if not isinstance(family_post_hoc, dict):
            raise TypeError("paper readiness post-hoc revision-delta evidence is not an object")
        if (
            family_post_hoc.get("metric_profile") != "falsirag-evaluation-metrics-v2-revision-delta"
            or family_post_hoc.get("model_calls") != 0
            or family_post_hoc.get("preregistered_primary") is not False
            or family_post_hoc.get("test_accessed") is not False
        ):
            errors.append("embedded family revision-delta boundary is unsafe")
        for name, metric in (
            ("raw", "typed_minus_untyped_revision_delta_f1"),
            ("typed", "typed_minus_untyped_typed_revision_delta_f1"),
        ):
            result = family_post_hoc.get(name)
            bootstrap = result.get("family_cluster_bootstrap") if isinstance(result, dict) else None
            if (
                not isinstance(result, dict)
                or result.get("metric") != metric
                or result.get("positive_families") != 3
                or isinstance(result.get("combined_delta"), bool)
                or not isinstance(result.get("combined_delta"), (int, float))
                or not math.isfinite(result["combined_delta"])
                or result["combined_delta"] <= 0
                or not isinstance(bootstrap, dict)
                or bootstrap.get("method") != "family-cluster-percentile-bootstrap-v1"
                or bootstrap.get("clusters") != 3
                or bootstrap.get("pairs_per_cluster") != 60
                or bootstrap.get("confidence") != 0.95
                or bootstrap.get("resamples") != 2000
                or bootstrap.get("seed") != 1729
                or bootstrap.get("probability_positive") != 1.0
                or isinstance(bootstrap.get("lower"), bool)
                or not isinstance(bootstrap.get("lower"), (int, float))
                or not math.isfinite(bootstrap["lower"])
                or bootstrap["lower"] <= 0
                or isinstance(bootstrap.get("upper"), bool)
                or not isinstance(bootstrap.get("upper"), (int, float))
                or not math.isfinite(bootstrap["upper"])
                or bootstrap["upper"] < bootstrap["lower"]
            ):
                errors.append(f"embedded family {name} revision-delta result is unsafe")

        trace_fidelity = evidence.get("revision_trace_fidelity")
        if not isinstance(trace_fidelity, dict):
            raise TypeError("paper readiness revision-trace evidence is not an object")
        if (
            trace_fidelity.get("valid") is not True
            or trace_fidelity.get("schema_version") != "far-revision-trace-fidelity-report-audit-v1"
            or trace_fidelity.get("analysis_profile")
            != "post-hoc-frozen-revision-trace-fidelity-v1"
            or trace_fidelity.get("checks") != TRACE_FIDELITY_CHECKS
            or trace_fidelity.get("boundaries") != TRACE_FIDELITY_BOUNDARIES
            or trace_fidelity.get("errors") != []
            or trace_fidelity.get("model_calls") != 0
            or trace_fidelity.get("test_accessed") is not False
            or trace_fidelity.get("human_review") is not False
            or trace_fidelity.get("publication_gold") is not False
            or trace_fidelity.get("semantic_correctness") is not False
            or not re.fullmatch(r"[0-9a-f]{64}", str(trace_fidelity.get("json_sha256", "")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(trace_fidelity.get("markdown_sha256", "")))
        ):
            errors.append("embedded revision-trace evidence or boundary is unsafe")
        trace_qwen = trace_fidelity.get("qwen_far")
        trace_comparison = trace_fidelity.get("qwen_typed_minus_untyped")
        trace_family = trace_fidelity.get("family_trace_delta_f1")
        trace_buckets = (
            trace_qwen.get("trace_bucket_counts") if isinstance(trace_qwen, dict) else None
        )
        trace_delta = (
            trace_comparison.get("trace_delta_f1") if isinstance(trace_comparison, dict) else None
        )
        trace_hit = (
            trace_comparison.get("trace_target_hit") if isinstance(trace_comparison, dict) else None
        )
        trace_cluster = (
            trace_family.get("family_cluster_bootstrap") if isinstance(trace_family, dict) else None
        )
        if (
            not isinstance(trace_qwen, dict)
            or trace_qwen.get("samples") != 60
            or not math.isclose(
                float(trace_qwen.get("mean_trace_delta_f1", -1.0)),
                0.08231897898428224,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or trace_buckets
            != {
                "complete_with_collateral": 14,
                "exact_target": 1,
                "no_lexical_edit": 12,
                "off_target": 19,
                "partial_target": 1,
                "partial_with_collateral": 13,
            }
            or not isinstance(trace_delta, dict)
            or trace_delta.get("candidate_minus_baseline", 0.0) <= 0.0
            or trace_delta.get("lower", 0.0) <= 0.0
            or not isinstance(trace_hit, dict)
            or trace_hit.get("candidate_minus_baseline", 0.0) >= 0.0
            or trace_hit.get("lower", 0.0) >= 0.0
            or trace_hit.get("upper", 0.0) <= 0.0
            or not isinstance(trace_family, dict)
            or trace_family.get("positive_families") != 3
            or trace_family.get("combined_delta", 0.0) <= 0.0
            or not isinstance(trace_cluster, dict)
            or trace_cluster.get("lower", 0.0) <= 0.0
        ):
            errors.append("embedded revision-trace result is incomplete or contradicted")

        selective_revision = evidence.get("selective_revision_feasibility")
        if not isinstance(selective_revision, dict):
            raise TypeError("paper readiness selective-revision evidence is not an object")
        if (
            selective_revision.get("valid") is not True
            or selective_revision.get("schema_version")
            != "far-selective-revision-feasibility-report-audit-v1"
            or selective_revision.get("analysis_profile")
            != "post-hoc-frozen-selective-revision-feasibility-v1"
            or selective_revision.get("checks") != SELECTIVE_REVISION_CHECKS
            or selective_revision.get("boundaries") != SELECTIVE_REVISION_BOUNDARIES
            or selective_revision.get("errors") != []
            or selective_revision.get("model_calls") != 0
            or selective_revision.get("test_accessed") is not False
            or selective_revision.get("human_review") is not False
            or selective_revision.get("publication_gold") is not False
            or selective_revision.get("semantic_correctness") is not False
            or selective_revision.get("deployable_selector_evaluated") is not False
            or not re.fullmatch(r"[0-9a-f]{64}", str(selective_revision.get("json_sha256", "")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(selective_revision.get("markdown_sha256", "")))
        ):
            errors.append("embedded selective-revision evidence or boundary is unsafe")
        selective_arms = selective_revision.get("fixed_arms")
        selective_envelope = selective_revision.get("reference_arm_choice_envelope")
        selective_high = selective_revision.get("confidence_threshold_0_90")
        if (
            not isinstance(selective_arms, dict)
            or set(selective_arms) != {"preserve", "generic", "typed"}
            or any(
                not isinstance(selective_arms.get(arm), dict)
                or selective_arms[arm].get("samples") != 60
                for arm in ("preserve", "generic", "typed")
            )
            or selective_arms["preserve"].get("answer_soft_f1_ge_0_8") != 60
            or not math.isclose(
                float(selective_arms["preserve"].get("mean_answer_soft_f1", -1.0)),
                0.9783512842439768,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or selective_arms["preserve"].get("mean_revision_delta_f1") != 0.0
            or not math.isclose(
                float(selective_arms["generic"].get("mean_revision_delta_f1", -1.0)),
                0.07225192012288786,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or not math.isclose(
                float(selective_arms["typed"].get("mean_revision_delta_f1", -1.0)),
                0.14544003604780276,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or not isinstance(selective_envelope, dict)
            or selective_envelope.get("reference_dependent") is not True
            or selective_envelope.get("deployable") is not False
            or not math.isclose(
                float(selective_envelope.get("mean_per_item_max", -1.0)),
                0.16182369870097854,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or not math.isclose(
                float(selective_envelope.get("gain_over_always_typed", -1.0)),
                0.016383662653175785,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or not isinstance(selective_high, dict)
            or selective_high.get("threshold") != 0.9
            or selective_high.get("selected_rows") != 31
            or selective_high.get("selected_trace_target_complete_rate") != 5 / 31
            or selective_high.get("selected_trace_collateral_rate") != 25 / 31
        ):
            errors.append("embedded selective-revision result is incomplete or contradicted")

        markdown = payload_by_role["solo_paper_readiness_markdown"].decode("utf-8")
        required_markdown_boundaries = (
            "| Strict AAAI submission | `false` |",
            "labels are not human-validated gold",
            "evaluation is not externally blind",
            "revision-delta metrics are post-hoc lexical diagnostics, not semantic correctness",
            "revision traces frequently miss the construction target or add collateral edits",
            "selective revision feasibility is post-hoc and does not evaluate a "
            "deployable selector",
            "raw baseline revision delta exceeds FAR despite zero typed action-conditioned delta",
            "P6-M as human review, human adjudication, or human IAA",
        )
        for boundary in required_markdown_boundaries:
            if boundary not in markdown:
                errors.append(f"Markdown readiness omits a claim boundary: {boundary}")

        fever = evidence.get("fever_binary")
        solo_release = evidence.get("solo_release")
        stage_trace = evidence.get("stage_trace_map")
        if (
            not isinstance(fever, dict)
            or not isinstance(solo_release, dict)
            or not isinstance(stage_trace, dict)
        ):
            raise TypeError("paper readiness release-boundary evidence is not an object")
        if (
            fever.get("valid") is not True
            or fever.get("publication_ready_main_result") is not False
        ):
            errors.append("embedded FEVER boundary was upgraded or changed")
        if (
            solo_release.get("valid") is not True
            or solo_release.get("publication_ready") is not False
        ):
            errors.append("embedded diagnostic-release boundary was upgraded or changed")
        if (
            stage_trace.get("valid") is not True
            or stage_trace.get("model_calls") != 0
            or stage_trace.get("publication_gold") is not False
            or stage_trace.get("test_accessed") is not False
            or stage_trace.get("causal_attribution") is not False
        ):
            errors.append("embedded stage-trace boundary was upgraded or changed")

        source_lock = _lock_values(payload_by_role["tmlr_source_lock"])
        if set(source_lock) != {
            "source",
            "source_sha256",
            "appendix",
            "appendix_sha256",
            "style_repository",
            "style_commit",
            "mode",
        }:
            errors.append("TMLR source lock has unexpected fields")
        if source_lock.get("source") != "paper/main.tex":
            errors.append("TMLR source lock points to the wrong main source")
        if source_lock.get("appendix") != "paper/appendix.tex":
            errors.append("TMLR source lock points to the wrong appendix")
        if source_lock.get("style_repository") != (
            "https://github.com/JmlrOrg/tmlr-style-file.git"
        ):
            errors.append("TMLR source lock uses the wrong style repository")
        if source_lock.get("mode") != "anonymous_submission":
            errors.append("TMLR source lock is not anonymous-submission mode")
        if source_lock.get("style_commit") != TMLR_STYLE_COMMIT:
            errors.append("TMLR source lock uses the wrong style commit")
        if source_lock.get("source_sha256") != evidence.get("paper_main_sha256"):
            errors.append("TMLR main-source lock does not match paper readiness")
        if source_lock.get("appendix_sha256") != evidence.get("paper_appendix_sha256"):
            errors.append("TMLR appendix lock does not match paper readiness")
        pdf = payload_by_role["tmlr_paper_pdf"]
        if not pdf.startswith(b"%PDF-") or b"%%EOF" not in pdf[-1024:]:
            errors.append("TMLR artifact is not a PDF")

        benchmark = json.loads(payload_by_role["benchmark_validation_report"])
        if not isinstance(benchmark, dict):
            raise TypeError("benchmark validation is not an object")
        if benchmark.get("candidate_ready") is not True:
            errors.append("embedded benchmark validation is not candidate-ready")
        if benchmark.get("publication_ready") is not False:
            errors.append("embedded benchmark validation upgrades publication readiness")
        if json.loads(payload_by_role["secret_scan_report"]) != []:
            errors.append("embedded secret scan is not empty")

        sbom = json.loads(payload_by_role["cyclonedx_sbom"])
        if not isinstance(sbom, dict):
            raise TypeError("SBOM is not an object")
        project = checksums.get("project") if isinstance(checksums, dict) else None
        metadata = sbom.get("metadata")
        if not isinstance(project, dict) or not isinstance(metadata, dict):
            raise TypeError("release project or SBOM metadata is not an object")
        component = metadata.get("component")
        if not isinstance(component, dict):
            raise TypeError("SBOM component is not an object")
        if sbom.get("bomFormat") != "CycloneDX":
            errors.append("embedded SBOM is not CycloneDX")
        if (
            component.get("name") != project.get("name")
            or component.get("version") != project.get("version")
            or component.get("type") != "application"
        ):
            errors.append("embedded SBOM project does not match release checksums")
        _verify_python_archives(payload_by_role, errors)
    except (KeyError, TypeError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))


def verify_bundle(archive: Path) -> dict[str, Any]:
    """Verify one archive without reading any source-worktree artifact."""

    payloads, errors = _member_payloads(archive)
    manifest: Any = None
    if MANIFEST_PATH not in payloads:
        errors.append("bundle manifest is missing")
    else:
        try:
            manifest = _parse_json_payload(payloads, MANIFEST_PATH)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"bundle manifest is invalid: {exc}")
    artifacts, supports = _verify_manifest_shape(manifest, errors)

    roles: set[str] = set()
    expected_paths = {MANIFEST_PATH}
    payload_by_role: dict[str, bytes] = {}
    artifact_by_role: dict[str, dict[str, Any]] = {}
    for entry in artifacts:
        role, path = _verify_entry(entry, payloads, errors)
        if role is not None:
            if role in roles:
                errors.append(f"duplicate bundle artifact role: {role}")
            roles.add(role)
            if isinstance(entry, dict):
                artifact_by_role[role] = entry
            if path in payloads:
                payload_by_role[role] = payloads[path]
        if path is not None:
            expected_paths.add(path)
    if roles != set(SOLO_PAPER_RELEASE_ARTIFACT_ROLES):
        errors.append("bundle artifact roles do not match the solo-paper profile")

    support_roles: set[str] = set()
    for entry in supports:
        role, path = _verify_entry(entry, payloads, errors, support=True)
        if role is not None:
            if role in support_roles:
                errors.append(f"duplicate bundle support role: {role}")
            support_roles.add(role)
            if path != SUPPORT_PATHS.get(role):
                errors.append(f"noncanonical bundle support path: {role}")
        if path is not None:
            expected_paths.add(path)
    if support_roles != set(SUPPORT_PATHS):
        errors.append("bundle support files are incomplete")
    if payloads.get(SUPPORT_PATHS["readme"]) != _readme():
        errors.append("bundle README differs from the frozen interpretation boundary")
    _verify_standalone_identity(payloads, errors)
    if set(payloads) != expected_paths:
        errors.append("archive member set differs from the embedded manifest")

    checksums: Any = None
    checksum_payload = payloads.get(SUPPORT_PATHS["release_checksums"])
    if checksum_payload is not None:
        try:
            checksums = json.loads(checksum_payload)
            if not isinstance(checksums, dict):
                raise TypeError("release checksums are not an object")
            if checksums.get("schema_version") != "far-release-checksums-v1":
                errors.append("embedded release checksum schema is unsupported")
            if checksums.get("release_profile") != "solo-paper":
                errors.append("embedded release checksums use the wrong profile")
            if isinstance(manifest, dict) and checksums.get("source_revision") != manifest.get(
                "source_revision"
            ):
                errors.append("bundle source revision differs from release checksums")
            checksum_items = [
                item
                for item in checksums.get("artifacts", [])
                if isinstance(item, dict) and isinstance(item.get("role"), str)
            ]
            checksum_artifacts = {item.get("role"): item for item in checksum_items}
            if len(checksum_artifacts) != len(checksum_items):
                errors.append("embedded release checksums contain duplicate roles")
            if set(checksum_artifacts) != set(SOLO_PAPER_RELEASE_ARTIFACT_ROLES):
                errors.append("embedded release checksum roles are incomplete")
            for role, entry in artifact_by_role.items():
                checksum_entry = checksum_artifacts.get(role, {})
                if {
                    "path": entry.get("original_path"),
                    "bytes": entry.get("bytes"),
                    "sha256": entry.get("sha256"),
                } != {
                    "path": checksum_entry.get("path"),
                    "bytes": checksum_entry.get("bytes"),
                    "sha256": checksum_entry.get("sha256"),
                }:
                    errors.append(f"bundle inventory differs from release checksums: {role}")
        except (TypeError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
    if checksums is not None and roles == set(SOLO_PAPER_RELEASE_ARTIFACT_ROLES):
        _verify_semantics(payload_by_role, checksums, errors)

    archive_is_safe_file = archive.is_file() and archive.stat().st_size <= MAX_COMPRESSED_BYTES
    verifier_payload = payloads.get(SUPPORT_PATHS["standalone_verifier"])
    return {
        "schema_version": "far-solo-paper-release-bundle-audit-v2",
        "valid": not errors,
        "errors": errors,
        "archive": str(archive),
        "archive_bytes": archive.stat().st_size if archive.is_file() else None,
        "archive_sha256": sha256_file(archive) if archive_is_safe_file else None,
        "artifact_count": len(roles),
        "source_revision": manifest.get("source_revision") if isinstance(manifest, dict) else None,
        "boundary_flags": manifest.get("boundary_flags") if isinstance(manifest, dict) else None,
        "standalone_verifier_sha256": (
            _sha256_bytes(verifier_payload) if verifier_payload is not None else None
        ),
        "standalone_execution": __package__ in {None, ""},
        "python_isolated": sys.flags.isolated == 1,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    pack_parser = subparsers.add_parser("pack")
    verify_parser = subparsers.add_parser("verify")
    pack_parser.add_argument("--project-root", type=Path, default=Path.cwd())
    pack_parser.add_argument("--checksum-manifest", type=Path, default=DEFAULT_CHECKSUM_MANIFEST)
    pack_parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    pack_parser.add_argument(
        "--standalone-verifier",
        type=Path,
        default=DEFAULT_STANDALONE_VERIFIER,
    )
    verify_parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args(argv)

    if args.command == "pack":
        result = pack_bundle(
            args.project_root,
            args.checksum_manifest,
            args.archive,
            args.standalone_verifier,
        )
    else:
        result = verify_bundle(args.archive)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result.get("valid") is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
