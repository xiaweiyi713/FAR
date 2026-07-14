"""Audit frozen FAR revision traces against construction-derived lexical edits.

This is a post-hoc, model-free development diagnostic. It measures whether the
recorded claim-level revision trace proposed the token edits required by the
construction reference, while keeping final-answer fidelity and action matching
separate. It is not semantic correctness, human validation, or causal evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from far.bench.build.common import read_jsonl, write_json
from far.eval.metrics import revision_delta_scores, token_edit_counters
from far.eval.stats import paired_bootstrap_comparison
from far.paths import repository_root

SCHEMA_VERSION = "far-revision-trace-fidelity-audit-v1"
ANALYSIS_PROFILE = "post-hoc-frozen-revision-trace-fidelity-v1"
BOOTSTRAP_SEED = 1729
BOOTSTRAP_RESAMPLES = 2000
ROOT = repository_root()
DEFAULT_BENCHMARK = ROOT / "bench" / "splits" / "dev.jsonl"
DEFAULT_SOLO_RUNS = ROOT / "diagnostics" / "solo_v1" / "experiments" / "runs"
DEFAULT_FAMILY_RUNS = ROOT / "diagnostics" / "family_dev_v1" / "runs"
DEFAULT_JSON = ROOT / "reports" / "revision_trace_fidelity.json"
DEFAULT_MARKDOWN = ROOT / "reports" / "revision_trace_fidelity.md"
QWEN_METHODS = (
    "far",
    "minus_typed_conflict",
    "minus_typed_revision",
    "minus_refutation_query",
    "minus_boundary_query",
)
FAMILIES = ("mistral", "google", "meta")
PAIR_METRICS = (
    "trace_delta_f1",
    "final_delta_f1",
    "trace_target_hit",
    "trace_target_complete",
    "action_correct",
)
TRACE_BUCKETS = (
    "no_lexical_edit",
    "off_target",
    "partial_target",
    "partial_with_collateral",
    "complete_with_collateral",
    "exact_target",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _by_id(rows: list[dict[str, Any]], *, key: str, role: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        item_id = str(row.get(key, ""))
        if not item_id or item_id in result:
            raise ValueError(f"{role} contains a missing or duplicate {key}: {item_id!r}")
        result[item_id] = row
    if not result:
        raise ValueError(f"{role} must not be empty")
    return result


def _score_counts(expected: int, proposed: int, correct: int) -> tuple[float, float, float]:
    if expected < 0 or proposed < 0 or correct < 0 or correct > min(expected, proposed):
        raise ValueError("invalid revision edit counts")
    if expected == 0:
        precision = 1.0 if proposed == 0 else 0.0
        recall = 1.0
    else:
        precision = correct / proposed if proposed else 0.0
        recall = correct / expected
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _bucket(expected: int, proposed: int, correct: int) -> str:
    if proposed == 0:
        return "no_lexical_edit"
    if correct == 0:
        return "off_target"
    if correct == expected and proposed == expected:
        return "exact_target"
    if correct == expected:
        return "complete_with_collateral"
    if proposed == correct:
        return "partial_target"
    return "partial_with_collateral"


def _counter_total(values: Counter[str]) -> int:
    return sum(values.values())


def _trace_edit_counters(
    traces: list[dict[str, Any]],
) -> tuple[Counter[str], Counter[str], int, int, int]:
    removed: Counter[str] = Counter()
    added: Counter[str] = Counter()
    changed_flags = 0
    text_changes = 0
    flag_mismatches = 0
    for trace in traces:
        before = trace.get("before")
        after = trace.get("after")
        changed = trace.get("changed")
        if (
            not isinstance(before, str)
            or not isinstance(after, str)
            or not isinstance(changed, bool)
        ):
            raise TypeError("revision trace requires string before/after and boolean changed")
        trace_removed, trace_added = token_edit_counters(before, after)
        removed += trace_removed
        added += trace_added
        changed_flags += int(changed)
        text_changed = before != after
        text_changes += int(text_changed)
        flag_mismatches += int(changed != text_changed)
    return removed, added, changed_flags, text_changes, flag_mismatches


def audit_row(sample: dict[str, Any], prediction: dict[str, Any]) -> dict[str, Any]:
    sample_id = str(sample["id"])
    if str(prediction.get("sample_id")) != sample_id:
        raise ValueError("sample and prediction IDs do not match")
    metadata = prediction.get("metadata")
    if not isinstance(metadata, dict):
        raise TypeError("prediction metadata must be an object")
    traces = metadata.get("revision_trace")
    primary = metadata.get("primary_revision_trace")
    if not isinstance(traces, list) or not traces or not isinstance(primary, dict):
        raise TypeError("prediction must expose non-empty revision and primary traces")
    if any(not isinstance(item, dict) for item in traces):
        raise TypeError("revision trace entries must be objects")

    initial = str(sample["initial_answer"])
    reference = str(sample["expected_revision"]["revised_answer"])
    expected_action = str(sample["expected_revision"]["action"])
    predicted_action = str(prediction.get("revision_action", ""))
    expected_removed, expected_added = token_edit_counters(initial, reference)
    trace_removed, trace_added, changed_flags, text_changes, flag_mismatches = _trace_edit_counters(
        traces
    )
    expected = _counter_total(expected_removed) + _counter_total(expected_added)
    trace_proposed = _counter_total(trace_removed) + _counter_total(trace_added)
    trace_correct = _counter_total(expected_removed & trace_removed) + _counter_total(
        expected_added & trace_added
    )
    trace_precision, trace_recall, trace_f1 = _score_counts(expected, trace_proposed, trace_correct)

    answer = prediction.get("answer")
    if not isinstance(answer, str):
        raise TypeError("prediction answer must be a string")
    final_removed, final_added = token_edit_counters(initial, answer)
    final_proposed = _counter_total(final_removed) + _counter_total(final_added)
    final_correct = _counter_total(expected_removed & final_removed) + _counter_total(
        expected_added & final_added
    )
    final_precision, final_recall, final_f1 = revision_delta_scores(initial, answer, reference)
    recomputed_final = _score_counts(expected, final_proposed, final_correct)
    if not all(
        math.isclose(observed, recomputed, rel_tol=0.0, abs_tol=1e-15)
        for observed, recomputed in zip(
            (final_precision, final_recall, final_f1), recomputed_final, strict=True
        )
    ):
        raise ValueError("final revision-delta count and score paths disagree")

    primary_action = primary.get("action")
    if not isinstance(primary_action, str):
        raise TypeError("primary revision trace action must be a string")
    trace_bucket = _bucket(expected, trace_proposed, trace_correct)
    return {
        "sample_id": sample_id,
        "category": str(sample["category"]),
        "expected_action": expected_action,
        "predicted_action": predicted_action,
        "primary_action": primary_action,
        "action_correct": float(predicted_action == expected_action),
        "primary_action_matches_declared": primary_action == predicted_action,
        "expected_edits": expected,
        "trace_changed_flags": changed_flags,
        "trace_text_changes": text_changes,
        "trace_changed_flag_mismatches": flag_mismatches,
        "trace_proposed_edits": trace_proposed,
        "trace_correct_edits": trace_correct,
        "trace_delta_precision": trace_precision,
        "trace_delta_recall": trace_recall,
        "trace_delta_f1": trace_f1,
        "trace_bucket": trace_bucket,
        "trace_target_hit": float(trace_correct > 0),
        "trace_target_complete": float(trace_correct == expected),
        "trace_collateral_edit": float(trace_proposed > trace_correct),
        "final_proposed_edits": final_proposed,
        "final_correct_edits": final_correct,
        "final_delta_precision": final_precision,
        "final_delta_recall": final_recall,
        "final_delta_f1": final_f1,
        "final_bucket": _bucket(expected, final_proposed, final_correct),
    }


def _micro(rows: list[dict[str, Any]], *, prefix: str) -> dict[str, Any]:
    expected = sum(int(row["expected_edits"]) for row in rows)
    proposed = sum(int(row[f"{prefix}_proposed_edits"]) for row in rows)
    correct = sum(int(row[f"{prefix}_correct_edits"]) for row in rows)
    precision, recall, f1 = _score_counts(expected, proposed, correct)
    return {
        "expected_edits": expected,
        "proposed_edits": proposed,
        "correct_edits": correct,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    categories = sorted({str(row["category"]) for row in rows})

    def summarize_subset(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "samples": len(items),
            "action_accuracy": mean(float(row["action_correct"]) for row in items),
            "mean_trace_delta_f1": mean(float(row["trace_delta_f1"]) for row in items),
            "mean_final_delta_f1": mean(float(row["final_delta_f1"]) for row in items),
            "trace_target_hit_rate": mean(float(row["trace_target_hit"]) for row in items),
            "trace_target_complete_rate": mean(
                float(row["trace_target_complete"]) for row in items
            ),
        }

    bucket_counts = Counter(str(row["trace_bucket"]) for row in rows)
    return {
        **summarize_subset(rows),
        "expected_edit_rows": sum(int(row["expected_edits"] > 0) for row in rows),
        "primary_action_match_rows": sum(
            bool(row["primary_action_matches_declared"]) for row in rows
        ),
        "trace_changed_flag_mismatches": sum(
            int(row["trace_changed_flag_mismatches"]) for row in rows
        ),
        "trace_changed_events": sum(int(row["trace_changed_flags"]) for row in rows),
        "trace_bucket_counts": {name: bucket_counts[name] for name in TRACE_BUCKETS},
        "trace_micro": _micro(rows, prefix="trace"),
        "final_micro": _micro(rows, prefix="final"),
        "by_category": {
            category: summarize_subset([row for row in rows if str(row["category"]) == category])
            for category in categories
        },
    }


def _method_result(
    path: Path,
    samples: dict[str, dict[str, Any]],
    *,
    source_key: str,
) -> dict[str, Any]:
    predictions = _by_id(read_jsonl(path), key="sample_id", role=source_key)
    if set(predictions) != set(samples):
        raise ValueError(f"{source_key} does not exactly cover the benchmark")
    rows = [audit_row(samples[sample_id], predictions[sample_id]) for sample_id in sorted(samples)]
    return {
        "source": source_key,
        "prediction_sha256": _sha256(path),
        "summary": _summarize(rows),
        "rows": rows,
    }


def _comparison(untyped: dict[str, Any], typed: dict[str, Any]) -> dict[str, Any]:
    untyped_rows = untyped["rows"]
    typed_rows = typed["rows"]
    return {
        metric: paired_bootstrap_comparison(untyped_rows, typed_rows, metric)
        for metric in PAIR_METRICS
    }


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _family_cluster_bootstrap(family_deltas: dict[str, list[float]]) -> dict[str, Any]:
    if set(family_deltas) != set(FAMILIES) or any(
        len(values) != 60 for values in family_deltas.values()
    ):
        raise ValueError("family trace bootstrap requires three 60-pair clusters")
    rng = random.Random(BOOTSTRAP_SEED)
    estimates: list[float] = []
    families = sorted(family_deltas)
    for _ in range(BOOTSTRAP_RESAMPLES):
        sampled = [rng.choice(families) for _ in families]
        values = [value for family in sampled for value in family_deltas[family]]
        estimates.append(mean(values))
    return {
        "method": "family-cluster-percentile-bootstrap-v1",
        "clusters": 3,
        "pairs_per_cluster": 60,
        "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED,
        "confidence": 0.95,
        "lower": _percentile(estimates, 0.025),
        "upper": _percentile(estimates, 0.975),
        "probability_positive": mean(float(value > 0) for value in estimates),
    }


def compute_report(
    *,
    benchmark_path: Path = DEFAULT_BENCHMARK,
    solo_runs: Path = DEFAULT_SOLO_RUNS,
    family_runs: Path = DEFAULT_FAMILY_RUNS,
) -> dict[str, Any]:
    samples = _by_id(read_jsonl(benchmark_path), key="id", role="development benchmark")
    if len(samples) != 60 or any(str(row.get("split")) != "dev" for row in samples.values()):
        raise ValueError("revision trace audit requires exactly 60 development samples")

    qwen = {
        method: _method_result(
            solo_runs / method / "predictions.jsonl",
            samples,
            source_key=f"solo_v1/{method}",
        )
        for method in QWEN_METHODS
    }
    family: dict[str, dict[str, Any]] = {}
    family_deltas: dict[str, list[float]] = {}
    for family_name in FAMILIES:
        typed = _method_result(
            family_runs / family_name / "far" / "predictions.jsonl",
            samples,
            source_key=f"family_dev_v1/{family_name}/far",
        )
        untyped = _method_result(
            family_runs / family_name / "minus_typed_conflict" / "predictions.jsonl",
            samples,
            source_key=f"family_dev_v1/{family_name}/minus_typed_conflict",
        )
        comparison = _comparison(untyped, typed)
        family[family_name] = {
            "far": typed,
            "minus_typed_conflict": untyped,
            "typed_minus_untyped": comparison,
        }
        family_deltas[family_name] = [
            float(typed_row["trace_delta_f1"]) - float(untyped_row["trace_delta_f1"])
            for typed_row, untyped_row in zip(typed["rows"], untyped["rows"], strict=True)
        ]

    qwen_comparison = _comparison(qwen["minus_typed_conflict"], qwen["far"])
    family_means = {name: mean(values) for name, values in family_deltas.items()}
    far_summary = qwen["far"]["summary"]
    checks = {
        "frozen_dev_only": True,
        "all_methods_cover_60": all(
            method["summary"]["samples"] == 60
            for method in [*qwen.values()]
            + [family[name][arm] for name in FAMILIES for arm in ("far", "minus_typed_conflict")]
        ),
        "all_rows_require_reference_edit": all(
            method["summary"]["expected_edit_rows"] == 60
            for method in [*qwen.values()]
            + [family[name][arm] for name in FAMILIES for arm in ("far", "minus_typed_conflict")]
        ),
        "trace_flags_consistent": all(
            method["summary"]["trace_changed_flag_mismatches"] == 0
            for method in [*qwen.values()]
            + [family[name][arm] for name in FAMILIES for arm in ("far", "minus_typed_conflict")]
        ),
        "primary_action_bound": all(
            method["summary"]["primary_action_match_rows"] == 60
            for method in [*qwen.values()]
            + [family[name][arm] for name in FAMILIES for arm in ("far", "minus_typed_conflict")]
        ),
        "qwen_trace_direction_positive": (
            qwen_comparison["trace_delta_f1"]["candidate_minus_baseline"] > 0.0
        ),
        "family_trace_direction_3_of_3": sum(value > 0.0 for value in family_means.values()) == 3,
        "absolute_qwen_trace_fidelity_bounded": (
            far_summary["mean_trace_delta_f1"] < 0.2
            and far_summary["trace_bucket_counts"]["off_target"] > 0
            and far_summary["trace_bucket_counts"]["no_lexical_edit"] > 0
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "analysis_profile": ANALYSIS_PROFILE,
        "valid": all(checks.values()),
        "checks": checks,
        "boundaries": {
            "post_hoc": True,
            "preregistered_primary": False,
            "model_calls": 0,
            "test_accessed": False,
            "human_review": False,
            "human_iaa": False,
            "publication_gold": False,
            "semantic_correctness": False,
            "construction_reference_dependent": True,
            "causal_attribution": False,
        },
        "benchmark": {
            "source": "bench/splits/dev.jsonl",
            "sha256": _sha256(benchmark_path),
            "samples": 60,
            "split": "dev",
        },
        "qwen": {
            "methods": qwen,
            "typed_minus_untyped": qwen_comparison,
        },
        "family_sensitivity": {
            "families": family,
            "trace_delta_f1": {
                "combined_delta": mean(
                    value for values in family_deltas.values() for value in values
                ),
                "family_deltas": family_means,
                "positive_families": sum(value > 0.0 for value in family_means.values()),
                "family_cluster_bootstrap": _family_cluster_bootstrap(family_deltas),
            },
        },
    }


def _fmt(value: float) -> str:
    return f"{value:.4f}"


def render_markdown(report: dict[str, Any]) -> str:
    qwen = report["qwen"]
    qwen_far = qwen["methods"]["far"]["summary"]
    qwen_compare = qwen["typed_minus_untyped"]["trace_delta_f1"]
    family_delta = report["family_sensitivity"]["trace_delta_f1"]
    cluster = family_delta["family_cluster_bootstrap"]
    qwen_buckets = qwen_far["trace_bucket_counts"]
    qwen_complete = qwen_buckets["exact_target"] + qwen_buckets["complete_with_collateral"]
    lines = [
        "# FAR Frozen Revision-Trace Fidelity Audit",
        "",
        "> Post-hoc, machine-audited development diagnostic over frozen predictions. "
        "No model calls, held-out/test access, human review, semantic judgment, or "
        "publication-gold claim.",
        "",
        "## Main result",
        "",
        f"Qwen FAR records a mean trace delta F1 of `{_fmt(qwen_far['mean_trace_delta_f1'])}`. "
        f"Only `{qwen_complete}/60` "
        "rows completely cover the construction-reference edit target; "
        f"`{qwen_buckets['off_target']}/60` propose only off-target lexical edits and "
        f"`{qwen_buckets['no_lexical_edit']}/60` propose no lexical target edit.",
        "",
        f"Typed minus untyped trace delta F1 is `{qwen_compare['candidate_minus_baseline']:+.4f}` "
        f"with a paired 95% interval of `[{qwen_compare['lower']:+.4f}, "
        f"{qwen_compare['upper']:+.4f}]`. The same post-hoc direction is positive in "
        f"`{family_delta['positive_families']}/3` WS2 families, combined "
        f"`{family_delta['combined_delta']:+.4f}` with a family-cluster interval of "
        f"`[{cluster['lower']:+.4f}, {cluster['upper']:+.4f}]`.",
        "",
        "The directional recurrence is narrower than revision reliability: typed control improves "
        "lexical target alignment on average, but the low absolute trace score and frequent "
        "off-target/collateral edits do not establish semantically correct repair.",
        "",
        "## Qwen frozen methods",
        "",
        "| Method | Action acc. | Trace delta F1 | Final delta F1 | Target hit | "
        "Target complete | Off-target | No edit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in QWEN_METHODS:
        summary = qwen["methods"][name]["summary"]
        buckets = summary["trace_bucket_counts"]
        lines.append(
            f"| `{name}` | {summary['action_accuracy']:.3f} | "
            f"{summary['mean_trace_delta_f1']:.3f} | "
            f"{summary['mean_final_delta_f1']:.3f} | "
            f"{summary['trace_target_hit_rate']:.3f} | "
            f"{summary['trace_target_complete_rate']:.3f} | "
            f"{buckets['off_target']} | {buckets['no_lexical_edit']} |"
        )
    lines.extend(
        [
            "",
            "## WS2 typed-minus-untyped trace sensitivity",
            "",
            "| Family | Trace delta F1 difference |",
            "|---|---:|",
        ]
    )
    for family_name, value in family_delta["family_deltas"].items():
        lines.append(f"| `{family_name}` | {value:+.4f} |")
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "The audit compares token-multiset edits in recorded claim traces with the "
            "construction-derived whole-answer edit target. It can penalize valid paraphrases, "
            "reward incidental token overlap, and cannot decide whether evidence or a revision is "
            "semantically correct. It is post-hoc and must remain subordinate to the preregistered "
            "answer-result and stop-rule evidence.",
            "",
            "Every source prediction is fingerprinted in the JSON report. Recompute with "
            "`falsirag diag revision-trace-audit verify`; the verifier performs zero model calls "
            "and rejects source, report, boundary, or Markdown drift.",
            "",
        ]
    )
    return "\n".join(lines)


def build_reports(
    *,
    benchmark_path: Path = DEFAULT_BENCHMARK,
    solo_runs: Path = DEFAULT_SOLO_RUNS,
    family_runs: Path = DEFAULT_FAMILY_RUNS,
    output_json: Path = DEFAULT_JSON,
    output_markdown: Path = DEFAULT_MARKDOWN,
) -> dict[str, Any]:
    report = compute_report(
        benchmark_path=benchmark_path,
        solo_runs=solo_runs,
        family_runs=family_runs,
    )
    write_json(output_json, report)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(render_markdown(report), encoding="utf-8")
    return report


def verify_reports(
    *,
    benchmark_path: Path = DEFAULT_BENCHMARK,
    solo_runs: Path = DEFAULT_SOLO_RUNS,
    family_runs: Path = DEFAULT_FAMILY_RUNS,
    output_json: Path = DEFAULT_JSON,
    output_markdown: Path = DEFAULT_MARKDOWN,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        observed = json.loads(output_json.read_text(encoding="utf-8"))
        recomputed = compute_report(
            benchmark_path=benchmark_path,
            solo_runs=solo_runs,
            family_runs=family_runs,
        )
        if observed != recomputed:
            errors.append("JSON report differs from deterministic recomputation")
        if output_markdown.read_text(encoding="utf-8") != render_markdown(recomputed):
            errors.append("Markdown report differs from deterministic recomputation")
        if recomputed.get("valid") is not True:
            errors.append("recomputed revision-trace report is invalid")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "far-revision-trace-fidelity-report-audit-v1",
        "valid": not errors,
        "errors": errors,
        "model_calls": 0,
        "test_accessed": False,
        "human_review": False,
        "publication_gold": False,
        "semantic_correctness": False,
    }


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--solo-runs", type=Path, default=DEFAULT_SOLO_RUNS)
    parser.add_argument("--family-runs", type=Path, default=DEFAULT_FAMILY_RUNS)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    verify_parser = subparsers.add_parser("verify")
    _add_common(build_parser)
    _add_common(verify_parser)
    args = parser.parse_args()
    kwargs = {
        "benchmark_path": args.benchmark,
        "solo_runs": args.solo_runs,
        "family_runs": args.family_runs,
        "output_json": args.output_json,
        "output_markdown": args.output_markdown,
    }
    result = build_reports(**kwargs) if args.command == "build" else verify_reports(**kwargs)
    if args.command == "build":
        qwen_far = result["qwen"]["methods"]["far"]["summary"]
        family_delta = result["family_sensitivity"]["trace_delta_f1"]
        result = {
            "schema_version": result["schema_version"],
            "valid": result["valid"],
            "output_json": str(args.output_json),
            "output_markdown": str(args.output_markdown),
            "qwen_far_mean_trace_delta_f1": qwen_far["mean_trace_delta_f1"],
            "qwen_far_complete_target_rows": (
                qwen_far["trace_bucket_counts"]["exact_target"]
                + qwen_far["trace_bucket_counts"]["complete_with_collateral"]
            ),
            "family_trace_delta_f1": family_delta,
            "model_calls": 0,
            "test_accessed": False,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "verify" and not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
