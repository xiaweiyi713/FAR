from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from bench.build.common import sha256_file, write_json, write_jsonl
from bench.build.jury_adjudication import (
    build_round1,
    build_round2,
    compile_jury_labels,
    freeze_round1,
    freeze_round2,
)
from bench.build.jury_annotate import PROMPT_SHA256
from bench.build.jury_consensus import build_jury_consensus, fleiss_kappa
from experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256


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
    write_json(
        directory / "jury_annotation_manifest.json",
        {
            "schema_version": "far-jury-annotation-manifest-v1",
            "juror_id": juror_id,
            "model_family": family,
            "model": f"{family}-model",
            "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
            "prompt_sha256": PROMPT_SHA256,
            "source_packet_sha256": packet_sha,
            "fallbacks": 0,
            "annotation_file": filename,
            "annotation_sha256": sha256_file(directory / filename),
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
            "schema_version": "packet",
            "sample_id": row["id"],
            "question": "question",
            "initial_answer": "initial",
            "claims": [{"claim_id": "C1", "claim": "claim"}],
            "evidence": [{"evidence_id": "EVIDENCE_A", "text": "evidence"}],
            "adjudicator_id": "",
            "gold_annotation": {},
        }
        for row in benchmark
    ]
    write_jsonl(packet / "adjudications.jsonl", blind_rows)
    write_json(
        packet / "packet_manifest.json",
        {"adjudication_file": "adjudications.jsonl", "source_fingerprints": {}},
    )
    packet_sha = sha256_file(packet / "packet_manifest.json")
    labels = {"S1": "temporal", "S2": "entity", "S3": "entity"}
    jurors = [
        _jury_dir(tmp_path, "J1", "deepseek", labels, packet_sha),
        _jury_dir(tmp_path, "J2", "glm", labels, packet_sha),
        _jury_dir(tmp_path, "J3", "meta", labels, packet_sha),
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
    with pytest.raises(ValueError, match="overlaps"):
        build_jury_consensus(data, jurors, tmp_path / "consensus")
