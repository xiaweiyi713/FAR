from __future__ import annotations

import json
import subprocess
import tarfile
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


def test_release_checksums_cover_extra_release_artifacts(tmp_path: Path) -> None:
    root, sbom = _release_tree(tmp_path)
    paper_pdf = root / "paper/build/release/main.pdf"
    paper_pdf.parent.mkdir(parents=True)
    paper_pdf.write_bytes(b"%PDF release copy")
    manifest = build_checksum_manifest(
        project_root=root,
        sbom_path=sbom,
        extra_artifacts=[("paper_main_pdf", paper_pdf)],
    )
    output = write_checksum_manifest(manifest, root / "build/release-checksums.json")

    audit = validate_checksum_manifest(output, project_root=root)

    assert audit.valid is True
    assert audit.artifact_count == 4
    assert {item["role"] for item in manifest["artifacts"]} == {
        "sdist",
        "wheel",
        "cyclonedx_sbom",
        "paper_main_pdf",
    }
    paper_pdf.write_bytes(b"%PDF replaced")
    modified_audit = validate_checksum_manifest(output, project_root=root)
    assert modified_audit.valid is False
    assert "artifact size mismatch: paper/build/release/main.pdf" in modified_audit.errors
    assert "artifact sha256 mismatch: paper/build/release/main.pdf" in modified_audit.errors


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
    assert "include submission/evidence.template.json" in manifest
    assert "include submission/blind_test_attestation.template.json" in manifest
    assert "recursive-include submission *.json" not in manifest
    assert "include submission/evidence.json" not in manifest
    assert "include submission/blind_test_attestation.json" not in manifest


def test_source_archive_excludes_real_submission_evidence(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    real_evidence = root / "submission/evidence.json"
    real_attestation = root / "submission/blind_test_attestation.json"
    assert not real_evidence.exists()
    assert not real_attestation.exists()
    real_evidence.write_text('{"secret": "real evidence must not ship"}\n', encoding="utf-8")
    real_attestation.write_text('{"secret": "real attestation must not ship"}\n', encoding="utf-8")
    dist_dir = tmp_path / "dist"
    try:
        subprocess.run(
            ["uv", "build", "--sdist", "--out-dir", str(dist_dir)],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        archive = next(dist_dir.glob("*.tar.gz"))
        with tarfile.open(archive) as tar:
            submission_members = {
                Path(name).relative_to(Path(name).parts[0]).as_posix()
                for name in tar.getnames()
                if "/submission/" in name
            }
    finally:
        real_evidence.unlink(missing_ok=True)
        real_attestation.unlink(missing_ok=True)
    assert submission_members == {
        "submission/blind_test_attestation.template.json",
        "submission/evidence.template.json",
    }
