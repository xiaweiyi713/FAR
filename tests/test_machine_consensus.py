from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.build.common import sha256_file, write_json, write_jsonl
from bench.build.machine_consensus import build_machine_consensus
from experiments.solo_readiness import audit as audit_solo_readiness

ROOT = Path(__file__).resolve().parents[1]


def _machine_sources(tmp_path: Path) -> tuple[Path, Path]:
    benchmark = [
        json.loads(line)
        for line in (ROOT / "bench/falsirag_bench.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    fingerprints = {
        "benchmark_sha256": sha256_file(ROOT / "bench/falsirag_bench.jsonl"),
        "corpus_sha256": sha256_file(ROOT / "bench/corpus.jsonl"),
    }
    pre_dir = tmp_path / "pre"
    weak_dir = tmp_path / "weak"
    pre_dir.mkdir()
    weak_dir.mkdir()
    pre_rows = []
    weak_rows = []
    for row in benchmark:
        annotation = {
            "conflict_present": True,
            "conflict_type": row["conflict_type"],
            "revision_action": row["expected_revision"]["action"],
            "revised_answer_acceptable": True,
            "suggested_revised_answer": row["expected_revision"]["revised_answer"],
            "rationale": "Independent test machine signal.",
            "confidence": 0.9,
            "needs_human_review": True,
        }
        pre_rows.append(
            {
                "sample_id": row["id"],
                "preannotator_id": "test_llm",
                "preannotation": annotation,
                "publication_gold": False,
            }
        )
        weak_rows.append(
            {
                "sample_id": row["id"],
                "weak_annotator_id": "test_rules",
                "weak_annotation": {**annotation, "abstained": False, "signals": []},
                "publication_gold": False,
            }
        )
    pre_path = pre_dir / "preannotations_test_llm.jsonl"
    weak_path = weak_dir / "weak_annotations.jsonl"
    write_jsonl(pre_path, pre_rows)
    write_jsonl(weak_path, weak_rows)
    write_json(
        pre_dir / "preannotation_manifest.json",
        {
            "preannotator_id": "test_llm",
            "preannotation_file": pre_path.name,
            "source_fingerprints": fingerprints,
            "publication_gold": False,
        },
    )
    write_json(
        weak_dir / "weak_annotation_manifest.json",
        {
            "weak_annotator_id": "test_rules",
            "weak_annotation_file": weak_path.name,
            "source_fingerprints": fingerprints,
            "publication_gold": False,
        },
    )
    return pre_dir, weak_dir


def test_machine_consensus_builds_non_human_audit(tmp_path: Path) -> None:
    pre_dir, weak_dir = _machine_sources(tmp_path)
    report = build_machine_consensus(
        ROOT / "bench",
        tmp_path / "out",
        preannotation_dirs=[pre_dir],
        weak_label_dirs=[weak_dir],
    )
    assert report["ready_for_solo_machine_audited_study"] is True
    assert report["dispositions"] == {"machine_confirmed": 300}
    assert report["publication_gold"] is False
    assert report["human_annotation_replaced"] is False
    assert report["can_report_human_iaa"] is False


def test_machine_consensus_rejects_stale_source_fingerprint(tmp_path: Path) -> None:
    pre_dir, weak_dir = _machine_sources(tmp_path)
    manifest_path = pre_dir / "preannotation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_fingerprints"]["benchmark_sha256"] = "0" * 64
    write_json(manifest_path, manifest)
    with pytest.raises(ValueError, match="source fingerprints"):
        build_machine_consensus(
            ROOT / "bench",
            tmp_path / "out",
            preannotation_dirs=[pre_dir],
            weak_label_dirs=[weak_dir],
        )


def test_solo_readiness_is_separate_and_fails_closed(tmp_path: Path) -> None:
    report = audit_solo_readiness(
        ROOT / "bench",
        tmp_path / "missing-machine-report.json",
        tmp_path / "missing-suite",
        tmp_path / "missing-bundle",
    )
    assert report["complete"] is False
    assert report["strict_submission_gate_affected"] is False
    assert report["gates"][0]["passed"] is True
    assert set(report["blockers"]) == {
        "machine_annotation_audit",
        "complete_local_dev_suite",
        "gold_free_local_test_bundle",
    }
