from __future__ import annotations

import json
import subprocess
import tarfile
from pathlib import Path

import pytest

from far.experiments.generate_release_checksums import (
    FINAL_RELEASE_ARTIFACT_ROLES,
    build_checksum_manifest,
    validate_checksum_manifest,
    write_checksum_manifest,
)
from far.experiments.generate_sbom import build_sbom, write_sbom
from far.experiments.runner import _implementation_sha256
from far.experiments.submission_readiness import Gate, _release_gate


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


def test_final_release_validation_requires_all_submission_artifacts(tmp_path: Path) -> None:
    root, sbom = _release_tree(tmp_path)
    manifest = build_checksum_manifest(project_root=root, sbom_path=sbom)
    output = write_checksum_manifest(manifest, root / "build/release-checksums.json")

    audit = validate_checksum_manifest(
        output,
        project_root=root,
        required_roles=FINAL_RELEASE_ARTIFACT_ROLES,
    )

    assert audit.valid is False
    assert set(audit.errors) == {
        f"missing required artifact role: {role}"
        for role in FINAL_RELEASE_ARTIFACT_ROLES - {"sdist", "wheel", "cyclonedx_sbom"}
    }


def test_final_release_validation_accepts_complete_submission_set(tmp_path: Path) -> None:
    root, sbom = _release_tree(tmp_path)
    extra_roles = FINAL_RELEASE_ARTIFACT_ROLES - {"sdist", "wheel", "cyclonedx_sbom"}
    extras: list[tuple[str, Path]] = []
    for role in sorted(extra_roles):
        artifact = root / "release" / f"{role}.artifact"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(role.encode())
        extras.append((role, artifact))
    manifest = build_checksum_manifest(
        project_root=root,
        sbom_path=sbom,
        extra_artifacts=extras,
    )
    output = write_checksum_manifest(manifest, root / "build/release-checksums.json")

    audit = validate_checksum_manifest(
        output,
        project_root=root,
        required_roles=FINAL_RELEASE_ARTIFACT_ROLES,
    )

    assert audit.valid is True
    assert audit.artifact_count == 9


def test_submission_release_gate_binds_exact_audited_evidence(tmp_path: Path) -> None:
    root, sbom = _release_tree(tmp_path)
    config = {
        "release_checksums": "build/release-checksums.json",
        "submission_evidence_snapshot": "submission/evidence.json",
    }
    evidence = root / config["submission_evidence_snapshot"]
    evidence.parent.mkdir(parents=True)
    evidence.write_text(json.dumps(config), encoding="utf-8")
    extras: list[tuple[str, Path]] = [("submission_evidence_snapshot", evidence)]
    for role in sorted(
        FINAL_RELEASE_ARTIFACT_ROLES
        - {"sdist", "wheel", "cyclonedx_sbom", "submission_evidence_snapshot"}
    ):
        artifact = root / "release" / f"{role}.artifact"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(role.encode())
        extras.append((role, artifact))
    manifest = build_checksum_manifest(
        project_root=root,
        sbom_path=sbom,
        extra_artifacts=extras,
    )
    write_checksum_manifest(manifest, root / config["release_checksums"])
    dev_suites = Gate(
        "adjudicated_dev_matrix",
        True,
        "ok",
        {"implementation_sha256": _implementation_sha256()},
    )

    result = _release_gate(root, config, dev_suites)

    assert result["artifacts"] == 9
    with pytest.raises(ValueError, match="does not match the audited evidence"):
        _release_gate(root, {**config, "unexpected": True}, dev_suites)


def test_release_check_fingerprints_generated_audit_and_pdf_artifacts() -> None:
    script = (Path(__file__).resolve().parents[1] / "scripts/release_check.sh").read_text(
        encoding="utf-8"
    )
    for role in (
        "benchmark_validation_report",
        "secret_scan_report",
        "submission_evidence_snapshot",
        "paper_main_pdf",
        "paper_supplement_pdf",
        "aaai_reproducibility_checklist_pdf",
    ):
        assert f"--artifact {role}=" in script
    checksum_offset = script.index("uv run falsirag-release-checksums")
    readiness_offset = script.index("uv run falsirag-submission-readiness")
    solo_offset = script.index("bash scripts/solo_diagnostic_check.sh")
    validate_offset = script.index("uv run falsirag-validate-bench")
    build_offset = script.index("uv build")
    smoke_offset = script.index("bash scripts/check_release_packages.sh")
    assert solo_offset < validate_offset
    assert build_offset < smoke_offset < checksum_offset
    assert checksum_offset < readiness_offset
    assert "submission_readiness_snapshot" not in script
    assert 'EVIDENCE_PATH="${FAR_SUBMISSION_EVIDENCE:-' in script


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
    assert "recursive-include reports *.md *.csv *.json" in manifest
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


def test_source_archive_includes_reader_facing_reports(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    dist_dir = tmp_path / "dist"

    subprocess.run(
        ["uv", "build", "--sdist", "--out-dir", str(dist_dir)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    archive = next(dist_dir.glob("*.tar.gz"))
    with tarfile.open(archive) as tar:
        members = {
            Path(name).relative_to(Path(name).parts[0]).as_posix() for name in tar.getnames()
        }
        report_members = {
            Path(name).relative_to(Path(name).parts[0]).as_posix()
            for name in tar.getnames()
            if "/reports/" in name
        }

    assert ".github/workflows/ci.yml" in members
    assert "scripts/check_release_packages.sh" in members
    assert "scripts/package_smoke.py" in members
    assert report_members == {
        "reports/README.md",
        "reports/boundary_benchmark_selection.md",
        "reports/boundary_matrix.md",
        "reports/longterm_roadmap_status.json",
        "reports/longterm_roadmap_status.md",
        "reports/mechanism_attribution.md",
        "reports/p5_ramdocs_ablations.json",
        "reports/p5_ramdocs_ablations.md",
        "reports/power_retrospective.md",
        "reports/project_status_snapshot.json",
        "reports/project_status_snapshot.md",
        "reports/ramdocs_round2_failure_readiness.json",
        "reports/repository_maintenance.json",
        "reports/repository_maintenance.md",
        "reports/single_author_diagnostic_report.md",
        "reports/solo_human_review_priority.csv",
        "reports/solo_paper_readiness.json",
        "reports/solo_paper_readiness.md",
        "reports/stage_trace_map.json",
        "reports/stage_trace_map.md",
        "reports/tmlr_result_integration_matrix.md",
        "reports/type_mappability_machine",
        "reports/type_mappability_machine/consensus_rows.jsonl",
        "reports/type_mappability_machine/manifest.json",
        "reports/type_mappability_machine/type_mappability_machine.json",
        "reports/type_mappability_machine/type_mappability_machine.md",
    }
