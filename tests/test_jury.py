from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from far.bench.build.common import sha256_file, write_json, write_jsonl
from far.bench.build.jury_adjudication import (
    build_round1,
    build_round2,
    compile_jury_labels,
    freeze_round1,
    freeze_round2,
)
from far.bench.build.jury_annotate import JUROR_SPECS, PROMPT_SHA256
from far.bench.build.jury_consensus import (
    build_jury_consensus,
    fleiss_kappa,
    verify_jury_consensus,
)
from far.experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256


def _phase_b_gate() -> dict[str, object]:
    return {
        "gate_a_passed": True,
        "phase_b_authorized": True,
        "samples": 350,
        "round_manifest_sha256": "a" * 64,
        "round1_suite_manifest_sha256": "b" * 64,
        "config_sha256": "c" * 64,
    }


def _annotation(conflict_type: str) -> dict[str, object]:
    return {
        "conflict_present": conflict_type != "no_conflict",
        "conflict_type": conflict_type,
        "revision_action": "qualify_uncertainty",
        "revised_answer_acceptable": True,
        "suggested_revised_answer": "revised",
        "rationale": "Evidence-only jury rationale.",
        "confidence": 0.8,
        "needs_human_review": False,
    }


def _jury_dir(
    root: Path,
    juror_id: str,
    family: str,
    labels: dict[str, str],
    packet_sha: str,
    adjudication_sha: str,
) -> Path:
    directory = root / juror_id
    directory.mkdir()
    filename = f"jury_annotations_{juror_id}.jsonl"
    rows = [
        {
            "schema_version": "far-jury-annotation-v1",
            "sample_id": sample_id,
            "juror_id": juror_id,
            "model_family": family,
            "jury_annotation": _annotation(label),
            "publication_gold": False,
        }
        for sample_id, label in sorted(labels.items())
    ]
    write_jsonl(directory / filename, rows)
    spec = JUROR_SPECS[juror_id]
    runtime: dict[str, object] = {
        "enabled": True,
        "provider": spec["provider"],
        "model": spec["model"],
    }
    if spec["provider"] == "ollama":
        runtime["ollama_model"] = {"model": spec["model"], "digest": "d" * 64}
    run_identity = {
        "schema_version": "far-jury-run-identity-v1",
        "juror_id": juror_id,
        "model_family": family,
        "config_sha256": "e" * 64,
        "llm_runtime": runtime,
        "implementation_sha256": "f" * 64,
        "source_revision": {"git_dirty": False, "git_commit": "1" * 40},
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "prompt_sha256": PROMPT_SHA256,
        "source_packet_sha256": packet_sha,
        "source_adjudication_sha256": adjudication_sha,
        "phase_b_gate": _phase_b_gate(),
    }
    write_json(directory / "run_identity.json", run_identity)
    write_json(
        directory / "jury_annotation_manifest.json",
        {
            "schema_version": "far-jury-annotation-manifest-v1",
            "juror_id": juror_id,
            "model_family": family,
            "model": spec["model"],
            "llm_runtime": runtime,
            "config_sha256": "e" * 64,
            "run_identity_sha256": sha256_file(directory / "run_identity.json"),
            "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
            "prompt_sha256": PROMPT_SHA256,
            "source_packet_sha256": packet_sha,
            "source_adjudication_sha256": adjudication_sha,
            "phase_b_gate": _phase_b_gate(),
            "samples": len(rows),
            "expected_samples": len(rows),
            "complete": True,
            "fallbacks": 0,
            "fallback_rate": 0.0,
            "annotation_file": filename,
            "annotation_sha256": sha256_file(directory / filename),
            "publication_gold": False,
            "human_annotator": False,
        },
    )
    return directory


def _fixture(tmp_path: Path) -> tuple[Path, Path, list[Path]]:
    data = tmp_path / "data"
    data.mkdir()
    benchmark = [
        {"id": "S1", "category": "temporal_shift", "conflict_type": "temporal"},
        {"id": "S2", "category": "entity_confusion", "conflict_type": "entity"},
        {"id": "S3", "category": "numerical_conflict", "conflict_type": "numerical"},
    ]
    write_jsonl(data / "falsirag_bench.jsonl", benchmark)
    packet = tmp_path / "packet"
    packet.mkdir()
    blind_rows = [
        {
            "schema_version": "falsirag-annotation-packet-v1",
            "sample_id": row["id"],
            "question": "question",
            "initial_answer": "initial",
            "claims": [{"claim_id": "C1", "claim": "claim"}],
            "evidence": [
                {
                    "evidence_id": "EVIDENCE_A",
                    "title": "title",
                    "source": "source",
                    "date": None,
                    "text": "evidence",
                }
            ],
            "adjudicator_id": "",
            "gold_annotation": {},
        }
        for row in benchmark
    ]
    write_jsonl(packet / "adjudications.jsonl", blind_rows)
    write_json(
        packet / "packet_manifest.json",
        {
            "schema_version": "falsirag-annotation-packet-v1",
            "source_fingerprints": {
                "benchmark_sha256": sha256_file(data / "falsirag_bench.jsonl"),
                "corpus_sha256": "0" * 64,
            },
            "samples": len(benchmark),
            "adjudication_file": "adjudications.jsonl",
            "blind_fields_omitted": [
                "category",
                "split",
                "conflict_type",
                "expected_revision",
                "source_metadata",
                "annotation_status",
                "evidence roles",
            ],
        },
    )
    packet_sha = sha256_file(packet / "packet_manifest.json")
    adjudication_sha = sha256_file(packet / "adjudications.jsonl")
    labels = {"S1": "temporal", "S2": "entity", "S3": "entity"}
    jurors = [
        _jury_dir(tmp_path, "J1", "deepseek", labels, packet_sha, adjudication_sha),
        _jury_dir(tmp_path, "J2", "glm", labels, packet_sha, adjudication_sha),
        _jury_dir(tmp_path, "J3", "meta", labels, packet_sha, adjudication_sha),
    ]
    return data, packet, jurors


def _fill_packet(source: Path, destination: Path) -> None:
    rows = []
    for row in [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]:
        row["author_annotation"] = {
            "conflict_present": True,
            "conflict_type": "numerical",
            "revision_action": "qualify_uncertainty",
            "revised_answer_acceptable": True,
            "revised_answer": "revised",
            "rationale": "Author evidence-only decision.",
        }
        rows.append(row)
    write_jsonl(destination, rows)


def test_fleiss_kappa_perfect_agreement() -> None:
    assert fleiss_kappa([["a", "a", "a"], ["b", "b", "b"]]) == 1.0


def test_jury_consensus_and_delayed_author_adjudication(tmp_path: Path) -> None:
    data, packet, jurors = _fixture(tmp_path)
    consensus_dir = tmp_path / "consensus"
    consensus = build_jury_consensus(data, jurors, consensus_dir)
    assert consensus["gate_k_passed"] is True
    assert consensus["dispositions"] == {"disputed": 1, "unanimous": 2}
    assert verify_jury_consensus(data, jurors, consensus_dir)["valid"] is True

    adjudication = tmp_path / "adjudication"
    started = datetime(2026, 7, 4, tzinfo=timezone.utc)
    manifest = build_round1(packet, consensus_dir, adjudication, now=started)
    assert manifest["samples"] == 1
    completed1 = tmp_path / "round1_done.jsonl"
    _fill_packet(adjudication / "round1_packet.jsonl", completed1)
    freeze_round1(adjudication, completed1, now=started)
    with pytest.raises(ValueError, match="locked"):
        build_round2(
            packet,
            consensus_dir,
            adjudication,
            now=started + timedelta(days=13, hours=23),
        )
    repeat = build_round2(
        packet,
        consensus_dir,
        adjudication,
        now=started + timedelta(days=14),
    )
    assert repeat["samples"] == 1
    completed2 = tmp_path / "round2_done.jsonl"
    _fill_packet(adjudication / "round2_packet.jsonl", completed2)
    consistency = freeze_round2(adjudication, completed2)
    assert consistency["gate_s_passed"] is True

    labels_dir = tmp_path / "labels"
    labels = compile_jury_labels(consensus_dir, adjudication, jurors, labels_dir)
    assert labels["jury_gold"] is True
    assert labels["publication_gold"] is False
    assert labels["samples"] == 3


def test_jury_rejects_system_family_overlap(tmp_path: Path) -> None:
    data, _, jurors = _fixture(tmp_path)
    manifest_path = jurors[0] / "jury_annotation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["model_family"] = "qwen"
    write_json(manifest_path, manifest)
    with pytest.raises(ValueError, match=r"preregistered identity|overlaps"):
        build_jury_consensus(data, jurors, tmp_path / "consensus")


def test_jury_binary_fallback_changes_active_votes_and_joint_majority(tmp_path: Path) -> None:
    data, packet, _ = _fixture(tmp_path)
    packet_sha = sha256_file(packet / "packet_manifest.json")
    adjudication_sha = sha256_file(packet / "adjudications.jsonl")
    sample_ids = ("S1", "S2", "S3")
    juror_root = tmp_path / "binary_jurors"
    juror_root.mkdir()
    jurors = [
        _jury_dir(
            juror_root,
            "J1",
            "deepseek",
            dict.fromkeys(sample_ids, "temporal"),
            packet_sha,
            adjudication_sha,
        ),
        _jury_dir(
            juror_root,
            "J2",
            "glm",
            dict.fromkeys(sample_ids, "entity"),
            packet_sha,
            adjudication_sha,
        ),
        _jury_dir(
            juror_root,
            "J3",
            "meta",
            dict.fromkeys(sample_ids, "numerical"),
            packet_sha,
            adjudication_sha,
        ),
    ]
    output = tmp_path / "binary_consensus"
    report = build_jury_consensus(data, jurors, output)
    assert report["gate_k_primary_passed"] is False
    assert report["gate_k_binary_fallback_passed"] is True
    assert report["active_label_granularity"] == "binary"
    rows = [
        json.loads(line) for line in (output / "jury_consensus_rows.jsonl").read_text().splitlines()
    ]
    assert {row["majority_label"] for row in rows} == {"conflict"}
    assert {tuple(row["joint_majority_fields"]) for row in rows} == {
        ("conflict_present", "revision_action", "revised_answer_acceptable")
    }
    assert all(len(set(row["typed_juror_votes"].values())) == 3 for row in rows)


def test_jury_verifier_rejects_tampering(tmp_path: Path) -> None:
    data, _, jurors = _fixture(tmp_path)
    consensus_dir = tmp_path / "consensus"
    build_jury_consensus(data, jurors, consensus_dir)
    path = jurors[0] / "jury_annotations_J1.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    assert verify_jury_consensus(data, jurors, consensus_dir)["valid"] is False
