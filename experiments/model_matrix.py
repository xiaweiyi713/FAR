"""Build the preregistered cross-family typed-versus-untyped result matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json
from experiments.protocol_2plus4 import (
    PROTOCOL_ACTIVE_SHA256,
    verify_active_protocol,
)


def _fallback_rate(predictions_path: Path) -> dict[str, Any]:
    rows = read_jsonl(predictions_path)
    sample_ids = [str(row.get("sample_id", "")) for row in rows]
    if not rows or any(not sample_id for sample_id in sample_ids):
        raise ValueError("fallback audit requires non-empty predictions with sample IDs")
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("fallback audit predictions contain duplicate sample IDs")
    fallback_ids: list[str] = []
    for row in rows:
        metadata = row.get("metadata", {})
        queries = metadata.get("retrieval_trace", [])
        revisions = metadata.get("revision_trace", [])
        query_fallback = any(
            not str(item.get("query", {}).get("tactic", "")).startswith("llm:") for item in queries
        )
        revision_fallback = any(
            item.get("changed") is True
            and "typed policy realized by the configured LLM" not in str(item.get("rationale", ""))
            for item in revisions
        )
        if query_fallback or revision_fallback:
            fallback_ids.append(str(row["sample_id"]))
    return {
        "samples": len(rows),
        "fallback_samples": len(fallback_ids),
        "fallback_rate": len(fallback_ids) / len(rows) if rows else 1.0,
        "fallback_sample_ids": fallback_ids,
    }


def _suite_row(family: str, suite_dir: Path) -> dict[str, Any]:
    suite = json.loads((suite_dir / "matrix_family_manifest.json").read_text(encoding="utf-8"))
    if (
        suite.get("schema_version") != "far-jury-family-rescore-v1"
        or suite.get("jury_gold") is not True
        or suite.get("publication_gold") is not False
        or suite.get("human_iaa") is not False
    ):
        raise ValueError(f"{family}: matrix input is not a jury-gold rescore bundle")
    if suite.get("split") != "dev":
        raise ValueError(f"{family}: model matrix requires development rescoring")
    if suite.get("family") != family or suite.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256:
        raise ValueError(f"{family}: matrix input identity mismatch")
    untyped_report = json.loads(
        (suite_dir / "minus_typed_conflict" / "evaluation" / "report.json").read_text(
            encoding="utf-8"
        )
    )
    untyped_report_path = suite_dir / "minus_typed_conflict" / "evaluation" / "report.json"
    if suite.get("reports", {}).get("minus_typed_conflict") != sha256_file(untyped_report_path):
        raise ValueError(f"{family}: untyped rescore report fingerprint mismatch")
    comparison = untyped_report.get("comparison")
    if not isinstance(comparison, dict):
        raise ValueError(f"{family}: untyped report has no paired FAR comparison")
    metrics = comparison.get("metrics", {})
    answer = metrics["answer_correctness"]
    label_granularity = str(suite.get("label_granularity", "six_class"))
    if label_granularity not in {"six_class", "binary"}:
        raise ValueError(f"{family}: unsupported jury label granularity")
    conflict_metric = (
        "conflict_presence_f1" if label_granularity == "binary" else "typed_conflict_f1"
    )
    conflict = metrics[conflict_metric]
    far_predictions = suite_dir / "far" / "predictions.jsonl"
    if suite.get("rescored_prediction_sha256", {}).get("far") != sha256_file(far_predictions):
        raise ValueError(f"{family}: rescored FAR prediction fingerprint mismatch")
    fallback = _fallback_rate(far_predictions)
    if fallback != suite.get("structured_fallback"):
        raise ValueError(f"{family}: structured fallback audit mismatch")
    return {
        "family": family,
        "model": suite.get("model_identity", {}).get("model"),
        "model_identity": suite.get("model_identity"),
        "label_granularity": label_granularity,
        "conflict_metric": conflict_metric,
        "suite_manifest_sha256": sha256_file(suite_dir / "matrix_family_manifest.json"),
        "typed_minus_untyped_answer_correctness": -float(answer["candidate_minus_baseline"]),
        "typed_minus_untyped_answer_ci": [-float(answer["upper"]), -float(answer["lower"])],
        "typed_minus_untyped_conflict_score": -float(conflict["candidate_minus_baseline"]),
        "typed_minus_untyped_conflict_score_ci": [
            -float(conflict["upper"]),
            -float(conflict["lower"]),
        ],
        "typed_minus_untyped_conflict_f1": (
            -float(conflict["candidate_minus_baseline"])
            if label_granularity == "six_class"
            else None
        ),
        "typed_minus_untyped_conflict_f1_ci": (
            [-float(conflict["upper"]), -float(conflict["lower"])]
            if label_granularity == "six_class"
            else None
        ),
        "structured_fallback": fallback,
        "excluded": float(fallback["fallback_rate"]) > 0.30,
        "exclusion_threshold": 0.30,
    }


def build_matrix(suites: dict[str, Path], output_path: Path) -> dict[str, Any]:
    verify_active_protocol()
    if set(suites) != {"qwen", "mistral", "google"}:
        raise ValueError("matrix requires exactly the three preregistered system families")
    rows = [_suite_row(family, directory) for family, directory in sorted(suites.items())]
    source_label_hashes = {
        json.loads((directory / "matrix_family_manifest.json").read_text(encoding="utf-8")).get(
            "jury_labels_manifest_sha256"
        )
        for directory in suites.values()
    }
    if len(source_label_hashes) != 1 or not next(iter(source_label_hashes)):
        raise ValueError("model families were not rescored against one frozen jury label set")
    granularities = {str(row["label_granularity"]) for row in rows}
    if len(granularities) != 1:
        raise ValueError("model matrix mixes incompatible jury label granularities")
    label_granularity = next(iter(granularities)) if granularities else None
    included = [row for row in rows if not row["excluded"]]
    result = {
        "schema_version": "far-model-matrix-v1",
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "rows": rows,
        "jury_labels_manifest_sha256": next(iter(source_label_hashes)),
        "label_granularity": label_granularity,
        "conflict_metric": (
            "conflict_presence_f1" if label_granularity == "binary" else "typed_conflict_f1"
        ),
        "included_families": [row["family"] for row in included],
        "minimum_matrix_passed": "qwen" in {row["family"] for row in included}
        and len(included) >= 2,
        "three_family_claim_ready": {row["family"] for row in included}
        == {"qwen", "mistral", "google"},
        "typed_answer_gain_same_direction": bool(included)
        and all(float(row["typed_minus_untyped_answer_correctness"]) > 0 for row in included),
        "conflict_gain_same_direction": bool(included)
        and all(float(row["typed_minus_untyped_conflict_score"]) > 0 for row in included),
        "typed_conflict_gain_same_direction": (
            bool(included)
            and all(float(row["typed_minus_untyped_conflict_score"]) > 0 for row in included)
            if label_granularity == "six_class"
            else None
        ),
        "publication_gold": False,
        "human_iaa": False,
    }
    write_json(output_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        action="append",
        nargs=2,
        metavar=("FAMILY", "PATH"),
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    suites = {str(family): Path(path) for family, path in args.suite}
    result = build_matrix(suites, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
