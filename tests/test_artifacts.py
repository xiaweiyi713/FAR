from __future__ import annotations

import json
from pathlib import Path

import pytest

from far.artifacts import install, pack, verify
from far.experiments.repository_maintenance import audit as audit_repository_maintenance
from far.paths import repository_root

ROOT = repository_root()


def test_diagnostic_archive_is_deterministic_and_installable(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "bundle-a").mkdir(parents=True)
    (source / "bundle-b").mkdir()
    (source / "bundle-a/result.json").write_text('{"score": 1}\n', encoding="utf-8")
    (source / "bundle-b/rows.jsonl").write_text('{"id": "x"}\n', encoding="utf-8")
    first_archive = tmp_path / "first" / "diagnostics.tar.gz"
    second_archive = tmp_path / "second" / "diagnostics.tar.gz"
    first_manifest = tmp_path / "first.json"
    second_manifest = tmp_path / "second.json"

    first = pack(source, first_archive, first_manifest)
    second = pack(source, second_archive, second_manifest)

    assert first["tree_sha256"] == second["tree_sha256"]
    assert first["archive"]["sha256"] == second["archive"]["sha256"]
    assert verify(source, first_manifest)["valid"] is True

    target = tmp_path / "installed"
    report = install(first_manifest, target, archive=first_archive)
    assert report["valid"] is True
    assert (target / "bundle-a/result.json").read_text(encoding="utf-8") == '{"score": 1}\n'
    with pytest.raises(ValueError, match="refusing to overwrite"):
        install(first_manifest, target, archive=first_archive)


def test_namespace_and_packaged_benchmark_snapshots_are_consolidated() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'include = ["far*"]' in pyproject
    for generic in ("baselines", "eval", "experiments"):
        assert not (ROOT / generic).exists()
    assert not list((ROOT / "bench").rglob("*.py"))

    source = ROOT / "bench"
    packaged = ROOT / "far/bench/data"
    files = (
        "CARD.md",
        "corpus.jsonl",
        "falsirag_bench.jsonl",
        "manifest.json",
        "split_manifest.json",
        "splits/dev.jsonl",
        "splits/test_inputs.jsonl",
        "splits/train.jsonl",
    )
    for relative in files:
        assert (source / relative).read_bytes() == (packaged / relative).read_bytes()

    manifest = json.loads((packaged / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["samples"] == 300


def test_published_diagnostic_cutover_is_complete_and_ignored() -> None:
    manifest = json.loads((ROOT / "far/data/diagnostics-v1.json").read_text(encoding="utf-8"))
    assert manifest["archive"] == {
        "bytes": 5639635,
        "filename": "far-diagnostics-v1.tar.gz",
        "published": True,
        "release_url": (
            "https://github.com/xiaweiyi713/FAR/releases/download/"
            "artifacts-v1/far-diagnostics-v1.tar.gz"
        ),
        "sha256": "5e3f28dcd81d2af3170f740611b9f59b8bbe1ee6e869379d5794730db4ecf96e",
    }
    release = audit_repository_maintenance(ROOT)["diagnostic_release"]
    assert release["cutover_valid"] is True
    assert release["tracked_files_removed"] is True
    assert release["local_install_target_ignored"] is True
