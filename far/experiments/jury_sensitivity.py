"""Compare construction, jury-gold, and unanimous-only development scores."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from far.bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.bench.build.jury_adjudication import _consensus
from far.experiments.jury_rescore import rescore_family
from far.experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256, verify_active_protocol

SIX_CLASS_METRICS = ("answer_correctness", "typed_conflict_f1", "revision_accuracy")
BINARY_METRICS = ("answer_correctness", "conflict_presence_f1", "revision_accuracy")


def _presence_f1(scores_path: Path) -> float:
    rows = read_jsonl(scores_path)
    true_positives = sum(
        bool(row.get("predicted_conflict_count"))
        for row in rows
        if bool(row.get("gold_conflict_present"))
    )
    predicted = sum(bool(row.get("predicted_conflict_count")) for row in rows)
    gold = sum(bool(row.get("gold_conflict_present")) for row in rows)
    precision = true_positives / predicted if predicted else 0.0
    recall = true_positives / gold if gold else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _report_metrics(path: Path, metric_names: tuple[str, ...]) -> dict[str, float]:
    report = json.loads(path.read_text(encoding="utf-8"))
    values = report["aggregate"]["metrics"]
    result: dict[str, float] = {}
    for name in metric_names:
        if name == "conflict_presence_f1" and values.get(name) is None:
            result[name] = _presence_f1(path.with_name("scores.jsonl"))
        else:
            result[name] = float(values[name])
    return result


def _construction_report(suite_dir: Path, method: str) -> Path:
    label = "vanilla_rag" if method == "vanilla" else method
    return suite_dir / "evaluations" / label / "report.json"


def build_sensitivity(
    data_dir: Path,
    labels_dir: Path,
    consensus_dir: Path,
    suite_dir: Path,
    output_dir: Path,
    *,
    family: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    verify_active_protocol()
    if family != "qwen":
        raise ValueError("the preregistered three-view sensitivity analysis is Qwen-only")
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass --overwrite")
        marker = output_dir / "sensitivity_report.json"
        if not marker.is_file():
            raise ValueError("refusing to overwrite a directory without a sensitivity report")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    labels_manifest = json.loads((labels_dir / "manifest.json").read_text(encoding="utf-8"))
    label_granularity = str(labels_manifest.get("label_granularity", "six_class"))
    if label_granularity not in {"six_class", "binary"}:
        raise ValueError("jury labels use an unsupported label granularity")
    metric_names = BINARY_METRICS if label_granularity == "binary" else SIX_CLASS_METRICS
    labels_path = labels_dir / str(labels_manifest["labels_file"])
    if sha256_file(labels_path) != labels_manifest.get("labels_sha256"):
        raise ValueError("jury label fingerprint mismatch")
    labels = read_jsonl(labels_path)
    consensus_report, consensus_rows = _consensus(consensus_dir)
    if consensus_report.get("gate_k_passed") is not True or labels_manifest.get(
        "consensus_report_sha256"
    ) != sha256_file(consensus_dir / "jury_consensus_report.json"):
        raise ValueError("jury labels do not bind the passing consensus report")
    if consensus_report.get("active_label_granularity") != label_granularity:
        raise ValueError("jury labels and consensus disagree on label granularity")
    consensus_path = consensus_dir / str(consensus_report["jury_consensus_rows"])
    if sha256_file(consensus_path) != consensus_report.get("jury_consensus_rows_sha256"):
        raise ValueError("jury consensus rows fingerprint mismatch")
    unanimous_ids = {
        sample_id for sample_id, row in consensus_rows.items() if row["disposition"] == "unanimous"
    }
    unanimous_rows = [row for row in labels if str(row["sample_id"]) in unanimous_ids]
    if not unanimous_rows:
        raise ValueError("jury sensitivity has no unanimous rows")
    unanimous_labels = output_dir / "unanimous_labels"
    unanimous_labels.mkdir()
    unanimous_path = unanimous_labels / "labels.jsonl"
    write_jsonl(unanimous_path, unanimous_rows)
    unanimous_manifest = {
        **labels_manifest,
        "schema_version": "far-jury-label-view-v1",
        "label_view": "unanimous_only",
        "samples": len(unanimous_rows),
        "labels_file": unanimous_path.name,
        "labels_sha256": sha256_file(unanimous_path),
        "source_labels_manifest_sha256": sha256_file(labels_dir / "manifest.json"),
        "source_consensus_rows_sha256": sha256_file(consensus_path),
    }
    write_json(unanimous_labels / "manifest.json", unanimous_manifest)

    jury_manifest = rescore_family(
        data_dir,
        labels_dir,
        suite_dir,
        output_dir / "jury_gold",
        family=family,
        split="dev",
    )
    unanimous_rescore = rescore_family(
        data_dir,
        unanimous_labels,
        suite_dir,
        output_dir / "unanimous_only",
        family=family,
        split="dev",
    )
    suite_manifest = json.loads((suite_dir / "suite_manifest.json").read_text(encoding="utf-8"))
    for method in jury_manifest["methods"]:
        report_path = _construction_report(suite_dir, method)
        if suite_manifest.get("reports", {}).get(method) != sha256_file(report_path):
            raise ValueError(f"construction report fingerprint mismatch: {method}")
    rows: list[dict[str, Any]] = []
    for method in jury_manifest["methods"]:
        rows.append(
            {
                "method": method,
                "construction": _report_metrics(
                    _construction_report(suite_dir, method), metric_names
                ),
                "jury_gold": _report_metrics(
                    output_dir / "jury_gold" / method / "evaluation" / "report.json",
                    metric_names,
                ),
                "unanimous_only": _report_metrics(
                    output_dir / "unanimous_only" / method / "evaluation" / "report.json",
                    metric_names,
                ),
            }
        )
    report = {
        "schema_version": "far-jury-label-sensitivity-v1",
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "family": family,
        "label_granularity": label_granularity,
        "metrics": list(metric_names),
        "views": {
            "construction": "controlled_benchmark_construction",
            "jury_gold": "cross_family_llm_jury_plus_author_blind_adjudication",
            "unanimous_only": "cross_family_llm_unanimous_only",
        },
        "samples": {
            "jury_gold_dev": jury_manifest["samples"],
            "unanimous_only_dev": unanimous_rescore["samples"],
        },
        "rows": rows,
        "jury_rescore_manifest_sha256": sha256_file(
            output_dir / "jury_gold" / "matrix_family_manifest.json"
        ),
        "unanimous_rescore_manifest_sha256": sha256_file(
            output_dir / "unanimous_only" / "matrix_family_manifest.json"
        ),
        "publication_gold": False,
        "human_iaa": False,
    }
    write_json(output_dir / "sensitivity_report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--labels-dir", type=Path, required=True)
    parser.add_argument("--consensus-dir", type=Path, required=True)
    parser.add_argument("--suite-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--family", choices=("qwen", "mistral", "google"), required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    result = build_sensitivity(
        args.data_dir,
        args.labels_dir,
        args.consensus_dir,
        args.suite_dir,
        args.output_dir,
        family=args.family,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
