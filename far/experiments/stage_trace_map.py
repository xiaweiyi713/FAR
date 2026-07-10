"""Capability-aware stage trace attribution over frozen RAMDocs Round 1 artifacts.

This analysis is intentionally model-free and observational. It compares only
fields shared by all eight methods, then reports detection/action details for the
two FAR arms that actually expose those traces. It never labels metadata-only
edits as causal oracle interventions.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from far.bench.build.common import read_jsonl, sha256_file, write_json
from far.eval.ramdocs import normalize_ramdocs_answer

METHODS = (
    "vanilla_rag",
    "multi_query_rag",
    "crag_style_reproduction",
    "self_rag_style_reproduction",
    "reflective_rag",
    "counterrefine_style_reproduction",
    "far",
    "far_minus_typed_conflict",
)
FAR_TRACE_METHODS = ("far", "far_minus_typed_conflict")
BUCKETS = (
    "correct",
    "retrieval_unscorable",
    "retrieval_miss",
    "post_retrieval_unchanged_wrong",
    "post_retrieval_changed_wrong",
)
_CITATION = re.compile(r"\[[^\]]+\]")


def _by_id(
    rows: Iterable[dict[str, Any]],
    *,
    key: str,
    role: str,
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = row.get(key)
        if value is None or not str(value).strip():
            raise ValueError(f"{role} row is missing {key}")
        item_id = str(value)
        if item_id in indexed:
            raise ValueError(f"duplicate {role} {key}: {item_id}")
        indexed[item_id] = row
    if not indexed:
        raise ValueError(f"{role} rows must not be empty")
    return indexed


def answer_changed(initial_answer: str, final_answer: str) -> bool:
    """Compare answer text after removing citations and frozen normalization."""

    initial = normalize_ramdocs_answer(_CITATION.sub(" ", initial_answer))
    final = normalize_ramdocs_answer(_CITATION.sub(" ", final_answer))
    return initial != final


def correct_document_recall(
    prediction: dict[str, Any],
    correct_document_ids: set[str],
) -> float | None:
    if not correct_document_ids:
        return None
    evidence_ids = prediction.get("evidence_ids")
    if not isinstance(evidence_ids, list) or any(
        not isinstance(item, str) for item in evidence_ids
    ):
        raise TypeError("prediction evidence_ids must be a list of strings")
    retrieved = set(evidence_ids)
    return len(retrieved & correct_document_ids) / len(correct_document_ids)


def classify_trace_cell(
    *,
    prediction: dict[str, Any],
    score: dict[str, Any],
    initial_answer: str,
    correct_document_ids: set[str],
) -> dict[str, Any]:
    """Assign one method/sample cell to the frozen exhaustive trace map."""

    exact_match = float(score["ramdocs_exact_match"])
    if exact_match not in (0.0, 1.0):
        raise ValueError("ramdocs_exact_match must be binary")
    final_answer = prediction.get("answer")
    if not isinstance(final_answer, str):
        raise TypeError("prediction answer must be a string")
    retrieval_recall = correct_document_recall(prediction, correct_document_ids)
    changed = answer_changed(initial_answer, final_answer)
    if exact_match == 1.0:
        bucket = "correct"
    elif retrieval_recall is None:
        bucket = "retrieval_unscorable"
    elif retrieval_recall == 0.0:
        bucket = "retrieval_miss"
    elif changed:
        bucket = "post_retrieval_changed_wrong"
    else:
        bucket = "post_retrieval_unchanged_wrong"
    return {
        "bucket": bucket,
        "correct_document_recall": retrieval_recall,
        "retrieval_scorable": retrieval_recall is not None,
        "answer_changed": changed,
    }


def _correct_documents(corpus: list[dict[str, Any]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    seen_document_ids: set[str] = set()
    for row in corpus:
        document_id = str(row.get("doc_id", ""))
        if not document_id or document_id in seen_document_ids:
            raise ValueError(f"invalid or duplicate corpus doc_id: {document_id!r}")
        seen_document_ids.add(document_id)
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            raise TypeError("corpus metadata must be a mapping")
        sample_id = str(metadata.get("sample_id", ""))
        if not sample_id:
            raise ValueError(f"corpus document {document_id} is missing metadata.sample_id")
        if metadata.get("document_type") == "correct":
            result.setdefault(sample_id, set()).add(document_id)
    return result


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def cluster_bootstrap_difference(
    cells_by_sample: dict[str, dict[str, str]],
    *,
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    """Bootstrap changed-wrong minus retrieval-miss by sample cluster."""

    if resamples < 1:
        raise ValueError("resamples must be positive")
    sample_ids = sorted(cells_by_sample)
    if not sample_ids:
        raise ValueError("cluster bootstrap requires samples")
    if any(set(methods) != set(METHODS) for methods in cells_by_sample.values()):
        raise ValueError("each sample cluster must contain all frozen methods")
    cluster_differences = {
        sample_id: sum(
            bucket == "post_retrieval_changed_wrong"
            for bucket in cells_by_sample[sample_id].values()
        )
        - sum(bucket == "retrieval_miss" for bucket in cells_by_sample[sample_id].values())
        for sample_id in sample_ids
    }
    denominator = len(sample_ids) * len(METHODS)
    estimate = sum(cluster_differences.values()) / denominator
    rng = random.Random(seed)
    estimates = [
        sum(cluster_differences[rng.choice(sample_ids)] for _ in sample_ids) / denominator
        for _ in range(resamples)
    ]
    return {
        "method": "sample-cluster-percentile-bootstrap-v1",
        "estimand": "P(post_retrieval_changed_wrong)-P(retrieval_miss)",
        "estimate": estimate,
        "lower": _percentile(estimates, 0.025),
        "upper": _percentile(estimates, 0.975),
        "confidence": 0.95,
        "resamples": resamples,
        "seed": seed,
        "clusters": len(sample_ids),
        "methods_per_cluster": len(METHODS),
        "direction_supported": _percentile(estimates, 0.025) > 0.0,
    }


def _far_trace_changed(prediction: dict[str, Any]) -> bool:
    metadata = prediction.get("metadata")
    if not isinstance(metadata, dict):
        raise TypeError("FAR prediction metadata must be a mapping")
    revision_trace = metadata.get("revision_trace")
    if not isinstance(revision_trace, list) or not revision_trace:
        raise ValueError("FAR prediction must contain a non-empty revision_trace")
    for item in revision_trace:
        if not isinstance(item, dict) or not isinstance(item.get("changed"), bool):
            raise TypeError("FAR revision_trace items must contain boolean changed")
    return any(bool(item["changed"]) for item in revision_trace)


def _far_detail(
    *,
    method: str,
    cells: dict[str, dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    actions: Counter[str] = Counter()
    trace_text_agreement: Counter[str] = Counter()
    failure_signal_map: Counter[str] = Counter()
    misinformation_post_retrieval_wrong: Counter[str] = Counter()
    for sample_id in sorted(cells):
        prediction = predictions[sample_id]
        conflict_types = prediction.get("predicted_conflict_types")
        if not isinstance(conflict_types, list) or any(
            not isinstance(item, str) for item in conflict_types
        ):
            raise TypeError(f"{method} predicted_conflict_types must be a list of strings")
        action = prediction.get("revision_action")
        if not isinstance(action, str) or not action:
            raise TypeError(f"{method} revision_action must be a non-empty string")
        actions[action] += 1
        conflict_signal = bool(conflict_types)
        trace_changed = _far_trace_changed(prediction)
        text_changed = bool(cells[sample_id]["answer_changed"])
        trace_text_agreement[
            f"text_{'changed' if text_changed else 'unchanged'}__"
            f"trace_{'changed' if trace_changed else 'unchanged'}"
        ] += 1
        bucket = str(cells[sample_id]["bucket"])
        if bucket != "correct":
            failure_signal_map[
                f"{bucket}__{'conflict_signal' if conflict_signal else 'no_conflict_signal'}"
            ] += 1
        if tasks[sample_id].get("category") == "ambiguity_misinformation" and bucket in {
            "post_retrieval_unchanged_wrong",
            "post_retrieval_changed_wrong",
        }:
            misinformation_post_retrieval_wrong[
                f"{'conflict_signal' if conflict_signal else 'no_conflict_signal'}__"
                f"trace_{'changed' if trace_changed else 'unchanged'}"
            ] += 1
    return {
        "method": method,
        "samples": len(cells),
        "revision_action_counts": dict(sorted(actions.items())),
        "text_change_vs_revision_trace": dict(sorted(trace_text_agreement.items())),
        "wrong_bucket_by_conflict_signal": dict(sorted(failure_signal_map.items())),
        "ambiguity_misinformation_post_retrieval_wrong_2x2": dict(
            sorted(misinformation_post_retrieval_wrong.items())
        ),
        "weak_labels": True,
        "causal_attribution": False,
    }


def compute_stage_trace_map(
    *,
    ramdocs_data_dir: Path,
    round1_dir: Path,
    resamples: int = 5000,
    seed: int = 1729,
) -> dict[str, Any]:
    """Compute the frozen capability-aware 8-method trace map."""

    tasks_path = ramdocs_data_dir / "splits/dev.jsonl"
    corpus_path = ramdocs_data_dir / "corpus.jsonl"
    suite_manifest_path = round1_dir / "suite_manifest.json"
    initial_path = round1_dir / "initial_answers/predictions.jsonl"
    tasks = _by_id(read_jsonl(tasks_path), key="id", role="task")
    initial = _by_id(read_jsonl(initial_path), key="sample_id", role="initial answer")
    if set(tasks) != set(initial):
        raise ValueError("task and initial-answer sample IDs differ")
    correct_documents = _correct_documents(read_jsonl(corpus_path))
    suite_manifest = json.loads(suite_manifest_path.read_text(encoding="utf-8"))
    if set(suite_manifest.get("methods", [])) != set(METHODS):
        raise ValueError("suite manifest methods differ from the frozen method set")
    if int(suite_manifest.get("samples", -1)) != len(tasks):
        raise ValueError("suite manifest sample count differs from tasks")
    if suite_manifest.get("split") != "dev" or suite_manifest.get("publication_gold") is not False:
        raise ValueError("trace map requires the non-gold RAMDocs dev suite")

    source_fingerprints = {
        "tasks": sha256_file(tasks_path),
        "corpus": sha256_file(corpus_path),
        "suite_manifest": sha256_file(suite_manifest_path),
        "initial_answers": sha256_file(initial_path),
    }
    method_map: dict[str, Any] = {}
    cells_by_method: dict[str, dict[str, dict[str, Any]]] = {}
    cells_by_sample: dict[str, dict[str, str]] = {sample_id: {} for sample_id in sorted(tasks)}
    prediction_rows: dict[str, dict[str, dict[str, Any]]] = {}
    for method in METHODS:
        prediction_path = round1_dir / "runs" / method / "predictions.jsonl"
        score_path = round1_dir / "evaluations" / method / "scores.jsonl"
        predictions = _by_id(
            read_jsonl(prediction_path), key="sample_id", role=f"{method} prediction"
        )
        scores = _by_id(read_jsonl(score_path), key="sample_id", role=f"{method} score")
        if set(predictions) != set(tasks) or set(scores) != set(tasks):
            raise ValueError(f"{method} predictions/scores do not exactly cover tasks")
        source_fingerprints[f"predictions:{method}"] = sha256_file(prediction_path)
        source_fingerprints[f"scores:{method}"] = sha256_file(score_path)
        method_cells: dict[str, dict[str, Any]] = {}
        counts: Counter[str] = Counter()
        for sample_id in sorted(tasks):
            if predictions[sample_id].get("method") != method:
                raise ValueError(f"prediction method mismatch for {method}:{sample_id}")
            if scores[sample_id].get("method") != method:
                raise ValueError(f"score method mismatch for {method}:{sample_id}")
            cell = classify_trace_cell(
                prediction=predictions[sample_id],
                score=scores[sample_id],
                initial_answer=str(initial[sample_id]["answer"]),
                correct_document_ids=correct_documents.get(sample_id, set()),
            )
            method_cells[sample_id] = cell
            counts[str(cell["bucket"])] += 1
            cells_by_sample[sample_id][method] = str(cell["bucket"])
        if sum(counts.values()) != len(tasks):
            raise AssertionError(f"{method} trace buckets are not exhaustive")
        counts_with_zeros = {bucket: counts.get(bucket, 0) for bucket in BUCKETS}
        method_map[method] = {
            "samples": len(tasks),
            "counts": counts_with_zeros,
            "proportions": {bucket: counts_with_zeros[bucket] / len(tasks) for bucket in BUCKETS},
        }
        cells_by_method[method] = method_cells
        prediction_rows[method] = predictions

    method_passes = {
        method: (
            method_map[method]["counts"]["post_retrieval_changed_wrong"]
            > method_map[method]["counts"]["retrieval_miss"]
        )
        for method in METHODS
    }
    passed_methods = sum(method_passes.values())
    pooled = cluster_bootstrap_difference(cells_by_sample, resamples=resamples, seed=seed)
    capabilities = {
        method: {
            "retrieval_evidence_ids": True,
            "shared_initial_and_final_answer": True,
            "typed_conflict_signal": method in FAR_TRACE_METHODS,
            "revision_action": method in FAR_TRACE_METHODS,
            "claim_level_revision_trace": method in FAR_TRACE_METHODS,
        }
        for method in METHODS
    }
    far_details = {
        method: _far_detail(
            method=method,
            cells=cells_by_method[method],
            predictions=prediction_rows[method],
            tasks=tasks,
        )
        for method in FAR_TRACE_METHODS
    }
    return {
        "schema_version": "far-stage-trace-map-v1",
        "analysis_kind": "observational_capability_aware_trace_attribution",
        "split": "dev",
        "samples": len(tasks),
        "methods": list(METHODS),
        "sample_method_cells": len(tasks) * len(METHODS),
        "bucket_order": list(BUCKETS),
        "method_map": method_map,
        "t1": {
            "criterion": "post_retrieval_changed_wrong > retrieval_miss in at least 6/8 methods",
            "method_passes": method_passes,
            "passed_methods": passed_methods,
            "required_methods": 6,
            "supported": passed_methods >= 6,
        },
        "t2": pooled,
        "capability_matrix": capabilities,
        "far_trace_details": far_details,
        "statistics": {"resamples": resamples, "seed": seed},
        "source_fingerprints": dict(sorted(source_fingerprints.items())),
        "model_calls": 0,
        "causal_attribution": False,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
        "claim_boundary": [
            "T1/T2 describe post-retrieval textual answer transformation failures.",
            "Only FAR arms expose typed detection and claim-level revision traces.",
            "The analysis does not estimate causal oracle or implementation gaps.",
        ],
    }


def report_text(result: dict[str, Any]) -> str:
    """Render the deterministic reader-facing stage trace report."""

    lines = [
        "# Stage-wise trace map (observational)",
        "",
        "> This is a zero-model, capability-aware trace attribution over frozen RAMDocs dev",
        "> artifacts. It is not a causal oracle ladder and does not use human gold.",
        "",
        "## Decision summary",
        "",
        f"- Samples: `{result['samples']}`; methods: `{len(result['methods'])}`; cells: "
        f"`{result['sample_method_cells']}`.",
        f"- T1 methods passing: `{result['t1']['passed_methods']}/8`; supported: "
        f"`{str(result['t1']['supported']).lower()}`.",
        f"- T2 changed-wrong minus retrieval-miss: `{result['t2']['estimate']:+.4f}` "
        f"(95% CI `[{result['t2']['lower']:+.4f}, {result['t2']['upper']:+.4f}]`).",
        "- Causal attribution: `false`; publication gold: `false`; test accessed: `false`.",
        "",
        "## 8-method failure map",
        "",
        (
            "| Method | Correct | Retrieval unscorable | Retrieval miss | "
            "Retrieved + unchanged wrong | Retrieved + changed wrong | T1 |"
        ),
        "|---|---:|---:|---:|---:|---:|:---:|",
    ]
    for method in METHODS:
        counts = result["method_map"][method]["counts"]
        lines.append(
            f"| `{method}` | {counts['correct']} | {counts['retrieval_unscorable']} | "
            f"{counts['retrieval_miss']} | "
            f"{counts['post_retrieval_unchanged_wrong']} | "
            f"{counts['post_retrieval_changed_wrong']} | "
            f"{'yes' if result['t1']['method_passes'][method] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "`changed` means citation-stripped normalized text changed relative to the shared "
            "initial answer. It does not mean the factual revision was correct.",
            "",
            "## Capability matrix",
            "",
            "| Method | Retrieval IDs | Initial/final answer | Typed conflict | "
            "Revision action | Claim revision trace |",
            "|---|:---:|:---:|:---:|:---:|:---:|",
        ]
    )
    for method in METHODS:
        row = result["capability_matrix"][method]
        markers = [
            "yes" if row[key] else "no"
            for key in (
                "retrieval_evidence_ids",
                "shared_initial_and_final_answer",
                "typed_conflict_signal",
                "revision_action",
                "claim_level_revision_trace",
            )
        ]
        lines.append(f"| `{method}` | " + " | ".join(markers) + " |")
    lines.extend(
        [
            "",
            "## FAR-only trace detail",
            "",
        ]
    )
    for method in FAR_TRACE_METHODS:
        detail = result["far_trace_details"][method]
        lines.extend(
            [
                f"### `{method}`",
                "",
                "Revision actions: "
                + ", ".join(
                    f"`{key}={value}`" for key, value in detail["revision_action_counts"].items()
                ),
                "",
                "Weak-label misinformation/post-retrieval/wrong 2x2: "
                + (
                    ", ".join(
                        f"`{key}={value}`"
                        for key, value in detail[
                            "ambiguity_misinformation_post_retrieval_wrong_2x2"
                        ].items()
                    )
                    or "none"
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## Claim boundary",
            "",
            (
                "- The cross-method result concerns post-retrieval answer transformation, "
                "not detection."
            ),
            (
                "- Detection/action traces are absent for six baselines and are not "
                "imputed as failures."
            ),
            "- Two samples lack upstream correct-document labels and are retrieval-unscorable.",
            "- RAMDocs labels are upstream labels, not human IAA or publication-grade gold.",
            "- No model was called and no held-out test was accessed.",
            "",
        ]
    )
    return "\n".join(lines)


def build_reports(
    *,
    ramdocs_data_dir: Path,
    round1_dir: Path,
    output_json: Path,
    output_report: Path,
    resamples: int = 5000,
    seed: int = 1729,
) -> dict[str, Any]:
    result = compute_stage_trace_map(
        ramdocs_data_dir=ramdocs_data_dir,
        round1_dir=round1_dir,
        resamples=resamples,
        seed=seed,
    )
    write_json(output_json, result)
    output_report.parent.mkdir(parents=True, exist_ok=True)
    output_report.write_text(report_text(result), encoding="utf-8")
    return result


def verify_reports(
    *,
    ramdocs_data_dir: Path,
    round1_dir: Path,
    output_json: Path,
    output_report: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        observed = json.loads(output_json.read_text(encoding="utf-8"))
        statistics = observed["statistics"]
        recomputed = compute_stage_trace_map(
            ramdocs_data_dir=ramdocs_data_dir,
            round1_dir=round1_dir,
            resamples=int(statistics["resamples"]),
            seed=int(statistics["seed"]),
        )
        if observed != recomputed:
            errors.append("JSON report differs from deterministic recomputation")
        if output_report.read_text(encoding="utf-8") != report_text(recomputed):
            errors.append("Markdown report differs from deterministic recomputation")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "far-stage-trace-map-audit-v1",
        "valid": not errors,
        "errors": errors,
        "model_calls": 0,
        "causal_attribution": False,
        "publication_gold": False,
        "test_accessed": False,
    }


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ramdocs-data-dir",
        type=Path,
        default=Path("bench/external/ramdocs_v1"),
    )
    parser.add_argument(
        "--round1-dir",
        type=Path,
        default=Path("diagnostics/ramdocs_v2/round1"),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("reports/stage_trace_map.json"),
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=Path("reports/stage_trace_map.md"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    _add_common(build_parser)
    build_parser.add_argument("--resamples", type=int, default=5000)
    build_parser.add_argument("--seed", type=int, default=1729)
    verify_parser = subparsers.add_parser("verify")
    _add_common(verify_parser)
    args = parser.parse_args()
    if args.command == "build":
        result = build_reports(
            ramdocs_data_dir=args.ramdocs_data_dir,
            round1_dir=args.round1_dir,
            output_json=args.output_json,
            output_report=args.output_report,
            resamples=args.resamples,
            seed=args.seed,
        )
    else:
        result = verify_reports(
            ramdocs_data_dir=args.ramdocs_data_dir,
            round1_dir=args.round1_dir,
            output_json=args.output_json,
            output_report=args.output_report,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "verify" and not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
