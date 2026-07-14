from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from far.experiments.generate_release_checksums import (
    build_checksum_manifest,
    write_checksum_manifest,
)
from far.experiments.solo_paper_bundle import (
    ALLOWED_CLAIM,
    CLAIM_SCOPE_CHECKS,
    FORBIDDEN_CLAIMS,
    MANIFEST_PATH,
    READINESS_GATES,
    REQUIRED_LIMITATIONS,
    SUPPORT_PATHS,
    TMLR_STYLE_COMMIT,
    pack_bundle,
    verify_bundle,
)


def _write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _sdist() -> bytes:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        content = b"fixture\n"
        member = tarfile.TarInfo("demo-project-1.2.3/README.md")
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
    return payload.getvalue()


def _wheel() -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, mode="w") as archive:
        archive.writestr("demo_project-1.2.3.dist-info/WHEEL", "Wheel-Version: 1.0\n")
    return payload.getvalue()


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _release_tree(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "demo-project"',
                'version = "1.2.3"',
                "dependencies = []",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / ".gitignore").write_text("build/\ndist/\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "tests@example.invalid")
    _git(root, "config", "user.name", "FAR Tests")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "fixture")

    main_sha = "1" * 64
    appendix_sha = "2" * 64
    readiness = {
        "schema_version": "far-solo-paper-readiness-v3",
        "ready": True,
        "strict_aaai_submission_ready": False,
        "study_profile": "single_author_machine_audited_paper",
        "allowed_claim": ALLOWED_CLAIM,
        "required_limitations": list(REQUIRED_LIMITATIONS),
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "gates": READINESS_GATES,
        "claim_scope": {
            "valid": True,
            "checks": dict.fromkeys(CLAIM_SCOPE_CHECKS, True),
            "missing_required_disclosures": [],
            "forbidden_stale_claims": [],
        },
        "evidence": {
            "paper_main_sha256": main_sha,
            "paper_appendix_sha256": appendix_sha,
            "p5_registered_ablations": {
                "valid": True,
                "samples": 350,
                "h3_verdict": "uncertain",
                "h5_verdict": "equivalent",
                "raw_outputs_recomputed_by_this_gate": False,
            },
            "p6m_machine_ontology_stability": {
                "valid": True,
                "schema_version": "far-p6m-report-audit-v1",
                "study_profile": "machine_ontology_stability_audit",
                "retrospective": True,
                "samples": 217,
                "consensus_samples": 15,
                "dispositions": {"unanimous": 1, "majority": 14, "contested": 202},
                "association_estimable": False,
                "human_annotation_replaced": False,
                "human_iaa_computed": False,
                "human_identity_verified": False,
                "publication_gold": False,
                "confirmatory_h4": False,
                "test_accessed": False,
            },
            "fever_binary": {
                "valid": True,
                "publication_ready_main_result": False,
            },
            "solo_release": {"valid": True, "publication_ready": False},
            "stage_trace_map": {
                "valid": True,
                "model_calls": 0,
                "publication_gold": False,
                "test_accessed": False,
                "causal_attribution": False,
            },
        },
    }
    sbom = _write(
        root / "build/sbom/demo.cdx.json",
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "metadata": {
                    "component": {
                        "name": "demo-project",
                        "version": "1.2.3",
                        "type": "application",
                    }
                },
            }
        ).encode(),
    )
    extras = [
        (
            "benchmark_validation_report",
            _write(
                root / "build/release/benchmark.json",
                b'{"candidate_ready": true, "publication_ready": false}\n',
            ),
        ),
        ("secret_scan_report", _write(root / "build/release/secrets.json", b"[]\n")),
        (
            "solo_paper_readiness_json",
            _write(root / "build/release/readiness.json", json.dumps(readiness).encode()),
        ),
        (
            "solo_paper_readiness_markdown",
            _write(
                root / "build/release/readiness.md",
                (
                    b"| Strict AAAI submission | `false` |\n"
                    b"- labels are not human-validated gold\n"
                    b"- evaluation is not externally blind\n"
                    b"- P6-M as human review, human adjudication, or human IAA\n"
                ),
            ),
        ),
        (
            "tmlr_paper_pdf",
            _write(root / "build/release/paper.pdf", b"%PDF-1.7\nfixture\n%%EOF\n"),
        ),
        (
            "tmlr_source_lock",
            _write(
                root / "build/release/SOURCE.lock",
                (
                    "source=paper/main.tex\n"
                    f"source_sha256={main_sha}\n"
                    "appendix=paper/appendix.tex\n"
                    f"appendix_sha256={appendix_sha}\n"
                    "style_repository=https://github.com/JmlrOrg/tmlr-style-file.git\n"
                    f"style_commit={TMLR_STYLE_COMMIT}\n"
                    "mode=anonymous_submission\n"
                ).encode(),
            ),
        ),
    ]
    _write(
        root / "dist/demo_project-1.2.3.tar.gz",
        _sdist(),
    )
    _write(root / "dist/demo_project-1.2.3-py3-none-any.whl", _wheel())
    checksums = build_checksum_manifest(
        project_root=root,
        sbom_path=sbom,
        extra_artifacts=extras,
        release_profile="solo-paper",
    )
    checksum_path = write_checksum_manifest(
        checksums,
        root / "build/release/release-checksums.json",
    )
    return root, checksum_path


def _rewrite_archive(
    source: Path,
    destination: Path,
    replacements: dict[str, bytes],
    *,
    extra: tuple[str, bytes] | None = None,
) -> None:
    with tarfile.open(source, "r:gz") as original, tarfile.open(destination, "w:gz") as output:
        for member in original.getmembers():
            extracted = original.extractfile(member)
            assert extracted is not None
            payload = replacements.get(member.name, extracted.read())
            member.size = len(payload)
            with tempfile.SpooledTemporaryFile() as handle:
                handle.write(payload)
                handle.seek(0)
                output.addfile(member, handle)
        if extra is not None:
            name, payload = extra
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            with tempfile.SpooledTemporaryFile() as handle:
                handle.write(payload)
                handle.seek(0)
                output.addfile(info, handle)


def _coordinated_artifact_rewrite(
    source: Path,
    destination: Path,
    role: str,
    payload: bytes,
) -> None:
    with tarfile.open(source, "r:gz") as archive:
        manifest_file = archive.extractfile(MANIFEST_PATH)
        checksums_file = archive.extractfile(SUPPORT_PATHS["release_checksums"])
        assert manifest_file is not None
        assert checksums_file is not None
        manifest = json.loads(manifest_file.read())
        release_checksums = json.loads(checksums_file.read())

    payload_sha256 = hashlib.sha256(payload).hexdigest()
    artifact_entry = next(item for item in manifest["artifacts"] if item["role"] == role)
    artifact_entry["bytes"] = len(payload)
    artifact_entry["sha256"] = payload_sha256
    checksum_entry = next(item for item in release_checksums["artifacts"] if item["role"] == role)
    checksum_entry["bytes"] = len(payload)
    checksum_entry["sha256"] = payload_sha256
    checksum_payload = (json.dumps(release_checksums, indent=2, sort_keys=True) + "\n").encode()
    checksum_support = next(
        item for item in manifest["support_files"] if item["role"] == "release_checksums"
    )
    checksum_support["bytes"] = len(checksum_payload)
    checksum_support["sha256"] = hashlib.sha256(checksum_payload).hexdigest()
    manifest_payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    _rewrite_archive(
        source,
        destination,
        {
            MANIFEST_PATH: manifest_payload,
            SUPPORT_PATHS["release_checksums"]: checksum_payload,
            artifact_entry["archive_path"]: payload,
        },
    )


def test_solo_paper_bundle_is_deterministic_and_independently_verifiable(
    tmp_path: Path,
) -> None:
    root, checksums = _release_tree(tmp_path)
    first = root / "build/release/first.tar.gz"
    second = root / "build/release/second.tar.gz"
    first_verifier = root / "build/release/verify-first.py"
    second_verifier = root / "build/release/verify-second.py"

    first_result = pack_bundle(root, checksums, first, first_verifier)
    second_result = pack_bundle(root, checksums, second, second_verifier)
    checksum_payload = json.loads(checksums.read_text(encoding="utf-8"))
    for item in checksum_payload["artifacts"]:
        (root / item["path"]).unlink()
    checksums.unlink()
    audit = verify_bundle(first)
    standalone = subprocess.run(
        [
            sys.executable,
            "-I",
            str(first_verifier),
            "verify",
            "--archive",
            str(first),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    standalone_audit = json.loads(standalone.stdout)
    with tarfile.open(first, "r:gz") as archive:
        embedded_verifier = archive.extractfile(SUPPORT_PATHS["standalone_verifier"])
        assert embedded_verifier is not None
        embedded_verifier_bytes = embedded_verifier.read()

    assert first_result["archive_sha256"] == second_result["archive_sha256"]
    assert first.read_bytes() == second.read_bytes()
    assert first_verifier.read_bytes() == second_verifier.read_bytes()
    assert (
        first_result["standalone_verifier_sha256"]
        == hashlib.sha256(first_verifier.read_bytes()).hexdigest()
    )
    assert embedded_verifier_bytes == first_verifier.read_bytes()
    assert audit["valid"] is True
    assert audit["artifact_count"] == 9
    assert audit["boundary_flags"]["strict_submission_ready"] is False
    assert audit["boundary_flags"]["human_review"] is False
    assert standalone_audit["valid"] is True
    assert standalone_audit["schema_version"] == "far-solo-paper-release-bundle-audit-v2"
    assert standalone_audit["standalone_execution"] is True
    assert standalone_audit["python_isolated"] is True


def test_standalone_verifier_rejects_identity_drift_and_nonisolated_execution(
    tmp_path: Path,
) -> None:
    root, checksums = _release_tree(tmp_path)
    original = root / "build/release/original.tar.gz"
    verifier = root / "build/release/verify.py"
    pack_bundle(root, checksums, original, verifier)
    with tarfile.open(original, "r:gz") as archive:
        manifest_file = archive.extractfile(MANIFEST_PATH)
        assert manifest_file is not None
        manifest = json.loads(manifest_file.read())

    changed_verifier = verifier.read_bytes() + b"\n# coordinated replacement\n"
    support_entry = next(
        item for item in manifest["support_files"] if item["role"] == "standalone_verifier"
    )
    support_entry["bytes"] = len(changed_verifier)
    support_entry["sha256"] = hashlib.sha256(changed_verifier).hexdigest()
    changed_manifest = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    rewritten = root / "build/release/changed-verifier.tar.gz"
    _rewrite_archive(
        original,
        rewritten,
        {
            MANIFEST_PATH: changed_manifest,
            SUPPORT_PATHS["standalone_verifier"]: changed_verifier,
        },
    )

    identity_check = subprocess.run(
        [sys.executable, "-I", str(verifier), "verify", "--archive", str(rewritten)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    identity_audit = json.loads(identity_check.stdout)
    nonisolated_check = subprocess.run(
        [sys.executable, str(verifier), "verify", "--archive", str(original)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    nonisolated_audit = json.loads(nonisolated_check.stdout)

    assert identity_check.returncode == 1
    assert identity_audit["valid"] is False
    assert (
        "embedded standalone verifier differs from executing verifier" in identity_audit["errors"]
    )
    assert nonisolated_check.returncode == 1
    assert nonisolated_audit["valid"] is False
    assert (
        "standalone verifier must run in Python isolated mode (-I)" in nonisolated_audit["errors"]
    )


def test_solo_paper_bundle_rejects_tampering_and_extra_members(tmp_path: Path) -> None:
    root, checksums = _release_tree(tmp_path)
    original = root / "build/release/original.tar.gz"
    pack_bundle(root, checksums, original)

    tampered = root / "build/release/tampered.tar.gz"
    _rewrite_archive(
        original,
        tampered,
        {"far-solo-paper-release/artifacts/tmlr_paper_pdf/paper.pdf": b"%PDF-tampered"},
    )
    tampered_audit = verify_bundle(tampered)
    assert tampered_audit["valid"] is False
    assert any("fingerprint mismatch" in error for error in tampered_audit["errors"])

    extra = root / "build/release/extra.tar.gz"
    _rewrite_archive(original, extra, {}, extra=("far-solo-paper-release/extra.txt", b"x"))
    extra_audit = verify_bundle(extra)
    assert extra_audit["valid"] is False
    assert "archive member set differs from the embedded manifest" in extra_audit["errors"]


def test_solo_paper_bundle_rejects_claim_boundary_upgrade(tmp_path: Path) -> None:
    root, checksums = _release_tree(tmp_path)
    original = root / "build/release/original.tar.gz"
    pack_bundle(root, checksums, original)
    with tarfile.open(original, "r:gz") as archive:
        manifest_file = archive.extractfile(MANIFEST_PATH)
        assert manifest_file is not None
        manifest = json.loads(manifest_file.read())
        readiness_entry = next(
            item for item in manifest["artifacts"] if item["role"] == "solo_paper_readiness_json"
        )
        readiness_file = archive.extractfile(readiness_entry["archive_path"])
        assert readiness_file is not None
        readiness = json.loads(readiness_file.read())
    manifest["boundary_flags"]["human_review"] = True

    upgraded = root / "build/release/upgraded.tar.gz"
    _rewrite_archive(
        original,
        upgraded,
        {MANIFEST_PATH: (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()},
    )
    audit = verify_bundle(upgraded)

    assert audit["valid"] is False
    assert "bundle boundary flags were upgraded or changed" in audit["errors"]

    readiness["evidence"]["stage_trace_map"]["publication_gold"] = True
    readiness_payload = (json.dumps(readiness, indent=2, sort_keys=True) + "\n").encode()
    internally_upgraded = root / "build/release/internally-upgraded.tar.gz"
    _coordinated_artifact_rewrite(
        original,
        internally_upgraded,
        "solo_paper_readiness_json",
        readiness_payload,
    )
    internal_audit = verify_bundle(internally_upgraded)

    assert internal_audit["valid"] is False
    assert "embedded stage-trace boundary was upgraded or changed" in internal_audit["errors"]


def test_solo_paper_bundle_rejects_invalid_wheel_after_coordinated_rehash(
    tmp_path: Path,
) -> None:
    root, checksums = _release_tree(tmp_path)
    original = root / "build/release/original.tar.gz"
    pack_bundle(root, checksums, original)
    wheel = b"PK-not-a-valid-wheel"
    rewritten = root / "build/release/invalid-wheel.tar.gz"
    _coordinated_artifact_rewrite(
        original,
        rewritten,
        "wheel",
        wheel,
    )
    audit = verify_bundle(rewritten)

    assert audit["valid"] is False
    assert any("wheel is not a valid ZIP archive" in error for error in audit["errors"])


def test_solo_paper_bundle_rejects_malformed_inputs_without_crashing(tmp_path: Path) -> None:
    malformed = _write(tmp_path / "malformed.tar.gz", b"not a gzip tar")
    malformed_audit = verify_bundle(malformed)
    assert malformed_audit["valid"] is False
    assert malformed_audit["errors"]

    root, checksums = _release_tree(tmp_path)
    original = root / "build/release/original.tar.gz"
    pack_bundle(root, checksums, original)
    with tarfile.open(original, "r:gz") as archive:
        manifest_file = archive.extractfile(MANIFEST_PATH)
        assert manifest_file is not None
        manifest = json.loads(manifest_file.read())
    manifest["artifacts"][0]["original_path"] = ""
    malformed_manifest = root / "build/release/malformed-manifest.tar.gz"
    _rewrite_archive(
        original,
        malformed_manifest,
        {MANIFEST_PATH: (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()},
    )
    manifest_audit = verify_bundle(malformed_manifest)

    assert manifest_audit["valid"] is False
    assert "release artifact path is missing" in manifest_audit["errors"]


def test_solo_paper_bundle_pack_rejects_dirty_source_revision(tmp_path: Path) -> None:
    root, checksums = _release_tree(tmp_path)
    (root / "pyproject.toml").write_text(
        (root / "pyproject.toml").read_text(encoding="utf-8") + "# dirty\n",
        encoding="utf-8",
    )

    try:
        pack_bundle(root, checksums, root / "build/release/dirty.tar.gz")
    except ValueError as exc:
        assert "source revision" in str(exc)
    else:
        raise AssertionError("dirty source revision unexpectedly produced a paper bundle")
