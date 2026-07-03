"""Build a reproducible machine-audit record for the synthetic benchmark labels.

This command does not convert machine labels into human gold.  It treats the
benchmark's construction-derived labels as the reference and records how
independent LLM preannotators and deterministic weak labelers agree, abstain, or
disagree.  The resulting profile is suitable for a transparently described
single-author, machine-audited synthetic benchmark study.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from bench.build.validate_bench import validate

REPORT_VERSION = "falsirag-machine-consensus-v1"


def _unique_rows(rows: list[dict[str, Any]], *, role: str) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        sample_id = str(row.get("sample_id", "")).strip()
        if not sample_id:
            raise ValueError(f"{role}: row without sample_id")
        if sample_id in by_id:
            raise ValueError(f"{role}: duplicate sample_id {sample_id}")
        by_id[sample_id] = row
    return by_id


def _load_preannotation(directory: Path) -> tuple[dict[str, Any], Path, dict[str, dict[str, Any]]]:
    manifest_path = directory / "preannotation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("publication_gold") is not False:
        raise ValueError(f"{directory}: preannotation source must declare publication_gold=false")
    path = directory / str(manifest["preannotation_file"])
    rows = _unique_rows(read_jsonl(path), role=f"preannotation:{directory}")
    return manifest, path, rows


def _load_weak_labels(directory: Path) -> tuple[dict[str, Any], Path, dict[str, dict[str, Any]]]:
    manifest_path = directory / "weak_annotation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("publication_gold") is not False:
        raise ValueError(f"{directory}: weak-label source must declare publication_gold=false")
    path = directory / str(manifest["weak_annotation_file"])
    rows = _unique_rows(read_jsonl(path), role=f"weak-label:{directory}")
    return manifest, path, rows


def _label(annotation: dict[str, Any]) -> tuple[str, str]:
    present = bool(annotation.get("conflict_present"))
    conflict_type = str(annotation.get("conflict_type", "")).strip()
    if not present:
        conflict_type = "no_conflict"
    return conflict_type, str(annotation.get("revision_action", "")).strip()


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def build_machine_consensus(
    data_dir: Path,
    output_dir: Path,
    *,
    preannotation_dirs: list[Path],
    weak_label_dirs: list[Path],
    minimum_weak_coverage: float = 0.5,
    maximum_llm_fallback_rate: float = 0.01,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Audit construction labels against one or more non-gold machine sources."""

    if not preannotation_dirs:
        raise ValueError("at least one complete LLM preannotation source is required")
    if not weak_label_dirs:
        raise ValueError("at least one deterministic weak-label source is required")
    if not 0.0 <= minimum_weak_coverage <= 1.0:
        raise ValueError("minimum_weak_coverage must be between 0 and 1")
    if not 0.0 <= maximum_llm_fallback_rate <= 1.0:
        raise ValueError("maximum_llm_fallback_rate must be between 0 and 1")

    validation = validate(data_dir)
    if not validation["valid"]:
        raise ValueError(f"benchmark validation failed: {validation['errors']}")
    benchmark_path = data_dir / "falsirag_bench.jsonl"
    corpus_path = data_dir / "corpus.jsonl"
    source_fingerprints = {
        "benchmark_sha256": sha256_file(benchmark_path),
        "corpus_sha256": sha256_file(corpus_path),
    }
    benchmark_rows = read_jsonl(benchmark_path)
    benchmark_by_id = {str(row["id"]): row for row in benchmark_rows}
    sample_ids = set(benchmark_by_id)

    llm_sources: list[dict[str, Any]] = []
    llm_ids: set[str] = set()
    for directory in preannotation_dirs:
        manifest, path, rows = _load_preannotation(directory)
        source_id = str(manifest.get("preannotator_id", "")).strip()
        if not source_id or source_id in llm_ids:
            raise ValueError("LLM preannotation sources require distinct non-empty IDs")
        llm_ids.add(source_id)
        if manifest.get("source_fingerprints") != source_fingerprints:
            raise ValueError(f"{source_id}: source fingerprints do not match the benchmark")
        if set(rows) != sample_ids:
            raise ValueError(f"{source_id}: preannotations do not cover the complete benchmark")
        fallback_count = sum(
            str(row.get("preannotation", {}).get("rationale", "")).startswith("Automatic fallback;")
            for row in rows.values()
        )
        llm_sources.append(
            {
                "source_id": source_id,
                "kind": "llm_preannotation",
                "path": path,
                "sha256": sha256_file(path),
                "rows": rows,
                "fallback_count": fallback_count,
            }
        )

    weak_sources: list[dict[str, Any]] = []
    weak_ids: set[str] = set()
    for directory in weak_label_dirs:
        manifest, path, rows = _load_weak_labels(directory)
        source_id = str(manifest.get("weak_annotator_id", "")).strip()
        if not source_id or source_id in weak_ids or source_id in llm_ids:
            raise ValueError("machine label sources require distinct non-empty IDs")
        weak_ids.add(source_id)
        if manifest.get("source_fingerprints") != source_fingerprints:
            raise ValueError(f"{source_id}: source fingerprints do not match the benchmark")
        if set(rows) != sample_ids:
            raise ValueError(f"{source_id}: weak labels do not cover the complete benchmark")
        weak_sources.append(
            {
                "source_id": source_id,
                "kind": "deterministic_weak_label",
                "path": path,
                "sha256": sha256_file(path),
                "rows": rows,
            }
        )

    source_stats: dict[str, dict[str, Any]] = {}
    per_category: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    audit_rows: list[dict[str, Any]] = []
    disposition_counts: Counter[str] = Counter()
    weak_non_abstained_total = 0

    for sample_id in sorted(sample_ids):
        sample = benchmark_by_id[sample_id]
        reference = (
            str(sample["conflict_type"]),
            str(sample["expected_revision"]["action"]),
        )
        signals: list[dict[str, Any]] = []
        exact_matches = 0
        non_abstained = 0
        for source in llm_sources:
            annotation = source["rows"][sample_id]["preannotation"]
            observed = _label(annotation)
            fallback = str(annotation.get("rationale", "")).startswith("Automatic fallback;")
            exact = observed == reference and not fallback
            non_abstained += not fallback
            exact_matches += exact
            signals.append(
                {
                    "source_id": source["source_id"],
                    "kind": source["kind"],
                    "conflict_type": observed[0],
                    "revision_action": observed[1],
                    "abstained": fallback,
                    "exact_joint_match": exact,
                }
            )
        for source in weak_sources:
            annotation = source["rows"][sample_id]["weak_annotation"]
            abstained = bool(annotation.get("abstained", False))
            observed = _label(annotation)
            exact = observed == reference and not abstained
            non_abstained += not abstained
            exact_matches += exact
            weak_non_abstained_total += not abstained
            signals.append(
                {
                    "source_id": source["source_id"],
                    "kind": source["kind"],
                    "conflict_type": observed[0],
                    "revision_action": observed[1],
                    "abstained": abstained,
                    "exact_joint_match": exact,
                }
            )

        if exact_matches:
            disposition = "machine_confirmed"
        elif non_abstained:
            disposition = "machine_disputed"
        else:
            disposition = "machine_unaudited"
        disposition_counts[disposition] += 1
        audit_rows.append(
            {
                "sample_id": sample_id,
                "category": sample["category"],
                "reference_origin": "controlled_benchmark_construction",
                "reference": {
                    "conflict_type": reference[0],
                    "revision_action": reference[1],
                    "revised_answer_sha256": hashlib.sha256(
                        str(sample["expected_revision"]["revised_answer"]).encode("utf-8")
                    ).hexdigest(),
                },
                "machine_signals": signals,
                "non_abstained_signals": non_abstained,
                "exact_joint_matches": exact_matches,
                "disposition": disposition,
                "requires_claim_limitation": disposition != "machine_confirmed",
            }
        )
        for signal in signals:
            stats = per_category[str(sample["category"])][str(signal["source_id"])]
            stats["samples"] += 1
            stats["abstained"] += bool(signal["abstained"])
            stats["joint_matches"] += bool(signal["exact_joint_match"])

    for source in (*llm_sources, *weak_sources):
        source_id = str(source["source_id"])
        samples = len(sample_ids)
        source_abstentions = sum(
            int(per_category[category][source_id]["abstained"]) for category in per_category
        )
        matches = sum(
            int(per_category[category][source_id]["joint_matches"]) for category in per_category
        )
        source_stats[source_id] = {
            "kind": source["kind"],
            "file_sha256": source["sha256"],
            "samples": samples,
            "non_abstained": samples - source_abstentions,
            "coverage": _rate(samples - source_abstentions, samples),
            "exact_joint_matches": matches,
            "exact_joint_agreement_on_non_abstained": _rate(matches, samples - source_abstentions),
            "fallback_count": source.get("fallback_count", 0),
            "by_category": {
                category: {
                    "samples": int(values[source_id]["samples"]),
                    "non_abstained": int(
                        values[source_id]["samples"] - values[source_id]["abstained"]
                    ),
                    "exact_joint_matches": int(values[source_id]["joint_matches"]),
                    "exact_joint_agreement_on_non_abstained": _rate(
                        int(values[source_id]["joint_matches"]),
                        int(values[source_id]["samples"] - values[source_id]["abstained"]),
                    ),
                }
                for category, values in sorted(per_category.items())
            },
        }

    weak_denominator = len(sample_ids) * len(weak_sources)
    weak_coverage = _rate(weak_non_abstained_total, weak_denominator) or 0.0
    llm_fallbacks = sum(int(source["fallback_count"]) for source in llm_sources)
    llm_denominator = len(sample_ids) * len(llm_sources)
    llm_fallback_rate = _rate(llm_fallbacks, llm_denominator) or 0.0
    checks = {
        "benchmark_structurally_valid": validation["valid"],
        "complete_llm_coverage": all(
            stats["samples"] == len(sample_ids)
            for source_id, stats in source_stats.items()
            if source_id in llm_ids
        ),
        "deterministic_weak_coverage": weak_coverage >= minimum_weak_coverage,
        "llm_fallback_rate": llm_fallback_rate <= maximum_llm_fallback_rate,
        "source_ids_distinct": len(source_stats) == len(llm_sources) + len(weak_sources),
        "source_fingerprints_match": True,
    }
    ready = all(checks.values())

    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass --overwrite to replace it")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    rows_path = output_dir / "machine_consensus_rows.jsonl"
    write_jsonl(rows_path, audit_rows)
    report = {
        "schema_version": REPORT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "study_profile": "single_author_machine_audited_synthetic_benchmark",
        "samples": len(sample_ids),
        "source_fingerprints": source_fingerprints,
        "sources": source_stats,
        "dispositions": dict(sorted(disposition_counts.items())),
        "thresholds": {
            "minimum_weak_coverage": minimum_weak_coverage,
            "maximum_llm_fallback_rate": maximum_llm_fallback_rate,
        },
        "observed": {
            "weak_coverage": weak_coverage,
            "llm_fallback_rate": llm_fallback_rate,
        },
        "checks": checks,
        "ready_for_solo_machine_audited_study": ready,
        "machine_consensus_rows": rows_path.name,
        "machine_consensus_rows_sha256": sha256_file(rows_path),
        "publication_gold": False,
        "human_annotation_replaced": False,
        "can_report_human_iaa": False,
        "allowed_claim": (
            "Construction-derived labels were audited by independent machine signals; "
            "machine agreement is reported as quality evidence, not human IAA."
        ),
        "forbidden_claims": [
            "independent human annotation",
            "human adjudication",
            "Cohen's kappa between human annotators",
            "human-validated gold",
        ],
    }
    write_json(output_dir / "machine_consensus_report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("bench"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--preannotation-dir",
        action="append",
        type=Path,
        default=[],
        dest="preannotation_dirs",
    )
    parser.add_argument(
        "--weak-label-dir",
        action="append",
        type=Path,
        default=[],
        dest="weak_label_dirs",
    )
    parser.add_argument("--minimum-weak-coverage", type=float, default=0.5)
    parser.add_argument("--maximum-llm-fallback-rate", type=float, default=0.01)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    result = build_machine_consensus(
        args.data_dir,
        args.output_dir,
        preannotation_dirs=args.preannotation_dirs,
        weak_label_dirs=args.weak_label_dirs,
        minimum_weak_coverage=args.minimum_weak_coverage,
        maximum_llm_fallback_rate=args.maximum_llm_fallback_rate,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not result["ready_for_solo_machine_audited_study"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
