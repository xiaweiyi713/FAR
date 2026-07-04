"""Build, freeze, repeat, and compile author-blind adjudication for jury disputes."""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bench.annotations import _validated_annotation, stable_rank
from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256, verify_active_protocol

ROUND1_SEED = 314159
ROUND2_SEED = 271828
MINIMUM_REPEAT_DELAY = timedelta(days=14)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("adjudication timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _consensus(consensus_dir: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    report = json.loads((consensus_dir / "jury_consensus_report.json").read_text(encoding="utf-8"))
    rows_path = consensus_dir / str(report["jury_consensus_rows"])
    if sha256_file(rows_path) != report.get("jury_consensus_rows_sha256"):
        raise ValueError("jury consensus rows fingerprint mismatch")
    rows = {str(row["sample_id"]): row for row in read_jsonl(rows_path)}
    if len(rows) != int(report.get("samples", -1)):
        raise ValueError("jury consensus sample count mismatch")
    return report, rows


def _blind_sources(packet_dir: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest_path = packet_dir / "packet_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = {
        str(row["sample_id"]): row
        for row in read_jsonl(packet_dir / str(manifest["adjudication_file"]))
    }
    return manifest, rows


def _blank_row(source: dict[str, Any], *, round_name: str) -> dict[str, Any]:
    visible = {
        key: value
        for key, value in source.items()
        if key not in {"gold_annotation", "adjudicator_id", "annotator_id", "annotation"}
    }
    visible["adjudication_round"] = round_name
    visible["author_annotation"] = {
        "conflict_present": None,
        "conflict_type": "",
        "revision_action": "",
        "revised_answer_acceptable": None,
        "revised_answer": "",
        "rationale": "",
    }
    return visible


def build_round1(
    packet_dir: Path,
    consensus_dir: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    verify_active_protocol()
    report, consensus_rows = _consensus(consensus_dir)
    if report.get("gate_k_passed") is not True:
        raise ValueError("G-K must pass before author adjudication")
    _, blind_rows = _blind_sources(packet_dir)
    disputed = [row for row in consensus_rows.values() if row["disposition"] == "disputed"]
    if not disputed:
        raise ValueError("jury consensus contains no disputed rows to adjudicate")
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass --overwrite")
        marker = output_dir / "adjudication_manifest.json"
        if not marker.is_file():
            raise ValueError("refusing to overwrite a directory without an adjudication manifest")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        disputed,
        key=lambda row: stable_rank(ROUND1_SEED, "author-blind-round1", row["sample_id"]),
    )
    packet_rows = [
        _blank_row(blind_rows[str(row["sample_id"])], round_name="round1") for row in ordered
    ]
    packet_path = output_dir / "round1_packet.jsonl"
    write_jsonl(packet_path, packet_rows)
    created = (now or _utcnow()).astimezone(timezone.utc)
    manifest = {
        "schema_version": "far-jury-author-adjudication-v1",
        "created_at": created.isoformat(),
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "source_packet_sha256": sha256_file(packet_dir / "packet_manifest.json"),
        "source_consensus_sha256": sha256_file(consensus_dir / "jury_consensus_report.json"),
        "source_consensus_rows_sha256": report["jury_consensus_rows_sha256"],
        "samples": len(packet_rows),
        "round1_seed": ROUND1_SEED,
        "round1_packet": packet_path.name,
        "round1_packet_sha256": sha256_file(packet_path),
        "minimum_repeat_days": 14,
        "round2_eligible_at": (created + MINIMUM_REPEAT_DELAY).isoformat(),
        "jury_votes_hidden": True,
        "construction_labels_hidden": True,
        "system_outputs_hidden": True,
        "human_iaa": False,
    }
    write_json(output_dir / "adjudication_manifest.json", manifest)
    (output_dir / "README.md").write_text(
        "# Author-blind jury adjudication\n\n"
        "Edit only `author_annotation` in `round1_packet.jsonl`; do not inspect the jury "
        "consensus or construction labels while judging. Then freeze with "
        "`falsirag-jury-adjudication freeze-round1`. The repeat packet cannot be built "
        "until the recorded 14-day interval has elapsed. This is author adjudication, "
        "not independent human annotation or human IAA.\n",
        encoding="utf-8",
    )
    return manifest


def _completed_rows(path: Path, expected_ids: set[str]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        sample_id = str(row.get("sample_id", ""))
        if not sample_id or sample_id in rows:
            raise ValueError("completed adjudication has missing or duplicate sample IDs")
        row["author_annotation"] = _validated_annotation(row, "author_annotation")
        if (
            row["author_annotation"]["conflict_present"]
            and not str(row["author_annotation"].get("revised_answer", "")).strip()
        ):
            raise ValueError(f"{sample_id}: conflict-positive adjudication needs a revision")
        rows[sample_id] = row
    if set(rows) != expected_ids:
        raise ValueError("completed adjudication does not exactly cover the packet")
    return rows


def freeze_round1(
    output_dir: Path,
    completed_file: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    manifest_path = output_dir / "adjudication_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    packet_path = output_dir / str(manifest["round1_packet"])
    if sha256_file(packet_path) != manifest.get("round1_packet_sha256"):
        raise ValueError("round1 packet changed after creation")
    packet_rows = read_jsonl(packet_path)
    completed = _completed_rows(completed_file, {str(row["sample_id"]) for row in packet_rows})
    destination = output_dir / "round1_completed.jsonl"
    write_jsonl(destination, [completed[sample_id] for sample_id in sorted(completed)])
    frozen_at = (now or _utcnow()).astimezone(timezone.utc)
    freeze = {
        "schema_version": "far-jury-author-round1-freeze-v1",
        "frozen_at": frozen_at.isoformat(),
        "samples": len(completed),
        "completed_file": destination.name,
        "completed_sha256": sha256_file(destination),
        "round2_eligible_at": (frozen_at + MINIMUM_REPEAT_DELAY).isoformat(),
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
    }
    write_json(output_dir / "round1_freeze.json", freeze)
    return freeze


def build_round2(
    packet_dir: Path,
    consensus_dir: Path,
    output_dir: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    freeze = json.loads((output_dir / "round1_freeze.json").read_text(encoding="utf-8"))
    current = (now or _utcnow()).astimezone(timezone.utc)
    eligible_at = _parse_time(str(freeze["round2_eligible_at"]))
    if current < eligible_at:
        raise ValueError(f"round2 is locked until {eligible_at.isoformat()}")
    completed_path = output_dir / str(freeze["completed_file"])
    if sha256_file(completed_path) != freeze.get("completed_sha256"):
        raise ValueError("round1 completion changed after freezing")
    _, consensus_rows = _consensus(consensus_dir)
    _, blind_rows = _blind_sources(packet_dir)
    completed_ids = {str(row["sample_id"]) for row in read_jsonl(completed_path)}
    by_category: dict[str, list[str]] = defaultdict(list)
    for sample_id in completed_ids:
        by_category[str(consensus_rows[sample_id]["category"])].append(sample_id)
    selected: list[str] = []
    for category, sample_ids in sorted(by_category.items()):
        ordered = sorted(sample_ids)
        random.Random(f"{ROUND2_SEED}:{category}").shuffle(ordered)
        selected.extend(ordered[: math.ceil(0.20 * len(ordered))])
    selected.sort(key=lambda sample_id: stable_rank(ROUND2_SEED, "author-blind-round2", sample_id))
    packet_rows = [_blank_row(blind_rows[sample_id], round_name="round2") for sample_id in selected]
    packet_path = output_dir / "round2_packet.jsonl"
    write_jsonl(packet_path, packet_rows)
    manifest = {
        "schema_version": "far-jury-author-round2-packet-v1",
        "created_at": current.isoformat(),
        "samples": len(packet_rows),
        "source_round1_sha256": freeze["completed_sha256"],
        "stratified_fraction": 0.20,
        "seed": ROUND2_SEED,
        "packet_file": packet_path.name,
        "packet_sha256": sha256_file(packet_path),
        "round1_labels_hidden": True,
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
    }
    write_json(output_dir / "round2_manifest.json", manifest)
    return manifest


def freeze_round2(output_dir: Path, completed_file: Path) -> dict[str, Any]:
    manifest = json.loads((output_dir / "round2_manifest.json").read_text(encoding="utf-8"))
    packet_path = output_dir / str(manifest["packet_file"])
    if sha256_file(packet_path) != manifest.get("packet_sha256"):
        raise ValueError("round2 packet changed after creation")
    packet_rows = read_jsonl(packet_path)
    completed = _completed_rows(completed_file, {str(row["sample_id"]) for row in packet_rows})
    destination = output_dir / "round2_completed.jsonl"
    write_jsonl(destination, [completed[sample_id] for sample_id in sorted(completed)])
    round1_freeze = json.loads((output_dir / "round1_freeze.json").read_text(encoding="utf-8"))
    round1_path = output_dir / str(round1_freeze["completed_file"])
    round1 = {str(row["sample_id"]): row for row in read_jsonl(round1_path)}
    fields = (
        "conflict_present",
        "conflict_type",
        "revision_action",
        "revised_answer_acceptable",
    )
    agreements = []
    for sample_id, row in completed.items():
        left = round1[sample_id]["author_annotation"]
        right = row["author_annotation"]
        agreements.append(all(left.get(field) == right.get(field) for field in fields))
    rate = sum(agreements) / len(agreements) if agreements else 0.0
    report = {
        "schema_version": "far-jury-author-self-consistency-v1",
        "samples": len(agreements),
        "joint_fields": list(fields),
        "joint_agreements": sum(agreements),
        "self_consistency": rate,
        "minimum_required": 0.80,
        "gate_s_passed": rate >= 0.80,
        "round1_sha256": sha256_file(round1_path),
        "round2_file": destination.name,
        "round2_sha256": sha256_file(destination),
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "human_iaa": False,
    }
    write_json(output_dir / "self_consistency_report.json", report)
    return report


def _load_juror_rows(directory: Path) -> tuple[str, dict[str, dict[str, Any]]]:
    manifest = json.loads((directory / "jury_annotation_manifest.json").read_text(encoding="utf-8"))
    path = directory / str(manifest["annotation_file"])
    if sha256_file(path) != manifest.get("annotation_sha256"):
        raise ValueError("juror annotation fingerprint mismatch")
    return str(manifest["juror_id"]), {str(row["sample_id"]): row for row in read_jsonl(path)}


def compile_jury_labels(
    consensus_dir: Path,
    adjudication_dir: Path,
    juror_dirs: list[Path],
    output_dir: Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    verify_active_protocol()
    report, consensus_rows = _consensus(consensus_dir)
    consistency = json.loads(
        (adjudication_dir / "self_consistency_report.json").read_text(encoding="utf-8")
    )
    freeze = json.loads((adjudication_dir / "round1_freeze.json").read_text(encoding="utf-8"))
    round1_path = adjudication_dir / str(freeze["completed_file"])
    if sha256_file(round1_path) != freeze.get("completed_sha256"):
        raise ValueError("round1 adjudication fingerprint mismatch")
    author = {str(row["sample_id"]): row for row in read_jsonl(round1_path)}
    jurors = dict(_load_juror_rows(directory) for directory in juror_dirs)
    if set(jurors) != {str(item["juror_id"]) for item in report["jurors"]}:
        raise ValueError("juror sources do not match consensus report")
    use_disputed = consistency.get("gate_s_passed") is True
    labels: list[dict[str, Any]] = []
    excluded: list[str] = []
    for sample_id, consensus in sorted(consensus_rows.items()):
        if consensus["disposition"] == "disputed":
            if not use_disputed:
                excluded.append(sample_id)
                continue
            annotation = author[sample_id]["author_annotation"]
            provenance = "author_blind_adjudication"
        else:
            juror_id = str(consensus["selected_juror_id"])
            source = jurors[juror_id][sample_id]["jury_annotation"]
            annotation = {
                **source,
                "revised_answer": source.get("suggested_revised_answer", ""),
            }
            provenance = "cross_family_llm_joint_majority"
        labels.append(
            {
                "sample_id": sample_id,
                "gold_annotation": annotation,
                "label_provenance": provenance,
                "jury_gold": True,
                "publication_gold": False,
            }
        )
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass --overwrite")
        marker = output_dir / "manifest.json"
        if not marker.is_file():
            raise ValueError("refusing to overwrite a directory without a jury-label manifest")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    labels_path = output_dir / "labels.jsonl"
    write_jsonl(labels_path, labels)
    manifest = {
        "schema_version": "far-jury-labels-v1",
        "label_provenance": "cross_family_llm_jury_plus_author_blind_adjudication",
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "jury_gold": True,
        "publication_gold": False,
        "human_iaa": False,
        "gate_k_passed": report.get("gate_k_passed"),
        "gate_s_passed": consistency.get("gate_s_passed"),
        "samples": len(labels),
        "excluded_disputed_samples": excluded,
        "labels_file": labels_path.name,
        "labels_sha256": sha256_file(labels_path),
        "consensus_report_sha256": sha256_file(consensus_dir / "jury_consensus_report.json"),
        "self_consistency_report_sha256": sha256_file(
            adjudication_dir / "self_consistency_report.json"
        ),
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build-round1")
    build.add_argument("--packet-dir", type=Path, required=True)
    build.add_argument("--consensus-dir", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--overwrite", action="store_true")
    freeze1 = subparsers.add_parser("freeze-round1")
    freeze1.add_argument("--output-dir", type=Path, required=True)
    freeze1.add_argument("--completed-file", type=Path, required=True)
    repeat = subparsers.add_parser("build-round2")
    repeat.add_argument("--packet-dir", type=Path, required=True)
    repeat.add_argument("--consensus-dir", type=Path, required=True)
    repeat.add_argument("--output-dir", type=Path, required=True)
    freeze2 = subparsers.add_parser("freeze-round2")
    freeze2.add_argument("--output-dir", type=Path, required=True)
    freeze2.add_argument("--completed-file", type=Path, required=True)
    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--consensus-dir", type=Path, required=True)
    compile_parser.add_argument("--adjudication-dir", type=Path, required=True)
    compile_parser.add_argument("--juror-dir", type=Path, action="append", required=True)
    compile_parser.add_argument("--output-dir", type=Path, required=True)
    compile_parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.command == "build-round1":
        result = build_round1(
            args.packet_dir,
            args.consensus_dir,
            args.output_dir,
            overwrite=args.overwrite,
        )
    elif args.command == "freeze-round1":
        result = freeze_round1(args.output_dir, args.completed_file)
    elif args.command == "build-round2":
        result = build_round2(args.packet_dir, args.consensus_dir, args.output_dir)
    elif args.command == "freeze-round2":
        result = freeze_round2(args.output_dir, args.completed_file)
    else:
        result = compile_jury_labels(
            args.consensus_dir,
            args.adjudication_dir,
            args.juror_dir,
            args.output_dir,
            overwrite=args.overwrite,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
