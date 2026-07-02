from __future__ import annotations

import json
from pathlib import Path

from experiments.generate_release_checksums import (
    build_checksum_manifest,
    validate_checksum_manifest,
    write_checksum_manifest,
)
from experiments.generate_sbom import build_sbom, write_sbom


def _release_tree(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "demo-project"',
                'version = "1.2.3"',
                'dependencies = ["PyYAML>=6"]',
                "",
                "[project.optional-dependencies]",
                'dev = ["pytest>=8"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    dist = root / "dist"
    dist.mkdir()
    (dist / "demo_project-1.2.3.tar.gz").write_bytes(b"sdist")
    (dist / "demo_project-1.2.3-py3-none-any.whl").write_bytes(b"wheel")
    sbom = write_sbom(build_sbom(root), root / "build/sbom/demo.cdx.json")
    return root, sbom


def test_release_checksums_cover_package_and_sbom(tmp_path: Path) -> None:
    root, sbom = _release_tree(tmp_path)
    manifest = build_checksum_manifest(project_root=root, sbom_path=sbom)
    output = write_checksum_manifest(manifest, root / "build/release-checksums.json")

    audit = validate_checksum_manifest(output, project_root=root)

    assert audit.valid is True
    assert audit.artifact_count == 3
    assert {item["role"] for item in manifest["artifacts"]} == {
        "sdist",
        "wheel",
        "cyclonedx_sbom",
    }
    assert manifest["source_revision"] == {"git_commit": None, "git_dirty": None}


def test_release_checksums_reject_modified_artifact(tmp_path: Path) -> None:
    root, sbom = _release_tree(tmp_path)
    manifest = build_checksum_manifest(project_root=root, sbom_path=sbom)
    output = write_checksum_manifest(manifest, root / "build/release-checksums.json")
    (root / "dist/demo_project-1.2.3.tar.gz").write_bytes(b"changed")

    audit = validate_checksum_manifest(output, project_root=root)

    assert audit.valid is False
    assert any("sdist" not in error and "mismatch" in error for error in audit.errors)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "far-release-checksums-v1"


def test_source_archive_includes_submission_evidence_templates() -> None:
    manifest = (Path(__file__).resolve().parents[1] / "MANIFEST.in").read_text(encoding="utf-8")
    assert "recursive-include submission *.json" in manifest
