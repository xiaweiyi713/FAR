"""Re-score frozen method predictions against compiled jury-gold labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from far.bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.eval.run_eval import evaluate
from far.experiments.model_matrix import _fallback_rate
from far.experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256, verify_active_protocol

QWEN_METHODS = {
    "counterrefine_style_reproduction",
    "crag_style_reproduction",
    "far",
    "minus_boundary_query",
    "minus_refutation_query",
    "minus_typed_conflict",
    "minus_typed_revision",
    "multi_query_rag",
    "reflective_rag",
    "self_rag_style_reproduction",
    "vanilla",
}
MATRIX_METHODS = {
    "counterrefine_style_reproduction",
    "crag_style_reproduction",
    "far",
    "minus_typed_conflict",
}


def _prediction_source(suite_dir: Path, method: str) -> Path:
    source_method = "vanilla_rag" if method == "vanilla" else method
    if method in {
        "vanilla",
        "vanilla_rag",
        "multi_query_rag",
        "reflective_rag",
        "crag_style_reproduction",
        "self_rag_style_reproduction",
        "counterrefine_style_reproduction",
    }:
        return suite_dir / "runs" / "baselines" / source_method / "predictions.jsonl"
    return suite_dir / "runs" / source_method / "predictions.jsonl"


def _overlay_benchmark(data_dir: Path, labels_dir: Path, output_path: Path) -> list[dict[str, Any]]:
    labels_manifest = json.loads((labels_dir / "manifest.json").read_text(encoding="utf-8"))
    schema = str(labels_manifest.get("schema_version", ""))
    if schema not in {"far-jury-labels-v1", "far-jury-label-view-v1"}:
        raise ValueError("unsupported jury label manifest schema")
    if (
        labels_manifest.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256
        or labels_manifest.get("jury_gold") is not True
        or labels_manifest.get("publication_gold") is not False
        or labels_manifest.get("human_iaa") is not False
        or labels_manifest.get("gate_k_passed") is not True
        or labels_manifest.get("gate_s_passed") is not True
    ):
        raise ValueError("jury label provenance or gate state is invalid")
    phase_b_gate = labels_manifest.get("phase_b_gate")
    if (
        not isinstance(phase_b_gate, dict)
        or phase_b_gate.get("gate_a_passed") is not True
        or phase_b_gate.get("phase_b_authorized") is not True
        or phase_b_gate.get("samples") != 350
    ):
        raise ValueError("jury labels are not bound to a verified G-A authorization")
    if schema == "far-jury-labels-v1" and labels_manifest.get("excluded_disputed_samples") != []:
        raise ValueError("full jury gold must not exclude disputed samples")
    if schema == "far-jury-label-view-v1" and labels_manifest.get("label_view") != "unanimous_only":
        raise ValueError("jury label view must be the unanimous-only sensitivity view")
    labels_path = labels_dir / str(labels_manifest["labels_file"])
    if sha256_file(labels_path) != labels_manifest.get("labels_sha256"):
        raise ValueError("jury label fingerprint mismatch")
    label_rows = read_jsonl(labels_path)
    labels = {str(row["sample_id"]): row for row in label_rows}
    if len(labels) != len(label_rows) or len(labels) != labels_manifest.get("samples"):
        raise ValueError("jury labels are duplicate or incomplete")
    if any(
        row.get("jury_gold") is not True
        or row.get("publication_gold") is not False
        or not isinstance(row.get("gold_annotation"), dict)
        for row in label_rows
    ):
        raise ValueError("jury label row provenance is invalid")
    label_granularity = str(labels_manifest.get("label_granularity", "six_class"))
    if label_granularity not in {"six_class", "binary"}:
        raise ValueError("jury labels use an unsupported label granularity")
    benchmark = {str(row["id"]): row for row in read_jsonl(data_dir / "falsirag_bench.jsonl")}
    if set(labels) - set(benchmark):
        raise ValueError("jury labels contain unknown benchmark samples")
    if schema == "far-jury-labels-v1" and set(labels) != set(benchmark):
        raise ValueError("full jury gold does not cover the complete benchmark")
    overlay: list[dict[str, Any]] = []
    for sample_id in sorted(labels):
        row = dict(benchmark[sample_id])
        annotation = labels[sample_id]["gold_annotation"]
        revised = str(
            annotation.get("revised_answer") or annotation.get("suggested_revised_answer") or ""
        ).strip()
        if not annotation.get("conflict_present"):
            revised = str(row["initial_answer"])
        elif not revised:
            raise ValueError(f"{sample_id}: jury gold lacks a revised-answer reference")
        row["conflict_type"] = (
            str(annotation["conflict_type"]) if annotation["conflict_present"] else "no_conflict"
        )
        row["expected_revision"] = {
            "action": str(annotation["revision_action"]),
            "revised_answer": revised,
        }
        row["annotation_status"] = "jury_gold"
        row["jury_label_granularity"] = label_granularity
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
    split: str = "dev",
) -> dict[str, Any]:
    verify_active_protocol()
    output_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = output_dir / "jury_benchmark.jsonl"
    overlay = _overlay_benchmark(data_dir, labels_dir, overlay_path)
    selected_ids = {str(row["id"]) for row in overlay if row["split"] == split}
    if not selected_ids:
        raise ValueError(f"jury labels leave no {split} samples")
    suite = json.loads((suite_dir / "suite_manifest.json").read_text(encoding="utf-8"))
    if (
        suite.get("schema_version") != "far-suite-manifest-v1"
        or suite.get("split") != split
        or suite.get("benchmark_sha256") != sha256_file(data_dir / "falsirag_bench.jsonl")
    ):
        raise ValueError("source suite identity does not match the requested benchmark split")
    method_set = {str(method) for method in suite.get("methods", [])}
    expected_methods = QWEN_METHODS if family == "qwen" else MATRIX_METHODS
    if method_set != expected_methods:
        raise ValueError(f"{family}: source suite does not contain the preregistered method set")
    selected_methods = ["far", *sorted(method_set - {"far"})]

    method_sources = {method: _prediction_source(suite_dir, method) for method in selected_methods}
    report_paths: dict[str, str] = {}
    prediction_hashes: dict[str, str] = {}
    rescored_prediction_hashes: dict[str, str] = {}
    for method, source in method_sources.items():
        source_rows = read_jsonl(source)
        source_ids = [str(row["sample_id"]) for row in source_rows]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError(f"{family}/{method}: frozen predictions contain duplicate samples")
        rows = [row for row in source_rows if str(row["sample_id"]) in selected_ids]
        row_ids = [str(row["sample_id"]) for row in rows]
        if len(row_ids) != len(set(row_ids)) or set(row_ids) != selected_ids:
            raise ValueError(f"{family}/{method}: predictions do not cover jury-labelled {split}")
        run_key = "vanilla_rag" if method == "vanilla" else method
        run_manifest = suite.get("run_manifests", {}).get(run_key, {})
        if (
            run_manifest.get("partial") is not False
            or run_manifest.get("completed") != len(source_rows)
            or run_manifest.get("predictions_sha256") != sha256_file(source)
        ):
            raise ValueError(f"{family}/{method}: frozen prediction fingerprint mismatch")
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
        rescored_prediction_hashes[method] = sha256_file(predictions_path)
    identity = json.loads(
        (suite_dir / "runs" / "far" / "run_identity.json").read_text(encoding="utf-8")
    )
    model_identity = identity.get("llm_runtime")
    model_name = str((model_identity or {}).get("model", "")).lower()
    family_marker = {"qwen": "qwen", "mistral": "mistral", "google": "gemma"}[family]
    if family_marker not in model_name:
        raise ValueError(f"{family}: FAR runtime model does not match the declared family")
    manifest = {
        "schema_version": "far-jury-family-rescore-v1",
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "family": family,
        "model_identity": model_identity,
        "split": split,
        "samples": len(selected_ids),
        "methods": selected_methods,
        "jury_benchmark_sha256": sha256_file(overlay_path),
        "jury_labels_manifest_sha256": sha256_file(labels_dir / "manifest.json"),
        "source_suite_manifest_sha256": sha256_file(suite_dir / "suite_manifest.json"),
        "source_prediction_sha256": prediction_hashes,
        "rescored_prediction_sha256": rescored_prediction_hashes,
        "reports": report_paths,
        "structured_fallback": _fallback_rate(method_sources["far"]),
        "publication_gold": False,
        "human_iaa": False,
        "jury_gold": True,
        "label_granularity": json.loads(
            (labels_dir / "manifest.json").read_text(encoding="utf-8")
        ).get("label_granularity", "six_class"),
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
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    args = parser.parse_args()
    result = rescore_family(
        args.data_dir,
        args.labels_dir,
        args.suite_dir,
        args.output_dir,
        family=args.family,
        split=args.split,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
