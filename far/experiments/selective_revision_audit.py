"""Audit whether frozen FAR signals support selective typed revision.

This is a post-hoc, model-free development diagnostic. It compares the recorded
typed FAR output, the matched generic-revision ablation, and deterministic
preservation of the erroneous initial answer. It measures metric conflict,
reference-dependent arm-choice headroom, and confidence-threshold behavior. It
does not evaluate a deployable selector, semantic correctness, or a causal
counterfactual policy effect.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from far.bench.build.common import read_jsonl, write_json
from far.eval.metrics import PredictionRecord, revision_delta_scores, score_sample, soft_f1
from far.eval.stats import paired_bootstrap_comparison
from far.experiments.revision_trace_audit import verify_reports as verify_trace_reports
from far.paths import repository_root

SCHEMA_VERSION = "far-selective-revision-feasibility-audit-v1"
AUDIT_SCHEMA_VERSION = "far-selective-revision-feasibility-report-audit-v1"
ANALYSIS_PROFILE = "post-hoc-frozen-selective-revision-feasibility-v1"
CORRECTNESS_THRESHOLD = 0.8
CONFIDENCE_THRESHOLDS = (0.0, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95)
ARMS = ("preserve", "generic", "typed")

ROOT = repository_root()
DEFAULT_BENCHMARK = ROOT / "bench" / "splits" / "dev.jsonl"
DEFAULT_SUITE_MANIFEST = ROOT / "diagnostics" / "solo_v1" / "experiments" / "suite_manifest.json"
DEFAULT_RUNS = ROOT / "diagnostics" / "solo_v1" / "experiments" / "runs"
DEFAULT_EVALUATIONS = ROOT / "diagnostics" / "solo_v1" / "experiments" / "evaluations"
DEFAULT_TRACE_JSON = ROOT / "reports" / "revision_trace_fidelity.json"
DEFAULT_TRACE_MARKDOWN = ROOT / "reports" / "revision_trace_fidelity.md"
DEFAULT_JSON = ROOT / "reports" / "selective_revision_feasibility.json"
DEFAULT_MARKDOWN = ROOT / "reports" / "selective_revision_feasibility.md"


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


def _stable_floats(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 15)
    if isinstance(value, dict):
        return {key: _stable_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stable_floats(item) for item in value]
    return value


def _validate_score_row(
    sample: dict[str, Any], prediction: dict[str, Any], observed: dict[str, Any], role: str
) -> None:
    recomputed = score_sample(sample, PredictionRecord.from_dict(prediction))
    if _stable_floats(observed) != _stable_floats(recomputed):
        raise ValueError(f"{role} score row differs from evaluator recomputation")


def _arm_summary(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    answer_key = f"{arm}_answer_soft_f1"
    delta_key = f"{arm}_revision_delta_f1"
    return {
        "samples": len(rows),
        "mean_answer_soft_f1": mean(float(row[answer_key]) for row in rows),
        "answer_soft_f1_ge_0_8": sum(
            float(row[answer_key]) >= CORRECTNESS_THRESHOLD for row in rows
        ),
        "mean_revision_delta_f1": mean(float(row[delta_key]) for row in rows),
    }


def _paired(rows: list[dict[str, Any]], baseline: str, candidate: str) -> dict[str, Any]:
    return {
        metric: paired_bootstrap_comparison(
            [
                {
                    "sample_id": row["sample_id"],
                    "category": row["category"],
                    metric: row[f"{baseline}_{metric}"],
                }
                for row in rows
            ],
            [
                {
                    "sample_id": row["sample_id"],
                    "category": row["category"],
                    metric: row[f"{candidate}_{metric}"],
                }
                for row in rows
            ],
            metric,
        )
        for metric in ("answer_soft_f1", "revision_delta_f1")
    }


def _arm_choice_envelope(rows: list[dict[str, Any]]) -> dict[str, Any]:
    winners: Counter[str] = Counter()
    envelope: list[float] = []
    for row in rows:
        values = {arm: float(row[f"{arm}_revision_delta_f1"]) for arm in ARMS}
        best = max(values.values())
        envelope.append(best)
        winner = "+".join(arm for arm in ARMS if math.isclose(values[arm], best, abs_tol=1e-15))
        winners[winner] += 1
    typed_mean = mean(float(row["typed_revision_delta_f1"]) for row in rows)
    return {
        "metric": "revision_delta_f1",
        "reference_dependent": True,
        "deployable": False,
        "mean_per_item_max": mean(envelope),
        "gain_over_always_typed": mean(envelope) - typed_mean,
        "winner_counts": dict(sorted(winners.items())),
    }


def _threshold_row(
    rows: list[dict[str, Any]], threshold: float, *, fallback: str
) -> dict[str, Any]:
    if fallback not in {"preserve", "generic"}:
        raise ValueError("confidence curve fallback must be preserve or generic")
    selected = [row for row in rows if float(row["primary_confidence"]) >= threshold]
    answer_values = [
        float(row["typed_answer_soft_f1"])
        if float(row["primary_confidence"]) >= threshold
        else float(row[f"{fallback}_answer_soft_f1"])
        for row in rows
    ]
    delta_values = [
        float(row["typed_revision_delta_f1"])
        if float(row["primary_confidence"]) >= threshold
        else float(row[f"{fallback}_revision_delta_f1"])
        for row in rows
    ]
    return {
        "threshold": threshold,
        "fallback": fallback,
        "selected_rows": len(selected),
        "coverage": len(selected) / len(rows),
        "mean_answer_soft_f1": mean(answer_values),
        "answer_soft_f1_ge_0_8": sum(value >= CORRECTNESS_THRESHOLD for value in answer_values),
        "mean_revision_delta_f1": mean(delta_values),
        "selected_mean_typed_revision_delta_f1": (
            mean(float(row["typed_revision_delta_f1"]) for row in selected) if selected else None
        ),
        "selected_trace_target_complete_rate": (
            mean(float(row["typed_trace_target_complete"]) for row in selected)
            if selected
            else None
        ),
        "selected_trace_collateral_rate": (
            mean(float(row["typed_trace_collateral_edit"]) for row in selected)
            if selected
            else None
        ),
    }


def _confidence_curves(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        fallback: [
            _threshold_row(rows, threshold, fallback=fallback)
            for threshold in CONFIDENCE_THRESHOLDS
        ]
        for fallback in ("preserve", "generic")
    }


def _threshold(
    curves: dict[str, list[dict[str, Any]]], fallback: str, value: float
) -> dict[str, Any]:
    matches = [row for row in curves[fallback] if row["threshold"] == value]
    if len(matches) != 1:
        raise ValueError("confidence curve is missing a required threshold")
    return matches[0]


def compute_report(
    *,
    benchmark_path: Path = DEFAULT_BENCHMARK,
    suite_manifest_path: Path = DEFAULT_SUITE_MANIFEST,
    runs_root: Path = DEFAULT_RUNS,
    evaluations_root: Path = DEFAULT_EVALUATIONS,
    trace_json_path: Path = DEFAULT_TRACE_JSON,
    trace_markdown_path: Path = DEFAULT_TRACE_MARKDOWN,
) -> dict[str, Any]:
    samples = _by_id(read_jsonl(benchmark_path), key="id", role="development benchmark")
    if len(samples) != 60 or any(str(row.get("split")) != "dev" for row in samples.values()):
        raise ValueError("selective revision audit requires exactly 60 development samples")
    if any(
        not str(row.get("expected_revision", {}).get("revised_answer", ""))
        or not str(row.get("expected_revision", {}).get("action", ""))
        for row in samples.values()
    ):
        raise ValueError("every selective revision audit row requires a construction target")

    suite = json.loads(suite_manifest_path.read_text(encoding="utf-8"))
    if (
        suite.get("split") != "dev"
        or suite.get("allow_test") is not False
        or suite.get("reports_only") is not True
        or suite.get("run_manifests", {}).get("far", {}).get("completed") != 60
        or suite.get("run_manifests", {}).get("minus_typed_revision", {}).get("completed") != 60
    ):
        raise ValueError("suite manifest does not bind the two complete frozen dev arms")

    paths = {
        "typed_predictions": runs_root / "far" / "predictions.jsonl",
        "generic_predictions": runs_root / "minus_typed_revision" / "predictions.jsonl",
        "typed_scores": evaluations_root / "far" / "scores.jsonl",
        "generic_scores": evaluations_root / "minus_typed_revision" / "scores.jsonl",
    }
    expected_hashes = {
        "typed_predictions": suite["run_manifests"]["far"]["predictions_sha256"],
        "generic_predictions": suite["run_manifests"]["minus_typed_revision"]["predictions_sha256"],
    }
    for role, expected in expected_hashes.items():
        if _sha256(paths[role]) != expected:
            raise ValueError(f"{role} hash differs from the frozen suite manifest")

    trace_audit = verify_trace_reports(
        output_json=trace_json_path,
        output_markdown=trace_markdown_path,
    )
    if trace_audit.get("valid") is not True:
        raise ValueError("tracked revision-trace report does not verify")
    trace_report = json.loads(trace_json_path.read_text(encoding="utf-8"))
    typed_trace = _by_id(
        trace_report["qwen"]["methods"]["far"]["rows"],
        key="sample_id",
        role="typed trace rows",
    )

    typed_predictions = _by_id(
        read_jsonl(paths["typed_predictions"]), key="sample_id", role="typed predictions"
    )
    generic_predictions = _by_id(
        read_jsonl(paths["generic_predictions"]), key="sample_id", role="generic predictions"
    )
    typed_scores = _by_id(read_jsonl(paths["typed_scores"]), key="sample_id", role="typed scores")
    generic_scores = _by_id(
        read_jsonl(paths["generic_scores"]), key="sample_id", role="generic scores"
    )
    aligned = set(samples)
    if any(
        set(group) != aligned
        for group in (
            typed_trace,
            typed_predictions,
            generic_predictions,
            typed_scores,
            generic_scores,
        )
    ):
        raise ValueError("selective revision sources do not exactly align on sample IDs")

    rows: list[dict[str, Any]] = []
    for sample_id in sorted(samples):
        sample = samples[sample_id]
        typed_prediction = typed_predictions[sample_id]
        generic_prediction = generic_predictions[sample_id]
        _validate_score_row(sample, typed_prediction, typed_scores[sample_id], "typed")
        _validate_score_row(sample, generic_prediction, generic_scores[sample_id], "generic")
        primary = typed_prediction.get("metadata", {}).get("primary_revision_trace")
        if not isinstance(primary, dict):
            raise TypeError("typed prediction is missing its primary revision trace")
        confidence = primary.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0.0 <= confidence <= 1.0
        ):
            raise ValueError("typed primary confidence must be finite and within [0, 1]")
        if primary.get("action") != typed_prediction.get("revision_action"):
            raise ValueError("typed primary action differs from the declared revision action")

        initial = str(sample["initial_answer"])
        reference = str(sample["expected_revision"]["revised_answer"])
        preserve_delta = revision_delta_scores(initial, initial, reference)[2]
        if preserve_delta != 0.0:
            raise ValueError("preserving an erroneous initial answer must make zero target edit")
        trace_row = typed_trace[sample_id]
        rows.append(
            {
                "sample_id": sample_id,
                "category": str(sample["category"]),
                "primary_confidence": float(confidence),
                "primary_action": str(primary["action"]),
                "typed_trace_bucket": str(trace_row["trace_bucket"]),
                "typed_trace_target_complete": float(trace_row["trace_target_complete"]),
                "typed_trace_collateral_edit": float(trace_row["trace_collateral_edit"]),
                "preserve_answer_soft_f1": soft_f1(initial, reference),
                "preserve_revision_delta_f1": preserve_delta,
                "generic_answer_soft_f1": float(generic_scores[sample_id]["answer_correctness"]),
                "generic_revision_delta_f1": float(generic_scores[sample_id]["revision_delta_f1"]),
                "typed_answer_soft_f1": float(typed_scores[sample_id]["answer_correctness"]),
                "typed_revision_delta_f1": float(typed_scores[sample_id]["revision_delta_f1"]),
            }
        )

    fixed_arms = {arm: _arm_summary(rows, arm) for arm in ARMS}
    comparisons = {
        "typed_minus_generic": _paired(rows, "generic", "typed"),
        "typed_minus_preserve": _paired(rows, "preserve", "typed"),
        "generic_minus_preserve": _paired(rows, "preserve", "generic"),
    }
    envelope = _arm_choice_envelope(rows)
    curves = _confidence_curves(rows)
    all_typed = _threshold(curves, "preserve", 0.0)
    high_confidence = _threshold(curves, "preserve", 0.9)
    checks = {
        "frozen_dev_sources_aligned": len(rows) == 60,
        "all_rows_require_reference_edit": all(
            str(sample["initial_answer"]) != str(sample["expected_revision"]["revised_answer"])
            for sample in samples.values()
        ),
        "whole_answer_threshold_false_safe": (
            fixed_arms["preserve"]["answer_soft_f1_ge_0_8"] == 60
            and fixed_arms["preserve"]["mean_answer_soft_f1"]
            > fixed_arms["generic"]["mean_answer_soft_f1"]
            > fixed_arms["typed"]["mean_answer_soft_f1"]
        ),
        "typed_revision_tradeoff_recurs": (
            fixed_arms["typed"]["mean_revision_delta_f1"]
            > fixed_arms["generic"]["mean_revision_delta_f1"]
            > fixed_arms["preserve"]["mean_revision_delta_f1"]
            and fixed_arms["typed"]["mean_answer_soft_f1"]
            < fixed_arms["generic"]["mean_answer_soft_f1"]
        ),
        "confidence_threshold_not_fidelity_improving": (
            high_confidence["selected_rows"] == 31
            and high_confidence["selected_mean_typed_revision_delta_f1"]
            <= all_typed["selected_mean_typed_revision_delta_f1"]
            and high_confidence["selected_trace_target_complete_rate"]
            <= all_typed["selected_trace_target_complete_rate"]
            and high_confidence["selected_trace_collateral_rate"]
            >= all_typed["selected_trace_collateral_rate"]
        ),
        "reference_envelope_headroom_below_0_02": (0.0 < envelope["gain_over_always_typed"] < 0.02),
        "no_deployable_selector_claim": True,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "analysis_profile": ANALYSIS_PROFILE,
        "valid": all(checks.values()),
        "checks": checks,
        "boundaries": {
            "post_hoc": True,
            "preregistered_primary": False,
            "reference_dependent": True,
            "deployable_selector_evaluated": False,
            "prospective_confidence_calibration": False,
            "registered_policy_utility": False,
            "counterfactual_policy_effect": False,
            "semantic_correctness": False,
            "independent_arm_runs": True,
            "preserve_output_generated": False,
            "model_calls": 0,
            "test_accessed": False,
            "human_review": False,
            "human_iaa": False,
            "publication_gold": False,
        },
        "sources": {
            "benchmark": {
                "path": "bench/splits/dev.jsonl",
                "sha256": _sha256(benchmark_path),
                "samples": 60,
                "split": "dev",
            },
            "suite_manifest_sha256": _sha256(suite_manifest_path),
            "trace_report_sha256": _sha256(trace_json_path),
            **{
                role: {"path": str(path.relative_to(ROOT)), "sha256": _sha256(path)}
                for role, path in paths.items()
            },
        },
        "fixed_arms": fixed_arms,
        "paired_comparisons": comparisons,
        "reference_arm_choice_envelope": envelope,
        "confidence_curves": curves,
        "rows": rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    arms = report["fixed_arms"]
    envelope = report["reference_arm_choice_envelope"]
    curves = report["confidence_curves"]["preserve"]
    high = next(row for row in curves if row["threshold"] == 0.9)
    lines = [
        "# FAR Selective-Revision Feasibility Audit",
        "",
        "> Post-hoc, reference-dependent development diagnostic over frozen outputs. No model "
        "calls, held-out/test access, human review, semantic judgment, deployable selector, or "
        "causal policy-effect claim.",
        "",
        "## Main result",
        "",
        f"All 60 construction rows require a lexical edit, yet preserving the erroneous initial "
        f"answer obtains mean whole-answer soft F1 `{arms['preserve']['mean_answer_soft_f1']:.4f}` "
        f"and places `{arms['preserve']['answer_soft_f1_ge_0_8']}/60` rows above the historical "
        "0.8 threshold. Whole-answer overlap is therefore unsafe as a selective-revision gate.",
        "",
        f"Typed revision improves mean lexical revision-delta F1 from "
        f"`{arms['generic']['mean_revision_delta_f1']:.4f}` for generic revision to "
        f"`{arms['typed']['mean_revision_delta_f1']:.4f}`, but its whole-answer soft F1 is lower "
        f"(`{arms['typed']['mean_answer_soft_f1']:.4f}` versus "
        f"`{arms['generic']['mean_answer_soft_f1']:.4f}`). A reference-dependent per-item maximum "
        f"over preserve/generic/typed reaches only `{envelope['mean_per_item_max']:.4f}` delta F1, "
        f"or `{envelope['gain_over_always_typed']:+.4f}` over always typed.",
        "",
        f"Filtering typed revisions at recorded primary confidence >=0.90 selects "
        f"`{high['selected_rows']}/60` rows. Their conditional delta F1 is "
        f"`{high['selected_mean_typed_revision_delta_f1']:.4f}`, target-complete rate is "
        f"`{high['selected_trace_target_complete_rate']:.4f}`, and collateral-edit rate is "
        f"`{high['selected_trace_collateral_rate']:.4f}`. None improves on the unfiltered typed "
        "trace. Current confidence is not a demonstrated fidelity selector.",
        "",
        "## Fixed-arm metric conflict",
        "",
        "| Frozen arm | Mean answer soft F1 | Rows >=0.8 | Mean revision-delta F1 |",
        "|---|---:|---:|---:|",
    ]
    for arm in ARMS:
        summary = arms[arm]
        lines.append(
            f"| `{arm}` | {summary['mean_answer_soft_f1']:.4f} | "
            f"{summary['answer_soft_f1_ge_0_8']}/60 | "
            f"{summary['mean_revision_delta_f1']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Confidence-threshold replay with preserve fallback",
            "",
            "| Threshold | Typed coverage | Mean answer soft F1 | Mean delta F1 | "
            "Selected delta F1 | Complete target | Collateral |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in curves:
        selected_delta = row["selected_mean_typed_revision_delta_f1"]
        complete = row["selected_trace_target_complete_rate"]
        collateral = row["selected_trace_collateral_rate"]
        lines.append(
            f"| {row['threshold']:.2f} | {row['selected_rows']}/60 | "
            f"{row['mean_answer_soft_f1']:.4f} | {row['mean_revision_delta_f1']:.4f} | "
            f"{'--' if selected_delta is None else f'{selected_delta:.4f}'} | "
            f"{'--' if complete is None else f'{complete:.4f}'} | "
            f"{'--' if collateral is None else f'{collateral:.4f}'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "The three outcomes are not causal counterfactuals: typed and generic answers come "
            "from independent frozen runs, while preserve is scored without generation. The "
            "per-item maximum and every delta-F1 result use the construction reference. The "
            "confidence curve was inspected on the same 60 development rows and has no "
            "prospective calibration or registered utility. It cannot license a selector, "
            "semantic repair claim, or held-out performance estimate.",
            "",
            "The observed arm-choice headroom is small relative to the low absolute edit fidelity. "
            "A future selector therefore needs a newly preregistered development branch, a "
            "reference-free confidence signal calibrated before evaluation, and a utility that "
            "jointly handles edit benefit, collateral risk, and abstention. Recompute with "
            "`falsirag diag selective-revision-audit verify`.",
            "",
        ]
    )
    return "\n".join(lines)


def build_reports(
    *,
    benchmark_path: Path = DEFAULT_BENCHMARK,
    suite_manifest_path: Path = DEFAULT_SUITE_MANIFEST,
    runs_root: Path = DEFAULT_RUNS,
    evaluations_root: Path = DEFAULT_EVALUATIONS,
    trace_json_path: Path = DEFAULT_TRACE_JSON,
    trace_markdown_path: Path = DEFAULT_TRACE_MARKDOWN,
    output_json: Path = DEFAULT_JSON,
    output_markdown: Path = DEFAULT_MARKDOWN,
) -> dict[str, Any]:
    report = compute_report(
        benchmark_path=benchmark_path,
        suite_manifest_path=suite_manifest_path,
        runs_root=runs_root,
        evaluations_root=evaluations_root,
        trace_json_path=trace_json_path,
        trace_markdown_path=trace_markdown_path,
    )
    write_json(output_json, report)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(render_markdown(report), encoding="utf-8")
    return report


def verify_reports(
    *,
    benchmark_path: Path = DEFAULT_BENCHMARK,
    suite_manifest_path: Path = DEFAULT_SUITE_MANIFEST,
    runs_root: Path = DEFAULT_RUNS,
    evaluations_root: Path = DEFAULT_EVALUATIONS,
    trace_json_path: Path = DEFAULT_TRACE_JSON,
    trace_markdown_path: Path = DEFAULT_TRACE_MARKDOWN,
    output_json: Path = DEFAULT_JSON,
    output_markdown: Path = DEFAULT_MARKDOWN,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        observed = json.loads(output_json.read_text(encoding="utf-8"))
        recomputed = compute_report(
            benchmark_path=benchmark_path,
            suite_manifest_path=suite_manifest_path,
            runs_root=runs_root,
            evaluations_root=evaluations_root,
            trace_json_path=trace_json_path,
            trace_markdown_path=trace_markdown_path,
        )
        if observed != recomputed:
            errors.append("JSON report differs from deterministic recomputation")
        if output_markdown.read_text(encoding="utf-8") != render_markdown(recomputed):
            errors.append("Markdown report differs from deterministic recomputation")
        if recomputed.get("valid") is not True:
            errors.append("recomputed selective-revision report is invalid")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "valid": not errors,
        "errors": errors,
        "model_calls": 0,
        "test_accessed": False,
        "human_review": False,
        "publication_gold": False,
        "semantic_correctness": False,
        "deployable_selector_evaluated": False,
    }


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--suite-manifest", type=Path, default=DEFAULT_SUITE_MANIFEST)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--evaluations-root", type=Path, default=DEFAULT_EVALUATIONS)
    parser.add_argument("--trace-json", type=Path, default=DEFAULT_TRACE_JSON)
    parser.add_argument("--trace-markdown", type=Path, default=DEFAULT_TRACE_MARKDOWN)
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
        "suite_manifest_path": args.suite_manifest,
        "runs_root": args.runs_root,
        "evaluations_root": args.evaluations_root,
        "trace_json_path": args.trace_json,
        "trace_markdown_path": args.trace_markdown,
        "output_json": args.output_json,
        "output_markdown": args.output_markdown,
    }
    result = build_reports(**kwargs) if args.command == "build" else verify_reports(**kwargs)
    if args.command == "build":
        result = {
            "schema_version": result["schema_version"],
            "valid": result["valid"],
            "output_json": str(args.output_json),
            "output_markdown": str(args.output_markdown),
            "fixed_arms": result["fixed_arms"],
            "reference_arm_choice_envelope": result["reference_arm_choice_envelope"],
            "model_calls": 0,
            "test_accessed": False,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "verify" and not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
