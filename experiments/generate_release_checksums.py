"""Generate and validate SHA-256 fingerprints for FAR release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.generate_sbom import build_sbom

DEFAULT_OUTPUT = Path("build/release-checksums.json")
DEFAULT_DIST_DIR = Path("dist")
DEFAULT_SBOM = Path("build/sbom/far-sbom.cdx.json")


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
) -> dict[str, Any]:
    root = Path(project_root)
    project = build_sbom(root)["metadata"]["component"]
    name = str(project["name"])
    version = str(project["version"])
    distribution = name.lower().replace("-", "_")
    dist = Path(dist_dir)
    return {
        "schema_version": "far-release-checksums-v1",
        "project": {"name": name, "version": version},
        "generator": "experiments.generate_release_checksums",
        "artifacts": [
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
        ],
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
    if manifest.get("schema_version") != "far-release-checksums-v1":
        errors.append("unsupported release checksum schema")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("manifest artifacts must be a non-empty list")
        artifacts = []
    root = Path(project_root).resolve()
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
    required = {"sdist", "wheel", "cyclonedx_sbom"}
    for role in sorted(required - roles):
        errors.append(f"missing required artifact role: {role}")
    return ChecksumAudit(not errors, tuple(errors), str(path), len(artifacts))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--dist-dir", type=Path, default=DEFAULT_DIST_DIR)
    parser.add_argument("--sbom", type=Path, default=DEFAULT_SBOM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    manifest = build_checksum_manifest(
        project_root=args.project_root,
        dist_dir=args.dist_dir,
        sbom_path=args.sbom,
    )
    path = write_checksum_manifest(manifest, args.output)
    audit = validate_checksum_manifest(path, project_root=args.project_root)
    if args.json:
        print(json.dumps(audit.to_dict(), indent=2, sort_keys=True))
    elif audit.valid:
        print(f"Release checksums validated: {audit.artifact_count} artifacts.")
    else:
        for error in audit.errors:
            print(f"- {error}")
    if args.check and not audit.valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
