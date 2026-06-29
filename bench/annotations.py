"""Blind double-annotation, adjudication, and inter-annotator agreement tools."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, stable_rank, write_json, write_jsonl
from bench.schema import VALID_CONFLICT_TYPES, VALID_REVISION_ACTIONS

PACKET_VERSION = "falsirag-annotation-packet-v1"


def _validate_annotator_id(value: str) -> str:
    if not value or not value.replace("-", "").replace("_", "").isalnum():
        raise ValueError("annotator IDs may contain only letters, digits, hyphens, and underscores")
    return value


def _visible_row(
    sample: dict[str, Any],
    corpus: dict[str, dict[str, Any]],
    annotator_id: str,
) -> dict[str, Any]:
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for evidence in (*sample["gold_evidence"], *sample["counter_evidence"]):
        document = corpus[evidence["doc_id"]]
        evidence_by_id[evidence["evidence_id"]] = {
            "evidence_id": evidence["evidence_id"],
            "title": document["title"],
            "source": document["source"],
            "date": document.get("date"),
            "text": evidence["text_span"],
        }
    ordered_evidence = sorted(
        evidence_by_id.values(),
        key=lambda row: stable_rank(1729, annotator_id, sample["id"], row["evidence_id"]),
    )
    evidence = []
    for index, row in enumerate(ordered_evidence):
        visible = dict(row)
        visible["evidence_id"] = f"EVIDENCE_{chr(ord('A') + index)}"
        evidence.append(visible)
    return {
        "schema_version": PACKET_VERSION,
        "sample_id": sample["id"],
        "question": sample["question"],
        "initial_answer": sample["initial_answer"],
        "claims": [
            {"claim_id": claim["claim_id"], "claim": claim["claim"]} for claim in sample["claims"]
        ],
        "evidence": evidence,
        "annotator_id": annotator_id,
        "annotation": {
            "conflict_present": None,
            "conflict_type": "",
            "revision_action": "",
            "revised_answer_acceptable": None,
            "rationale": "",
        },
    }


def build_annotation_packet(
    data_dir: Path,
    output_dir: Path,
    annotator_ids: list[str],
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    if len(annotator_ids) < 2:
        raise ValueError("at least two independent annotators are required")
    annotator_ids = [_validate_annotator_id(value) for value in annotator_ids]
    if len(set(annotator_ids)) != len(annotator_ids):
        raise ValueError("annotator IDs must be unique")
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass overwrite=True to replace it")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    samples = read_jsonl(data_dir / "falsirag_bench.jsonl")
    corpus = {row["doc_id"]: row for row in read_jsonl(data_dir / "corpus.jsonl")}
    files: dict[str, str] = {}
    for annotator_id in annotator_ids:
        rows = [_visible_row(sample, corpus, annotator_id) for sample in samples]
        rows.sort(key=lambda row: stable_rank(1729, annotator_id, row["sample_id"]))
        filename = f"annotations_{annotator_id}.jsonl"
        write_jsonl(output_dir / filename, rows)
        files[annotator_id] = filename
    adjudication_rows = []
    for sample in samples:
        row = _visible_row(sample, corpus, "adjudicator")
        row.pop("annotator_id")
        row["adjudicator_id"] = ""
        row["gold_annotation"] = row.pop("annotation")
        row["gold_annotation"]["revised_answer"] = ""
        adjudication_rows.append(row)
    write_jsonl(output_dir / "adjudications.jsonl", adjudication_rows)
    manifest = {
        "schema_version": PACKET_VERSION,
        "source_fingerprints": {
            "benchmark_sha256": sha256_file(data_dir / "falsirag_bench.jsonl"),
            "corpus_sha256": sha256_file(data_dir / "corpus.jsonl"),
        },
        "samples": len(samples),
        "annotator_ids": annotator_ids,
        "annotation_files": files,
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
    }
    write_json(output_dir / "packet_manifest.json", manifest)
    (output_dir / "README.md").write_text(
        "# FalsiRAG annotation packet\n\n"
        "Annotators must work independently. Fill every `annotation` field without consulting "
        "machine seeds or another annotator. The adjudicator completes `gold_annotation` only "
        "after both annotation files are frozen. Conflict types and revision actions follow "
        "`bench/schema.py`.\n",
        encoding="utf-8",
    )
    return manifest


def cohen_kappa(left: list[str], right: list[str]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("kappa requires non-empty aligned labels")
    observed = sum(a == b for a, b in zip(left, right, strict=True)) / len(left)
    left_counts = Counter(left)
    right_counts = Counter(right)
    labels = set(left_counts) | set(right_counts)
    expected = sum(
        (left_counts[label] / len(left)) * (right_counts[label] / len(right)) for label in labels
    )
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def _validated_annotation(row: dict[str, Any], field: str) -> dict[str, Any]:
    if row.get("draft_from_machine_preannotation") and not row.get("human_reviewed"):
        raise ValueError(
            f"{row.get('sample_id')}: machine preannotation drafts require human_reviewed=true"
        )
    annotation = row.get(field)
    if not isinstance(annotation, dict):
        raise ValueError(f"{row.get('sample_id')}: missing {field}")
    present = annotation.get("conflict_present")
    if not isinstance(present, bool):
        raise ValueError(f"{row.get('sample_id')}: conflict_present must be boolean")
    conflict_type = annotation.get("conflict_type")
    if present and conflict_type not in VALID_CONFLICT_TYPES:
        raise ValueError(f"{row.get('sample_id')}: invalid conflict type")
    if not present:
        conflict_type = "no_conflict"
    action = annotation.get("revision_action")
    if action not in VALID_REVISION_ACTIONS:
        raise ValueError(f"{row.get('sample_id')}: invalid revision action")
    acceptable = annotation.get("revised_answer_acceptable")
    if not isinstance(acceptable, bool):
        raise ValueError(f"{row.get('sample_id')}: revised_answer_acceptable must be boolean")
    return {**annotation, "conflict_type": conflict_type}


def compile_annotations(
    data_dir: Path,
    packet_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    packet_manifest = json.loads((packet_dir / "packet_manifest.json").read_text(encoding="utf-8"))
    source_fingerprints = packet_manifest["source_fingerprints"]
    if source_fingerprints != {
        "benchmark_sha256": sha256_file(data_dir / "falsirag_bench.jsonl"),
        "corpus_sha256": sha256_file(data_dir / "corpus.jsonl"),
    }:
        raise ValueError("annotation packet does not match the current benchmark")
    by_annotator: dict[str, dict[str, dict[str, Any]]] = {}
    for annotator_id, filename in packet_manifest["annotation_files"].items():
        rows = read_jsonl(packet_dir / filename)
        by_annotator[annotator_id] = {
            row["sample_id"]: _validated_annotation(row, "annotation") for row in rows
        }
    sample_ids = set.intersection(*(set(rows) for rows in by_annotator.values()))
    if len(sample_ids) != packet_manifest["samples"]:
        raise ValueError("annotation files do not contain the same complete sample set")
    adjudications = {
        row["sample_id"]: _validated_annotation(row, "gold_annotation")
        for row in read_jsonl(packet_dir / packet_manifest["adjudication_file"])
    }
    if set(adjudications) != sample_ids:
        raise ValueError("adjudications are incomplete or contain unknown samples")

    pair_reports: list[dict[str, Any]] = []
    for left_id, right_id in combinations(sorted(by_annotator), 2):
        ordered_ids = sorted(sample_ids)
        left = by_annotator[left_id]
        right = by_annotator[right_id]
        pair_reports.append(
            {
                "annotators": [left_id, right_id],
                "conflict_presence_kappa": cohen_kappa(
                    [str(left[item]["conflict_present"]) for item in ordered_ids],
                    [str(right[item]["conflict_present"]) for item in ordered_ids],
                ),
                "conflict_type_kappa": cohen_kappa(
                    [str(left[item]["conflict_type"]) for item in ordered_ids],
                    [str(right[item]["conflict_type"]) for item in ordered_ids],
                ),
                "revision_action_kappa": cohen_kappa(
                    [str(left[item]["revision_action"]) for item in ordered_ids],
                    [str(right[item]["revision_action"]) for item in ordered_ids],
                ),
            }
        )
    mean_kappas = {
        key: sum(float(report[key]) for report in pair_reports) / len(pair_reports)
        for key in (
            "conflict_presence_kappa",
            "conflict_type_kappa",
            "revision_action_kappa",
        )
    }
    samples = read_jsonl(data_dir / "falsirag_bench.jsonl")
    compiled = []
    for sample in samples:
        gold = adjudications[sample["id"]]
        sample["annotation_status"] = "adjudicated"
        sample["conflict_type"] = gold["conflict_type"]
        sample["expected_revision"]["action"] = gold["revision_action"]
        revised_answer = gold.get("revised_answer")
        if isinstance(revised_answer, str) and revised_answer.strip():
            sample["expected_revision"]["revised_answer"] = revised_answer.strip()
        compiled.append(sample)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "falsirag_bench.jsonl", compiled)
    shutil.copy2(data_dir / "corpus.jsonl", output_dir / "corpus.jsonl")
    shutil.copy2(data_dir / "split_manifest.json", output_dir / "split_manifest.json")
    (output_dir / "splits").mkdir(exist_ok=True)
    for split in ("train", "dev"):
        write_jsonl(
            output_dir / "splits" / f"{split}.jsonl",
            (sample for sample in compiled if sample["split"] == split),
        )
    shutil.copy2(
        data_dir / "splits" / "test_inputs.jsonl",
        output_dir / "splits" / "test_inputs.jsonl",
    )
    report = {
        "schema_version": "falsirag-annotation-report-v1",
        "samples": len(compiled),
        "annotators": sorted(by_annotator),
        "pairwise": pair_reports,
        "mean_kappas": mean_kappas,
        "minimum_required_kappa": 0.6,
        "agreement_gate_passed": min(mean_kappas.values()) >= 0.6,
        "adjudicated": True,
    }
    write_json(output_dir / "annotation_report.json", report)
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    blockers = ["externally held blind-test protocol"]
    if not report["agreement_gate_passed"]:
        blockers.insert(0, "Cohen's kappa agreement gate did not pass")
    manifest["annotation"] = {
        "status": "adjudicated",
        "machine_seed_is_gold": False,
        "required_annotators": 2,
        "required_adjudication": True,
        "report": "annotation_report.json",
        "agreement_gate_passed": report["agreement_gate_passed"],
        "mean_kappas": mean_kappas,
    }
    manifest["publication_ready"] = False
    manifest["publication_blockers"] = blockers
    manifest["fingerprints"] = {
        "corpus_sha256": sha256_file(output_dir / "corpus.jsonl"),
        "benchmark_sha256": sha256_file(output_dir / "falsirag_bench.jsonl"),
        "split_manifest_sha256": sha256_file(output_dir / "split_manifest.json"),
    }
    write_json(output_dir / "manifest.json", manifest)
    return report
