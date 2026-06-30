"""Compare non-gold machine preannotations and weak labels."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl

AUDIT_VERSION = "falsirag-machine-label-audit-v1"


def _load_preannotations(preannotation_dir: Path) -> tuple[list[dict[str, Any]], Path]:
    manifest_path = preannotation_dir / "preannotation_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        path = preannotation_dir / str(manifest["preannotation_file"])
    else:
        candidates = sorted(preannotation_dir.glob("preannotations_*.jsonl"))
        if len(candidates) != 1:
            raise FileNotFoundError(
                f"{preannotation_dir} must contain one preannotations_*.jsonl file "
                "or a preannotation_manifest.json"
            )
        path = candidates[0]
    return read_jsonl(path), path


def _load_weak_labels(weak_label_dir: Path) -> tuple[list[dict[str, Any]], Path]:
    manifest_path = weak_label_dir / "weak_annotation_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        path = weak_label_dir / str(manifest["weak_annotation_file"])
    else:
        path = weak_label_dir / "weak_annotations.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"weak label file not found: {path}")
    return read_jsonl(path), path


def _annotation_view(annotation: dict[str, Any]) -> dict[str, Any]:
    conflict_present = bool(annotation.get("conflict_present"))
    conflict_type = str(annotation.get("conflict_type", ""))
    if not conflict_present:
        conflict_type = "no_conflict"
    return {
        "conflict_present": conflict_present,
        "conflict_type": conflict_type,
        "revision_action": str(annotation.get("revision_action", "")),
        "abstained": bool(annotation.get("abstained", False)),
    }


def audit_machine_labels(
    preannotation_dir: Path,
    weak_label_dir: Path,
    output_dir: Path,
    *,
    packet_dir: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    pre_rows, pre_path = _load_preannotations(preannotation_dir)
    weak_rows, weak_path = _load_weak_labels(weak_label_dir)
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass --overwrite to replace it")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    pre_by_id = {str(row["sample_id"]): row for row in pre_rows}
    weak_by_id = {str(row["sample_id"]): row for row in weak_rows}
    duplicate_pre = len(pre_by_id) != len(pre_rows)
    duplicate_weak = len(weak_by_id) != len(weak_rows)
    shared_ids = sorted(set(pre_by_id) & set(weak_by_id))
    weak_non_abstained_ids = [
        sample_id
        for sample_id in shared_ids
        if not bool(weak_by_id[sample_id]["weak_annotation"].get("abstained", False))
    ]

    compared_rows: list[dict[str, Any]] = []
    for sample_id in shared_ids:
        pre = _annotation_view(pre_by_id[sample_id]["preannotation"])
        weak = _annotation_view(weak_by_id[sample_id]["weak_annotation"])
        compared_rows.append(
            {
                "sample_id": sample_id,
                "preannotation": pre,
                "weak_annotation": weak,
                "agreements": {
                    "conflict_present": pre["conflict_present"] == weak["conflict_present"],
                    "conflict_type": pre["conflict_type"] == weak["conflict_type"],
                    "revision_action": pre["revision_action"] == weak["revision_action"],
                },
                "needs_priority_review": (
                    not weak["abstained"]
                    and (
                        pre["conflict_type"] != weak["conflict_type"]
                        or pre["revision_action"] != weak["revision_action"]
                    )
                ),
            }
        )
    write_jsonl(output_dir / "machine_label_comparison.jsonl", compared_rows)

    def _rate(key: str, rows: list[dict[str, Any]]) -> float | None:
        if not rows:
            return None
        return sum(bool(row["agreements"][key]) for row in rows) / len(rows)

    non_abstained_rows = [row for row in compared_rows if not row["weak_annotation"]["abstained"]]
    priority_ids = [row["sample_id"] for row in compared_rows if row["needs_priority_review"]]
    packet_samples: int | None = None
    missing_packet_ids: list[str] = []
    if packet_dir is not None:
        packet_manifest = json.loads(
            (packet_dir / "packet_manifest.json").read_text(encoding="utf-8")
        )
        packet_rows = read_jsonl(packet_dir / packet_manifest["adjudication_file"])
        packet_ids = {str(row["sample_id"]) for row in packet_rows}
        packet_samples = len(packet_ids)
        missing_packet_ids = sorted(packet_ids - set(shared_ids))

    result = {
        "schema_version": AUDIT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "preannotation_file": str(pre_path),
        "preannotation_sha256": sha256_file(pre_path),
        "weak_annotation_file": str(weak_path),
        "weak_annotation_sha256": sha256_file(weak_path),
        "preannotation_samples": len(pre_rows),
        "weak_label_samples": len(weak_rows),
        "shared_samples": len(shared_ids),
        "duplicate_preannotation_ids": duplicate_pre,
        "duplicate_weak_label_ids": duplicate_weak,
        "weak_non_abstained_shared_samples": len(weak_non_abstained_ids),
        "agreement_rates_all_shared": {
            "conflict_present": _rate("conflict_present", compared_rows),
            "conflict_type": _rate("conflict_type", compared_rows),
            "revision_action": _rate("revision_action", compared_rows),
        },
        "agreement_rates_weak_non_abstained": {
            "conflict_present": _rate("conflict_present", non_abstained_rows),
            "conflict_type": _rate("conflict_type", non_abstained_rows),
            "revision_action": _rate("revision_action", non_abstained_rows),
        },
        "priority_review_samples": len(priority_ids),
        "priority_review_sample_ids_preview": priority_ids[:50],
        "packet_samples": packet_samples,
        "missing_packet_samples": len(missing_packet_ids),
        "missing_packet_sample_ids_preview": missing_packet_ids[:50],
        "comparison_file": "machine_label_comparison.jsonl",
        "publication_gold": False,
        "can_satisfy_human_annotation_gate": False,
        "required_next_step": (
            "Use disagreements to prioritize review. Machine-machine agreement is not "
            "human IAA and cannot produce Cohen's kappa for publication."
        ),
    }
    write_json(output_dir / "machine_label_audit.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preannotation-dir", type=Path, required=True)
    parser.add_argument("--weak-label-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--packet-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    result = audit_machine_labels(
        args.preannotation_dir,
        args.weak_label_dir,
        args.output_dir,
        packet_dir=args.packet_dir,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
