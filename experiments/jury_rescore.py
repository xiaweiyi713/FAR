"""Re-score frozen method predictions against compiled jury-gold labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from eval.run_eval import evaluate
from experiments.model_matrix import _fallback_rate
from experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256, verify_active_protocol


def _overlay_benchmark(data_dir: Path, labels_dir: Path, output_path: Path) -> list[dict[str, Any]]:
    labels_manifest = json.loads((labels_dir / "manifest.json").read_text(encoding="utf-8"))
    labels_path = labels_dir / str(labels_manifest["labels_file"])
    if sha256_file(labels_path) != labels_manifest.get("labels_sha256"):
        raise ValueError("jury label fingerprint mismatch")
    labels = {str(row["sample_id"]): row for row in read_jsonl(labels_path)}
    benchmark = {str(row["id"]): row for row in read_jsonl(data_dir / "falsirag_bench.jsonl")}
    if set(labels) - set(benchmark):
        raise ValueError("jury labels contain unknown benchmark samples")
    overlay: list[dict[str, Any]] = []
    for sample_id in sorted(labels):
        row = dict(benchmark[sample_id])
        annotation = labels[sample_id]["gold_annotation"]
        revised = str(
            annotation.get("revised_answer") or annotation.get("suggested_revised_answer") or ""
        ).strip()
        if not revised:
            raise ValueError(f"{sample_id}: jury gold lacks a revised-answer reference")
        row["conflict_type"] = (
            str(annotation["conflict_type"]) if annotation["conflict_present"] else "no_conflict"
        )
        row["expected_revision"] = {
            "action": str(annotation["revision_action"]),
            "revised_answer": revised,
        }
        row["annotation_status"] = "jury_gold"
        row["label_provenance"] = labels[sample_id]["label_provenance"]
        overlay.append(row)
    write_jsonl(output_path, overlay)
    return overlay


def rescore_family(
    data_dir: Path,
    labels_dir: Path,
    suite_dir: Path,
    output_dir: Path,
    *,
    family: str,
) -> dict[str, Any]:
    verify_active_protocol()
    output_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = output_dir / "jury_benchmark.jsonl"
    overlay = _overlay_benchmark(data_dir, labels_dir, overlay_path)
    dev_ids = {str(row["id"]) for row in overlay if row["split"] == "dev"}
    if not dev_ids:
        raise ValueError("jury labels leave no development samples")
    method_sources = {
        "far": suite_dir / "runs" / "far" / "predictions.jsonl",
        "minus_typed_conflict": suite_dir / "runs" / "minus_typed_conflict" / "predictions.jsonl",
    }
    report_paths: dict[str, str] = {}
    prediction_hashes: dict[str, str] = {}
    for method, source in method_sources.items():
        rows = [row for row in read_jsonl(source) if str(row["sample_id"]) in dev_ids]
        if {str(row["sample_id"]) for row in rows} != dev_ids:
            raise ValueError(f"{family}/{method}: predictions do not cover jury-labelled dev")
        predictions_path = output_dir / method / "predictions.jsonl"
        write_jsonl(predictions_path, rows)
        evaluation_dir = output_dir / method / "evaluation"
        evaluate(
            overlay_path,
            predictions_path,
            evaluation_dir,
            baseline_scores_path=(
                output_dir / "far" / "evaluation" / "scores.jsonl"
                if method == "minus_typed_conflict"
                else None
            ),
        )
        report_paths[method] = sha256_file(evaluation_dir / "report.json")
        prediction_hashes[method] = sha256_file(source)
    identity = json.loads(
        (suite_dir / "runs" / "far" / "run_identity.json").read_text(encoding="utf-8")
    )
    manifest = {
        "schema_version": "far-jury-family-rescore-v1",
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "family": family,
        "model_identity": identity.get("llm_runtime"),
        "samples": len(dev_ids),
        "jury_benchmark_sha256": sha256_file(overlay_path),
        "jury_labels_manifest_sha256": sha256_file(labels_dir / "manifest.json"),
        "source_suite_manifest_sha256": sha256_file(suite_dir / "suite_manifest.json"),
        "source_prediction_sha256": prediction_hashes,
        "reports": report_paths,
        "structured_fallback": _fallback_rate(method_sources["far"]),
        "publication_gold": False,
        "jury_gold": True,
    }
    write_json(output_dir / "matrix_family_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--labels-dir", type=Path, required=True)
    parser.add_argument("--suite-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--family", choices=("qwen", "mistral", "google"), required=True)
    args = parser.parse_args()
    result = rescore_family(
        args.data_dir,
        args.labels_dir,
        args.suite_dir,
        args.output_dir,
        family=args.family,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
