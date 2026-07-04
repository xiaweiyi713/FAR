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
    fallback_ids: list[str] = []
    for row in rows:
        metadata = row.get("metadata", {})
        queries = metadata.get("retrieval_trace", [])
        revisions = metadata.get("revision_trace", [])
        query_fallback = any(
            not str(item.get("query", {}).get("tactic", "")).startswith("llm:")
            for item in queries
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
    suite = json.loads(
        (suite_dir / "matrix_family_manifest.json").read_text(encoding="utf-8")
    )
    if suite.get("jury_gold") is not True or suite.get("publication_gold") is not False:
        raise ValueError(f"{family}: matrix input is not a jury-gold rescore bundle")
    if suite.get("family") != family or suite.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256:
        raise ValueError(f"{family}: matrix input identity mismatch")
    untyped_report = json.loads(
        (suite_dir / "minus_typed_conflict" / "evaluation" / "report.json").read_text(
            encoding="utf-8"
        )
    )
    comparison = untyped_report.get("comparison")
    if not isinstance(comparison, dict):
        raise ValueError(f"{family}: untyped report has no paired FAR comparison")
    metrics = comparison.get("metrics", {})
    answer = metrics["answer_correctness"]
    conflict = metrics["typed_conflict_f1"]
    fallback = suite["structured_fallback"]
    return {
        "family": family,
        "model": suite.get("model_identity", {}).get("model"),
        "model_identity": suite.get("model_identity"),
        "suite_manifest_sha256": sha256_file(
            suite_dir / "matrix_family_manifest.json"
        ),
        "typed_minus_untyped_answer_correctness": -float(answer["candidate_minus_baseline"]),
        "typed_minus_untyped_answer_ci": [-float(answer["upper"]), -float(answer["lower"])],
        "typed_minus_untyped_conflict_f1": -float(conflict["candidate_minus_baseline"]),
        "typed_minus_untyped_conflict_f1_ci": [
            -float(conflict["upper"]),
            -float(conflict["lower"]),
        ],
        "structured_fallback": fallback,
        "excluded": float(fallback["fallback_rate"]) > 0.30,
        "exclusion_threshold": 0.30,
    }


def build_matrix(suites: dict[str, Path], output_path: Path) -> dict[str, Any]:
    verify_active_protocol()
    if set(suites) - {"qwen", "mistral", "google"}:
        raise ValueError("matrix contains an unregistered system family")
    rows = [_suite_row(family, directory) for family, directory in sorted(suites.items())]
    included = [row for row in rows if not row["excluded"]]
    result = {
        "schema_version": "far-model-matrix-v1",
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "rows": rows,
        "included_families": [row["family"] for row in included],
        "minimum_matrix_passed": "qwen" in {row["family"] for row in included}
        and len(included) >= 2,
        "three_family_claim_ready": {row["family"] for row in included}
        == {"qwen", "mistral", "google"},
        "typed_answer_gain_same_direction": bool(included)
        and all(float(row["typed_minus_untyped_answer_correctness"]) > 0 for row in included),
        "typed_conflict_gain_same_direction": bool(included)
        and all(float(row["typed_minus_untyped_conflict_f1"]) > 0 for row in included),
        "publication_gold": False,
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
