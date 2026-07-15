"""Generate and validate SHA-256 fingerprints for FAR release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from far.experiments.generate_sbom import build_sbom

DEFAULT_OUTPUT = Path("build/release-checksums.json")
DEFAULT_DIST_DIR = Path("dist")
DEFAULT_SBOM = Path("build/sbom/far-sbom.cdx.json")
BASE_RELEASE_ARTIFACT_ROLES = frozenset({"sdist", "wheel", "cyclonedx_sbom"})
FINAL_RELEASE_ARTIFACT_ROLES = BASE_RELEASE_ARTIFACT_ROLES | frozenset(
    {
        "benchmark_validation_report",
        "secret_scan_report",
        "submission_evidence_snapshot",
        "paper_main_pdf",
        "paper_supplement_pdf",
        "aaai_reproducibility_checklist_pdf",
    }
)
SOLO_PAPER_RELEASE_ARTIFACT_ROLES = BASE_RELEASE_ARTIFACT_ROLES | frozenset(
    {
        "benchmark_validation_report",
        "secret_scan_report",
        "selective_acceptance_json",
        "selective_acceptance_markdown",
        "solo_paper_readiness_json",
        "solo_paper_readiness_markdown",
        "tmlr_paper_pdf",
        "tmlr_source_lock",
    }
)
RELEASE_PROFILES = {
    "base": BASE_RELEASE_ARTIFACT_ROLES,
    "solo-paper": SOLO_PAPER_RELEASE_ARTIFACT_ROLES,
    "strict-submission": FINAL_RELEASE_ARTIFACT_ROLES,
}


@dataclass(frozen=True)
class ChecksumAudit:
    valid: bool
    errors: tuple[str, ...]
    manifest_path: str
    artifact_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "manifest_path": self.manifest_path,
            "artifact_count": self.artifact_count,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_revision(root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return {"git_commit": None, "git_dirty": None}
    return {"git_commit": commit, "git_dirty": bool(status.strip())}


def _entry(path: Path, *, role: str, root: Path) -> dict[str, Any]:
    resolved_root = root.resolve()
    resolved = (path if path.is_absolute() else resolved_root / path).resolve()
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"release artifact must stay inside project root: {path}") from exc
    if not resolved.is_file():
        raise FileNotFoundError(f"release artifact is missing: {resolved}")
    return {
        "role": role,
        "path": relative.as_posix(),
        "bytes": resolved.stat().st_size,
        "sha256": _sha256(resolved),
    }


def build_checksum_manifest(
    *,
    project_root: str | Path = ".",
    dist_dir: str | Path = DEFAULT_DIST_DIR,
    sbom_path: str | Path = DEFAULT_SBOM,
    extra_artifacts: Iterable[tuple[str, str | Path]] = (),
    release_profile: str = "base",
) -> dict[str, Any]:
    if release_profile not in RELEASE_PROFILES:
        raise ValueError(f"unknown release profile: {release_profile}")
    root = Path(project_root)
    project = build_sbom(root)["metadata"]["component"]
    name = str(project["name"])
    version = str(project["version"])
    distribution = name.lower().replace("-", "_")
    dist = Path(dist_dir)
    artifacts = [
        _entry(
            dist / f"{distribution}-{version}.tar.gz",
            role="sdist",
            root=root,
        ),
        _entry(
            dist / f"{distribution}-{version}-py3-none-any.whl",
            role="wheel",
            root=root,
        ),
        _entry(Path(sbom_path), role="cyclonedx_sbom", root=root),
    ]
    artifacts.extend(_entry(Path(path), role=role, root=root) for role, path in extra_artifacts)
    return {
        "schema_version": "far-release-checksums-v1",
        "release_profile": release_profile,
        "project": {"name": name, "version": version},
        "source_revision": _git_revision(root),
        "generator": "far.experiments.generate_release_checksums",
        "artifacts": artifacts,
    }


def write_checksum_manifest(
    manifest: dict[str, Any],
    output_path: str | Path = DEFAULT_OUTPUT,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def validate_checksum_manifest(
    manifest_path: str | Path = DEFAULT_OUTPUT,
    *,
    project_root: str | Path = ".",
    required_roles: Iterable[str] = BASE_RELEASE_ARTIFACT_ROLES,
    required_profile: str | None = None,
) -> ChecksumAudit:
    path = Path(manifest_path)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ChecksumAudit(False, (f"manifest does not exist: {path}",), str(path), 0)
    except json.JSONDecodeError as exc:
        return ChecksumAudit(False, (f"manifest is not valid JSON: {exc}",), str(path), 0)
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ChecksumAudit(False, ("manifest must be a JSON object",), str(path), 0)
    root = Path(project_root).resolve()
    if manifest.get("schema_version") != "far-release-checksums-v1":
        errors.append("unsupported release checksum schema")
    if required_profile is not None and manifest.get("release_profile") != required_profile:
        errors.append(
            f"release profile mismatch: {manifest.get('release_profile')!r} != {required_profile!r}"
        )
    recorded_revision = manifest.get("source_revision")
    current_revision = _git_revision(root)
    if not isinstance(recorded_revision, dict):
        errors.append("manifest source_revision is missing")
    elif recorded_revision.get("git_commit") is not None:
        if recorded_revision != current_revision:
            errors.append("release source revision no longer matches the working tree")
        if recorded_revision.get("git_dirty") is not False:
            errors.append("release source revision must be a clean Git worktree")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("manifest artifacts must be a non-empty list")
        artifacts = []
    roles: set[str] = set()
    paths: set[str] = set()
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            errors.append(f"artifact[{index}] must be an object")
            continue
        role = item.get("role")
        relative = item.get("path")
        if not isinstance(role, str) or not role:
            errors.append(f"artifact[{index}] has no role")
        elif role in roles:
            errors.append(f"duplicate artifact role: {role}")
        else:
            roles.add(role)
        if not isinstance(relative, str) or not relative:
            errors.append(f"artifact[{index}] has no path")
            continue
        rel_path = Path(relative)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            errors.append(f"artifact path escapes project root: {relative}")
            continue
        if relative in paths:
            errors.append(f"duplicate artifact path: {relative}")
        paths.add(relative)
        artifact_path = root / rel_path
        if not artifact_path.is_file():
            errors.append(f"artifact is missing: {relative}")
            continue
        if item.get("bytes") != artifact_path.stat().st_size:
            errors.append(f"artifact size mismatch: {relative}")
        if item.get("sha256") != _sha256(artifact_path):
            errors.append(f"artifact sha256 mismatch: {relative}")
    required = set(required_roles)
    if required_profile is not None:
        profile_roles = RELEASE_PROFILES.get(required_profile)
        if profile_roles is None:
            errors.append(f"unknown required release profile: {required_profile}")
        else:
            required.update(profile_roles)
    for role in sorted(required - roles):
        errors.append(f"missing required artifact role: {role}")
    return ChecksumAudit(not errors, tuple(errors), str(path), len(artifacts))


def _parse_extra_artifact(raw: str) -> tuple[str, Path]:
    role, sep, path = raw.partition("=")
    if not sep or not role.strip() or not path.strip():
        raise argparse.ArgumentTypeError("artifact must use ROLE=PATH")
    return role.strip(), Path(path.strip())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--dist-dir", type=Path, default=DEFAULT_DIST_DIR)
    parser.add_argument("--sbom", type=Path, default=DEFAULT_SBOM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        type=_parse_extra_artifact,
        metavar="ROLE=PATH",
        help="add an extra release artifact to fingerprint; may be repeated",
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--profile",
        choices=sorted(RELEASE_PROFILES),
        default="base",
        help="validate the artifact roles required by this release profile",
    )
    args = parser.parse_args(argv)
    manifest = build_checksum_manifest(
        project_root=args.project_root,
        dist_dir=args.dist_dir,
        sbom_path=args.sbom,
        extra_artifacts=args.artifact,
        release_profile=args.profile,
    )
    path = write_checksum_manifest(manifest, args.output)
    audit = validate_checksum_manifest(
        path,
        project_root=args.project_root,
        required_roles=RELEASE_PROFILES[args.profile],
        required_profile=args.profile,
    )
    if args.json:
        print(
            json.dumps(
                {
                    **audit.to_dict(),
                    "profile": args.profile,
                    "required_roles": sorted(RELEASE_PROFILES[args.profile]),
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif audit.valid:
        print(f"Release checksums validated: {audit.artifact_count} artifacts.")
    else:
        for error in audit.errors:
            print(f"- {error}")
    if args.check and not audit.valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
