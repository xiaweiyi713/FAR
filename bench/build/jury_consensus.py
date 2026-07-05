"""Aggregate three cross-family jurors and execute the preregistered G-K gate."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

from bench.annotations import cohen_kappa
from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from bench.build.jury_annotate import JURY_TYPES, PROMPT_SHA256, _is_fallback
from experiments.protocol_2plus4 import (
    PROTOCOL_ACTIVE_SHA256,
    SYSTEM_MODEL_FAMILIES,
    verify_active_protocol,
)


def fleiss_kappa(ratings: list[list[str]]) -> float:
    if not ratings or any(len(row) != len(ratings[0]) for row in ratings):
        raise ValueError("Fleiss kappa requires non-empty equal-width ratings")
    raters = len(ratings[0])
    if raters < 2:
        raise ValueError("Fleiss kappa requires at least two raters")
    categories = sorted({label for row in ratings for label in row})
    category_totals: Counter[str] = Counter()
    agreements: list[float] = []
    for row in ratings:
        counts = Counter(row)
        category_totals.update(counts)
        agreements.append(
            (sum(count * count for count in counts.values()) - raters) / (raters * (raters - 1))
        )
    observed = sum(agreements) / len(agreements)
    expected = sum(
        (category_totals[category] / (len(ratings) * raters)) ** 2 for category in categories
    )
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def _load_juror(directory: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest = json.loads((directory / "jury_annotation_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "far-jury-annotation-manifest-v1":
        raise ValueError(f"{directory}: unsupported jury annotation manifest schema")
    if manifest.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256:
        raise ValueError(f"{directory}: jury annotation uses a stale protocol")
    if manifest.get("prompt_sha256") != PROMPT_SHA256:
        raise ValueError(f"{directory}: jury annotation prompt fingerprint mismatch")
    if any(
        not str(manifest.get(field, "")).strip()
        for field in (
            "config_sha256",
            "source_packet_sha256",
            "source_adjudication_sha256",
        )
    ):
        raise ValueError(f"{directory}: jury source fingerprints are incomplete")
    if manifest.get("complete") is not True:
        raise ValueError(f"{directory}: jury annotation manifest is incomplete")
    if (
        manifest.get("publication_gold") is not False
        or manifest.get("human_annotator") is not False
    ):
        raise ValueError(f"{directory}: jury source is mislabeled as human or publication gold")
    path = directory / str(manifest["annotation_file"])
    if sha256_file(path) != manifest.get("annotation_sha256"):
        raise ValueError(f"{directory}: jury annotation fingerprint mismatch")
    rows: dict[str, dict[str, Any]] = {}
    juror_id = str(manifest.get("juror_id", ""))
    family = str(manifest.get("model_family", ""))
    if not juror_id or not family:
        raise ValueError(f"{directory}: jury identity is missing")
    for row in read_jsonl(path):
        sample_id = str(row["sample_id"])
        if sample_id in rows:
            raise ValueError(f"{directory}: duplicate sample {sample_id}")
        if (
            row.get("schema_version") != "far-jury-annotation-v1"
            or row.get("juror_id") != juror_id
            or row.get("model_family") != family
            or row.get("publication_gold") is not False
        ):
            raise ValueError(f"{directory}: jury row identity or provenance mismatch")
        rows[sample_id] = row
    if (
        len(rows) != manifest.get("samples")
        or len(rows) != manifest.get("expected_samples")
    ):
        raise ValueError(f"{directory}: jury annotation rows are incomplete")
    fallbacks = sum(_is_fallback(row) for row in rows.values())
    if fallbacks != manifest.get("fallbacks"):
        raise ValueError(f"{directory}: jury fallback count mismatch")
    return manifest, rows


def _label(row: dict[str, Any]) -> str:
    annotation = row["jury_annotation"]
    return str(annotation["conflict_type"]) if annotation["conflict_present"] else "no_conflict"


def _joint(row: dict[str, Any]) -> tuple[bool, str, str, bool]:
    annotation = row["jury_annotation"]
    return (
        bool(annotation["conflict_present"]),
        _label(row),
        str(annotation["revision_action"]),
        bool(annotation["revised_answer_acceptable"]),
    )


def _binary_label(row: dict[str, Any]) -> str:
    return "conflict" if bool(row["jury_annotation"]["conflict_present"]) else "no_conflict"


def _binary_joint(row: dict[str, Any]) -> tuple[bool, str, bool]:
    annotation = row["jury_annotation"]
    return (
        bool(annotation["conflict_present"]),
        str(annotation["revision_action"]),
        bool(annotation["revised_answer_acceptable"]),
    )


def build_jury_consensus(
    data_dir: Path,
    juror_dirs: list[Path],
    output_dir: Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    verify_active_protocol()
    if len(juror_dirs) != 3:
        raise ValueError("jury consensus requires exactly three jurors")
    loaded = [_load_juror(directory) for directory in juror_dirs]
    manifests = [item[0] for item in loaded]
    rows_by_juror = [item[1] for item in loaded]
    juror_ids = [str(item["juror_id"]) for item in manifests]
    families = [str(item["model_family"]).lower() for item in manifests]
    if len(set(juror_ids)) != 3 or len(set(families)) != 3:
        raise ValueError("jury IDs and model families must be pairwise distinct")
    if set(families) & SYSTEM_MODEL_FAMILIES:
        raise ValueError("jury family overlaps a system model family")
    if any(item.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256 for item in manifests):
        raise ValueError("jury source uses a stale protocol fingerprint")
    if any(item.get("prompt_sha256") != PROMPT_SHA256 for item in manifests):
        raise ValueError("jury source uses a different prompt")
    source_packets = {str(item.get("source_packet_sha256")) for item in manifests}
    if len(source_packets) != 1:
        raise ValueError("jury sources do not share one frozen packet")
    source_adjudications = {
        str(item.get("source_adjudication_sha256", "")) for item in manifests
    }
    if len(source_adjudications) != 1 or not next(iter(source_adjudications)):
        raise ValueError("jury sources do not share one frozen blind-row file")
    sample_sets = [set(rows) for rows in rows_by_juror]
    if not sample_sets[0] or any(samples != sample_sets[0] for samples in sample_sets[1:]):
        raise ValueError("jury sources do not have identical complete samples")
    benchmark = {str(row["id"]): row for row in read_jsonl(data_dir / "falsirag_bench.jsonl")}
    if set(benchmark) != sample_sets[0]:
        raise ValueError("jury samples do not cover the complete benchmark")

    ordered_ids = sorted(benchmark)
    labels_by_juror = {
        juror_id: [_label(rows[sample_id]) for sample_id in ordered_ids]
        for juror_id, rows in zip(juror_ids, rows_by_juror, strict=True)
    }
    pairwise: dict[str, float] = {}
    pairwise_binary: dict[str, float] = {}
    for left, right in combinations(juror_ids, 2):
        key = f"{left}__{right}"
        pairwise[key] = cohen_kappa(labels_by_juror[left], labels_by_juror[right])
        pairwise_binary[key] = cohen_kappa(
            [
                "conflict" if label != "no_conflict" else "no_conflict"
                for label in labels_by_juror[left]
            ],
            [
                "conflict" if label != "no_conflict" else "no_conflict"
                for label in labels_by_juror[right]
            ],
        )
    ratings = [
        [labels_by_juror[juror_id][index] for juror_id in juror_ids]
        for index in range(len(ordered_ids))
    ]
    binary_ratings = [
        ["conflict" if label != "no_conflict" else "no_conflict" for label in row]
        for row in ratings
    ]
    type_fleiss = fleiss_kappa(ratings)
    binary_fleiss = fleiss_kappa(binary_ratings)
    zero_fallbacks = sum(int(item.get("fallbacks", 0)) for item in manifests) == 0
    primary_gate = min(pairwise.values()) >= 0.50 and type_fleiss >= 0.45 and zero_fallbacks
    binary_gate = min(pairwise_binary.values()) >= 0.50 and binary_fleiss >= 0.45 and zero_fallbacks
    active_granularity = "six_class" if primary_gate else "binary" if binary_gate else None

    consensus_rows: list[dict[str, Any]] = []
    disposition_counts: Counter[str] = Counter()
    for index, sample_id in enumerate(ordered_ids):
        typed_labels = ratings[index]
        binary_labels = binary_ratings[index]
        labels = binary_labels if active_granularity == "binary" else typed_labels
        counts = Counter(labels)
        label, votes = counts.most_common(1)[0]
        has_majority = votes >= 2
        juror_rows = [rows[sample_id] for rows in rows_by_juror]
        joint_function = _binary_joint if active_granularity == "binary" else _joint
        joint_counts = Counter(joint_function(row) for row in juror_rows)
        majority_joint, joint_count = joint_counts.most_common(1)[0]
        has_joint_majority = joint_count >= 2
        construction_type = str(benchmark[sample_id]["conflict_type"])
        construction = (
            "conflict"
            if active_granularity == "binary" and construction_type != "no_conflict"
            else "no_conflict"
            if active_granularity == "binary"
            else construction_type
        )
        selected_juror: str | None = None
        if has_joint_majority:
            candidates = [
                (float(row["jury_annotation"].get("confidence", 0.0)), juror_id)
                for juror_id, row in zip(juror_ids, juror_rows, strict=True)
                if joint_function(row) == majority_joint
            ]
            selected_juror = max(candidates, key=lambda item: (item[0], item[1]))[1]
        if len(joint_counts) == 1 and label == construction:
            disposition = "unanimous"
        elif has_joint_majority and label == construction:
            disposition = "majority"
        else:
            disposition = "disputed"
        disposition_counts[disposition] += 1
        consensus_rows.append(
            {
                "sample_id": sample_id,
                "category": str(benchmark[sample_id]["category"]),
                "active_label_granularity": active_granularity,
                "juror_votes": {
                    juror_id: (
                        "conflict"
                        if active_granularity == "binary"
                        and labels_by_juror[juror_id][index] != "no_conflict"
                        else labels_by_juror[juror_id][index]
                    )
                    for juror_id in juror_ids
                },
                "typed_juror_votes": {
                    juror_id: labels_by_juror[juror_id][index] for juror_id in juror_ids
                },
                "majority_label": label if has_majority else None,
                "majority_votes": votes if has_majority else 0,
                "joint_majority": list(majority_joint) if has_joint_majority else None,
                "joint_majority_fields": (
                    ["conflict_present", "revision_action", "revised_answer_acceptable"]
                    if active_granularity == "binary"
                    else [
                        "conflict_present",
                        "conflict_type",
                        "revision_action",
                        "revised_answer_acceptable",
                    ]
                ),
                "joint_majority_votes": joint_count if has_joint_majority else 0,
                "selected_juror_id": selected_juror if disposition != "disputed" else None,
                "construction_label": construction,
                "construction_type_label": construction_type,
                "disposition": disposition,
                "requires_author_adjudication": disposition == "disputed",
            }
        )

    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass --overwrite")
        marker = output_dir / "jury_consensus_report.json"
        if not marker.is_file():
            raise ValueError("refusing to overwrite a directory without a jury report")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = output_dir / "jury_consensus_rows.jsonl"
    write_jsonl(rows_path, consensus_rows)
    report = {
        "schema_version": "far-jury-consensus-v1",
        "study_profile": "cross_family_llm_jury",
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "source_packet_sha256": next(iter(source_packets)),
        "source_adjudication_sha256": next(iter(source_adjudications)),
        "jurors": [
            {
                "juror_id": juror_id,
                "model_family": family,
                "model": manifest.get("model"),
                "config_sha256": manifest.get("config_sha256"),
                "annotation_sha256": manifest.get("annotation_sha256"),
                "fallbacks": manifest.get("fallbacks"),
            }
            for juror_id, family, manifest in zip(juror_ids, families, manifests, strict=True)
        ],
        "samples": len(ordered_ids),
        "label_space": [*JURY_TYPES, "no_conflict"],
        "pairwise_cohen_kappa": pairwise,
        "fleiss_kappa": type_fleiss,
        "binary_pairwise_cohen_kappa": pairwise_binary,
        "binary_fleiss_kappa": binary_fleiss,
        "zero_fallbacks": zero_fallbacks,
        "gate_k_primary_passed": primary_gate,
        "gate_k_binary_fallback_passed": binary_gate,
        "gate_k_passed": primary_gate or binary_gate,
        "active_label_granularity": active_granularity,
        "dispositions": dict(sorted(disposition_counts.items())),
        "jury_consensus_rows": rows_path.name,
        "jury_consensus_rows_sha256": sha256_file(rows_path),
        "publication_gold": False,
        "human_iaa": False,
    }
    write_json(output_dir / "jury_consensus_report.json", report)
    return report


def verify_jury_consensus(
    data_dir: Path,
    juror_dirs: list[Path],
    output_dir: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        tracked_report = json.loads(
            (output_dir / "jury_consensus_report.json").read_text(encoding="utf-8")
        )
        tracked_rows = output_dir / str(tracked_report["jury_consensus_rows"])
        if sha256_file(tracked_rows) != tracked_report.get("jury_consensus_rows_sha256"):
            errors.append("tracked jury consensus rows fingerprint mismatch")
        with tempfile.TemporaryDirectory(prefix="far-jury-verify-") as temporary:
            rebuilt_dir = Path(temporary) / "consensus"
            rebuilt = build_jury_consensus(data_dir, juror_dirs, rebuilt_dir)
            rebuilt_rows = rebuilt_dir / str(rebuilt["jury_consensus_rows"])
            if rebuilt != tracked_report:
                errors.append("jury consensus report differs from recomputation")
            if rebuilt_rows.read_bytes() != tracked_rows.read_bytes():
                errors.append("jury consensus rows differ from recomputation")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "far-jury-consensus-audit-v1",
        "valid": not errors,
        "errors": errors,
        "gate_k_passed": (
            tracked_report.get("gate_k_passed") if "tracked_report" in locals() else False
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--juror-dir", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = (
        verify_jury_consensus(args.data_dir, args.juror_dir, args.output_dir)
        if args.verify
        else build_jury_consensus(
            args.data_dir, args.juror_dir, args.output_dir, overwrite=args.overwrite
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.verify and not result["valid"]:
        raise SystemExit(1)
    if not args.verify and not result["gate_k_passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
