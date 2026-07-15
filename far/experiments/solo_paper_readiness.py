"""Audit the relaxed, transparent single-author machine-audited paper profile."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from far.bench.build.common import read_jsonl, sha256_file, write_json
from far.eval.stats import paired_bootstrap_comparison
from far.experiments.diagnostic_release import verify_solo_release
from far.experiments.evaluate_fever_binary import verify_evaluation as verify_fever_binary
from far.experiments.evidence_family_dev import verify_release as verify_family_dev_release
from far.experiments.revision_trace_audit import verify_reports as verify_revision_trace_reports
from far.experiments.selective_acceptance import (
    ANALYSIS_PROFILE as SELECTIVE_ACCEPTANCE_PROFILE,
)
from far.experiments.selective_acceptance import (
    SCHEMA_VERSION as SELECTIVE_ACCEPTANCE_SCHEMA_VERSION,
)
from far.experiments.selective_acceptance import (
    _calibration_gate as selective_acceptance_calibration_gate,
)
from far.experiments.selective_acceptance import (
    _choose_policy as choose_selective_acceptance_policy,
)
from far.experiments.selective_acceptance import (
    _enrichment_bootstrap as selective_acceptance_bootstrap,
)
from far.experiments.selective_acceptance import (
    _policy_summary as selective_acceptance_policy_summary,
)
from far.experiments.selective_acceptance import (
    render_markdown as render_selective_acceptance_markdown,
)
from far.experiments.selective_revision_audit import (
    verify_reports as verify_selective_revision_reports,
)
from far.experiments.stage_trace_map import verify_reports as verify_stage_trace_map
from far.experiments.type_mappability_machine import (
    verify_report as verify_type_mappability_machine_report,
)
from far.paths import repository_root

SCHEMA_VERSION = "far-solo-paper-readiness-v6"
REQUIRED_PAPER_FRAGMENTS = (
    "machine-audited synthetic benchmark",
    "single-model development diagnostic",
    "\\input{../diagnostics/solo_v1/experiments/artifacts/main_results.tex}",
    "\\input{../diagnostics/solo_v1/experiments/artifacts/ablation_results.tex}",
    "0.078 (95\\% paired bootstrap [0.034, 0.124])",
    "Removing refutation queries does not reduce answer correctness",
    "Removing boundary queries is also neutral on answer correctness",
    "Removing typed revision increases answer correctness",
    "post-hoc revision-delta audit",
    "An unchanged erroneous answer receives zero",
    "raw delta F1 0.145",
    "raises raw delta F1 from 0.145 to 0.194",
    "CRAG-style and Vanilla obtain raw delta F1 values of 0.307 and 0.264",
    "Across the three frozen WS2 families, the post-hoc raw delta difference is positive in 3/3",
    "combined +0.0398 with a family-cluster 95\\% interval of [+0.0133,+0.0536]",
    "This was not a preregistered WS2 primary metric",
    "not semantic correctness",
    "post-hoc frozen revision-trace audit",
    "mean trace delta F1 0.082",
    "Only 15 of 60 traces",
    "19 are off-target and 12 make no lexical",
    "typed-minus-untyped trace delta is +0.048",
    "any-target-hit rate is lower by 0.033",
    "combined +0.0232 with a family-cluster interval",
    "revision traces frequently miss the construction target",
    "post-hoc selective-revision feasibility audit",
    "preserving the erroneous initial answer obtains mean whole-answer soft F1 0.978",
    "all 60 rows above the historical 0.8 threshold",
    "typed and generic revision obtain delta F1 0.145 and 0.072",
    "reference-dependent per-item arm envelope reaches 0.162",
    "only +0.016 over always typed",
    "confidence at least 0.90 selects 31 of 60",
    "conditional delta F1 0.139",
    "5/31 target-complete",
    "25/31 carry collateral edits",
    "does not evaluate a deployable selector",
    "preregistered reference-free post-generation acceptance study",
    "Calibration selected 15 of 60",
    "Evaluation accepted 18 of 60",
    "delta enrichment of +0.235",
    "95\\% category-stratified bootstrap interval of [+0.103,+0.386]",
    "does not save inference",
    "both obtain 0.72 accuracy",
    "post-hoc label-audit sensitivity",
    "machine-confirmed subset ($n=35$)",
    "machine-disputed subset ($n=25$)",
    "not human-validated gold",
    "not externally blind",
    "does not establish multi-model generality",
    "McNemar $p=1.0$",
    "Across eight methods and 350 upstream-labelled RAMDocs development items",
    "T1 passes for 8/8 methods",
    "cannot identify a cross-method detection bottleneck",
    "Registered clean RAMDocs ablations",
    "H3 remains \\texttt{uncertain}",
    "H5 is \\texttt{equivalent}",
    "15 of 217 items",
    "202 are contested",
    "cannot estimate population type mappability",
)
FORBIDDEN_PAPER_FRAGMENTS = (
    "PENDING-EMPIRICAL-RUN",
    "final performance claims are intentionally withheld",
)


def _csv_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["method"]: row for row in csv.DictReader(handle)}


def _metric(rows: dict[str, dict[str, str]], method: str, metric: str) -> float:
    return float(rows[method][metric])


def _stable_floats(value: Any) -> Any:
    """Normalize insignificant cross-Python float summation differences."""
    if isinstance(value, float):
        return round(value, 15)
    if isinstance(value, dict):
        return {key: _stable_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stable_floats(item) for item in value]
    return value


def _tracked_p5_evidence(root: Path) -> dict[str, Any]:
    """Audit the frozen tracked P5 report without claiming raw-output recomputation."""
    json_path = root / "reports/p5_ramdocs_ablations.json"
    markdown_path = root / "reports/p5_ramdocs_ablations.md"
    errors: list[str] = []
    checks: dict[str, bool] = {}
    result: dict[str, Any] = {}
    try:
        result = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")
        evaluations = result["evaluations"]
        h3 = result["hypotheses"]["H3"]
        h5 = result["hypotheses"]["H5"]
        checks = {
            "registered_dev_metadata": (
                result.get("schema_version") == "far-p5-ramdocs-ablations-v1"
                and result.get("samples") == 350
                and result.get("split") == "dev"
                and result.get("registered_enhancement") is True
                and result.get("model_calls_during_finalize") == 0
                and result.get("test_accessed") is False
                and result.get("publication_gold") is False
                and result.get("human_iaa") is False
            ),
            "frozen_exact_match_values": (
                math.isclose(
                    evaluations["full"]["metrics"]["ramdocs_exact_match"],
                    0.3057142857142857,
                )
                and math.isclose(
                    evaluations["minus_typed_revision_aggressive"]["metrics"][
                        "ramdocs_exact_match"
                    ],
                    0.30857142857142855,
                )
                and math.isclose(
                    evaluations["flat_claims"]["metrics"]["ramdocs_exact_match"],
                    0.3057142857142857,
                )
            ),
            "h3_uncertain": (
                h3["verdict"] == "uncertain"
                and h3["comparison"]["lower"] < -0.02
                and h3["comparison"]["upper"] < 0.02
            ),
            "h5_equivalent": (
                h5["verdict"] == "equivalent"
                and h5["comparison"]["lower"] >= -0.02
                and h5["comparison"]["upper"] <= 0.02
            ),
            "reader_report_discloses_boundaries": (
                "upstream-labelled" in markdown
                and "publication-grade human gold" in markdown
                and "`uncertain`" in markdown
                and "`equivalent`" in markdown
            ),
        }
        errors.extend(name for name, passed in checks.items() if not passed)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        "valid": not errors,
        "errors": errors,
        "checks": checks,
        "samples": result.get("samples"),
        "h3_verdict": result.get("hypotheses", {}).get("H3", {}).get("verdict"),
        "h5_verdict": result.get("hypotheses", {}).get("H5", {}).get("verdict"),
        "raw_outputs_recomputed_by_this_gate": False,
        "json_sha256": sha256_file(json_path) if json_path.is_file() else None,
        "markdown_sha256": sha256_file(markdown_path) if markdown_path.is_file() else None,
    }


def _p6m_evidence(root: Path) -> dict[str, Any]:
    report_root = root / "reports/type_mappability_machine"
    audit = verify_type_mappability_machine_report(
        root / "diagnostics/type_mappability_v1",
        [report_root / "jurors" / juror_id for juror_id in ("J1", "J2", "J3")],
        report_root,
    )
    errors = list(audit["errors"])
    result: dict[str, Any] = {}
    checks: dict[str, bool] = {}
    try:
        result = json.loads(
            (report_root / "type_mappability_machine.json").read_text(encoding="utf-8")
        )
        checks = {
            "negative_consensus_result": (
                result.get("samples") == 217
                and result.get("consensus_samples") == 15
                and result.get("dispositions") == {"unanimous": 1, "majority": 14, "contested": 202}
            ),
            "machine_only_boundary": (
                result.get("human_annotation_replaced") is False
                and result.get("human_iaa_computed") is False
                and result.get("human_identity_verified") is False
                and result.get("publication_gold") is False
                and result.get("confirmatory_h4") is False
                and result.get("test_accessed") is False
            ),
            "association_not_estimable": result.get("association", {}).get("estimable") is False,
        }
        errors.extend(name for name, passed in checks.items() if not passed)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        **audit,
        "valid": not errors,
        "errors": errors,
        "checks": checks,
        "samples": result.get("samples"),
        "consensus_samples": result.get("consensus_samples"),
        "dispositions": result.get("dispositions"),
        "association_estimable": result.get("association", {}).get("estimable"),
    }


def _family_revision_delta_evidence(root: Path) -> dict[str, Any]:
    release_root = root / "diagnostics/family_dev_v1"
    audit = verify_family_dev_release(release_root)
    errors = list(audit.get("errors", []))
    result: dict[str, Any] = {}
    checks: dict[str, bool] = {}
    try:
        result = json.loads((release_root / "result.json").read_text(encoding="utf-8"))
        delta = result["post_hoc_revision_delta"]
        raw = delta["raw"]
        typed = delta["typed"]
        checks = {
            "frozen_release_valid": audit.get("valid") is True,
            "post_hoc_boundary": (
                delta.get("metric_profile") == "falsirag-evaluation-metrics-v2-revision-delta"
                and delta.get("preregistered_primary") is False
                and delta.get("model_calls") == 0
                and delta.get("test_accessed") is False
            ),
            "raw_direction_recurs": (
                raw.get("positive_families") == 3
                and raw.get("combined_delta", 0.0) > 0.0
                and raw.get("family_cluster_bootstrap", {}).get("lower", 0.0) > 0.0
            ),
            "typed_direction_recurs": (
                typed.get("positive_families") == 3
                and typed.get("combined_delta", 0.0) > 0.0
                and typed.get("family_cluster_bootstrap", {}).get("lower", 0.0) > 0.0
            ),
        }
        errors.extend(name for name, passed in checks.items() if not passed)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        **audit,
        "valid": not errors,
        "errors": errors,
        "checks": checks,
        "post_hoc_revision_delta": result.get("post_hoc_revision_delta"),
    }


def _revision_trace_evidence(root: Path) -> dict[str, Any]:
    json_path = root / "reports/revision_trace_fidelity.json"
    markdown_path = root / "reports/revision_trace_fidelity.md"
    audit = verify_revision_trace_reports(
        benchmark_path=root / "bench/splits/dev.jsonl",
        solo_runs=root / "diagnostics/solo_v1/experiments/runs",
        family_runs=root / "diagnostics/family_dev_v1/runs",
        output_json=json_path,
        output_markdown=markdown_path,
    )
    errors = list(audit.get("errors", []))
    result: dict[str, Any] = {}
    checks: dict[str, bool] = {}
    try:
        result = json.loads(json_path.read_text(encoding="utf-8"))
        boundaries = result["boundaries"]
        qwen_far = result["qwen"]["methods"]["far"]["summary"]
        qwen_comparison = result["qwen"]["typed_minus_untyped"]
        trace_delta = qwen_comparison["trace_delta_f1"]
        trace_hit = qwen_comparison["trace_target_hit"]
        family_delta = result["family_sensitivity"]["trace_delta_f1"]
        checks = {
            "deterministic_report_valid": audit.get("valid") is True,
            "post_hoc_boundary": (
                result.get("analysis_profile") == "post-hoc-frozen-revision-trace-fidelity-v1"
                and boundaries.get("post_hoc") is True
                and boundaries.get("preregistered_primary") is False
                and boundaries.get("model_calls") == 0
                and boundaries.get("test_accessed") is False
                and boundaries.get("human_review") is False
                and boundaries.get("human_iaa") is False
                and boundaries.get("publication_gold") is False
                and boundaries.get("semantic_correctness") is False
                and boundaries.get("construction_reference_dependent") is True
                and boundaries.get("causal_attribution") is False
            ),
            "absolute_fidelity_bounded": (
                qwen_far.get("samples") == 60
                and qwen_far.get("mean_trace_delta_f1", 1.0) < 0.2
                and qwen_far.get("trace_bucket_counts", {}).get("exact_target") == 1
                and qwen_far.get("trace_bucket_counts", {}).get("complete_with_collateral") == 14
                and qwen_far.get("trace_bucket_counts", {}).get("off_target") == 19
                and qwen_far.get("trace_bucket_counts", {}).get("no_lexical_edit") == 12
            ),
            "typed_trace_direction_positive_but_hit_not_improved": (
                trace_delta.get("candidate_minus_baseline", 0.0) > 0.0
                and trace_delta.get("lower", 0.0) > 0.0
                and trace_hit.get("candidate_minus_baseline", 0.0) < 0.0
                and trace_hit.get("lower", 0.0) < 0.0 < trace_hit.get("upper", 0.0)
            ),
            "family_trace_direction_recurs": (
                family_delta.get("positive_families") == 3
                and family_delta.get("combined_delta", 0.0) > 0.0
                and family_delta.get("family_cluster_bootstrap", {}).get("lower", 0.0) > 0.0
            ),
        }
        errors.extend(name for name, passed in checks.items() if not passed)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        **audit,
        "valid": not errors,
        "errors": errors,
        "checks": checks,
        "analysis_profile": result.get("analysis_profile"),
        "boundaries": result.get("boundaries"),
        "qwen_far": result.get("qwen", {}).get("methods", {}).get("far", {}).get("summary"),
        "qwen_typed_minus_untyped": result.get("qwen", {}).get("typed_minus_untyped"),
        "family_trace_delta_f1": result.get("family_sensitivity", {}).get("trace_delta_f1"),
        "json_sha256": sha256_file(json_path) if json_path.is_file() else None,
        "markdown_sha256": sha256_file(markdown_path) if markdown_path.is_file() else None,
    }


def _selective_revision_evidence(root: Path) -> dict[str, Any]:
    json_path = root / "reports/selective_revision_feasibility.json"
    markdown_path = root / "reports/selective_revision_feasibility.md"
    audit = verify_selective_revision_reports(
        benchmark_path=root / "bench/splits/dev.jsonl",
        suite_manifest_path=root / "diagnostics/solo_v1/experiments/suite_manifest.json",
        runs_root=root / "diagnostics/solo_v1/experiments/runs",
        evaluations_root=root / "diagnostics/solo_v1/experiments/evaluations",
        trace_json_path=root / "reports/revision_trace_fidelity.json",
        trace_markdown_path=root / "reports/revision_trace_fidelity.md",
        output_json=json_path,
        output_markdown=markdown_path,
    )
    errors = list(audit.get("errors", []))
    result: dict[str, Any] = {}
    checks: dict[str, bool] = {}
    high_confidence: dict[str, Any] = {}
    try:
        result = json.loads(json_path.read_text(encoding="utf-8"))
        boundaries = result["boundaries"]
        arms = result["fixed_arms"]
        envelope = result["reference_arm_choice_envelope"]
        high_rows = [
            row for row in result["confidence_curves"]["preserve"] if row.get("threshold") == 0.9
        ]
        if len(high_rows) != 1:
            raise ValueError("selective revision report lacks the 0.90 confidence row")
        high_confidence = high_rows[0]
        checks = {
            "deterministic_report_valid": audit.get("valid") is True,
            "post_hoc_non_policy_boundary": (
                result.get("analysis_profile")
                == "post-hoc-frozen-selective-revision-feasibility-v1"
                and boundaries.get("post_hoc") is True
                and boundaries.get("preregistered_primary") is False
                and boundaries.get("reference_dependent") is True
                and boundaries.get("deployable_selector_evaluated") is False
                and boundaries.get("prospective_confidence_calibration") is False
                and boundaries.get("registered_policy_utility") is False
                and boundaries.get("counterfactual_policy_effect") is False
                and boundaries.get("semantic_correctness") is False
                and boundaries.get("independent_arm_runs") is True
                and boundaries.get("preserve_output_generated") is False
                and boundaries.get("model_calls") == 0
                and boundaries.get("test_accessed") is False
                and boundaries.get("human_review") is False
                and boundaries.get("human_iaa") is False
                and boundaries.get("publication_gold") is False
            ),
            "whole_answer_gate_invalidated": (
                arms["preserve"]["samples"] == 60
                and arms["preserve"]["answer_soft_f1_ge_0_8"] == 60
                and arms["preserve"]["mean_answer_soft_f1"] > 0.97
                and arms["preserve"]["mean_revision_delta_f1"] == 0.0
            ),
            "selection_headroom_bounded": (
                envelope.get("reference_dependent") is True
                and envelope.get("deployable") is False
                and 0.0 < envelope.get("gain_over_always_typed", 1.0) < 0.02
                and envelope.get("mean_per_item_max", 0.0) > arms["typed"]["mean_revision_delta_f1"]
            ),
            "confidence_not_fidelity_selector": (
                high_confidence.get("selected_rows") == 31
                and high_confidence.get("selected_mean_typed_revision_delta_f1", 1.0)
                < arms["typed"]["mean_revision_delta_f1"]
                and high_confidence.get("selected_trace_target_complete_rate") == 5 / 31
                and high_confidence.get("selected_trace_collateral_rate") == 25 / 31
            ),
        }
        errors.extend(name for name, passed in checks.items() if not passed)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        **audit,
        "valid": not errors,
        "errors": errors,
        "checks": checks,
        "analysis_profile": result.get("analysis_profile"),
        "boundaries": result.get("boundaries"),
        "fixed_arms": result.get("fixed_arms"),
        "reference_arm_choice_envelope": result.get("reference_arm_choice_envelope"),
        "confidence_threshold_0_90": high_confidence,
        "json_sha256": sha256_file(json_path) if json_path.is_file() else None,
        "markdown_sha256": sha256_file(markdown_path) if markdown_path.is_file() else None,
    }


def _tracked_selective_acceptance_evidence(root: Path) -> dict[str, Any]:
    """Recompute P14 row summaries from tracked reports without requiring raw runs."""
    json_path = root / "reports/selective_acceptance.json"
    markdown_path = root / "reports/selective_acceptance.md"
    errors: list[str] = []
    checks: dict[str, bool] = {}
    result: dict[str, Any] = {}
    selected: dict[str, Any] | None = None
    evaluation_summary: dict[str, Any] = {}
    bootstrap: dict[str, Any] = {}
    try:
        result = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")
        calibration = result["calibration"]
        evaluation = result["evaluation"]
        calibration_rows = calibration["rows"]
        evaluation_rows = evaluation["rows"]
        selected, candidate_count = choose_selective_acceptance_policy(calibration_rows)
        if selected is None:
            raise ValueError("tracked P14 report has no eligible calibration policy")
        calibration_checks = selective_acceptance_calibration_gate(selected)
        evaluation_summary = selective_acceptance_policy_summary(
            evaluation_rows, selected["policy"]
        )
        bootstrap = selective_acceptance_bootstrap(evaluation_rows, selected["policy"])
        evaluation_checks = {
            "coverage_registered": 0.25 <= float(evaluation_summary["coverage"]) <= 0.75,
            "delta_enrichment_at_least_0_03": (
                float(evaluation_summary["selected_delta_enrichment"]) >= 0.03
            ),
            "enrichment_interval_lower_positive": float(bootstrap["lower"]) > 0.0,
            "collateral_not_worse": (
                float(evaluation_summary["selected_collateral_rate"])
                <= float(evaluation_summary["always_typed_collateral_rate"])
            ),
            "target_complete_not_worse": (
                float(evaluation_summary["selected_target_complete_rate"])
                >= float(evaluation_summary["always_typed_target_complete_rate"])
            ),
        }
        protocol = result["protocol"]
        run = result["run"]
        boundaries = result["boundaries"]
        calibration_ids = {str(row["sample_id"]) for row in calibration_rows}
        evaluation_ids = {str(row["sample_id"]) for row in evaluation_rows}
        expected_categories = {
            "causal_overclaim",
            "entity_confusion",
            "multi_source_conflict",
            "numerical_conflict",
            "temporal_shift",
        }
        checks = {
            "tracked_report_shape": (
                result.get("schema_version") == SELECTIVE_ACCEPTANCE_SCHEMA_VERSION
                and result.get("analysis_profile") == SELECTIVE_ACCEPTANCE_PROFILE
                and result.get("valid") is True
                and result.get("registered_outcome") == "evaluation_success"
                and result.get("candidate_grid")
                == {
                    "candidate_count": 100,
                    "confidence_min": [0.0, 0.75, 0.8, 0.85, 0.9],
                    "coverage_bounds": [0.25, 0.75],
                    "max_edit_fraction": [0.2, 0.35, 0.5, 1.0, 2.0],
                    "min_trace_consistency_margin": [-1.0, 0.0, 0.1, 0.25],
                    "minimum_enrichment": 0.03,
                }
                and set(result)
                == {
                    "analysis_profile",
                    "boundaries",
                    "calibration",
                    "candidate_grid",
                    "evaluation",
                    "packet_manifest_sha256",
                    "protocol",
                    "registered_outcome",
                    "run",
                    "schema_version",
                    "valid",
                }
            ),
            "fresh_group_disjoint_120_rows": (
                calibration.get("samples") == 60
                and len(calibration_rows) == 60
                and len(calibration_ids) == 60
                and len(evaluation_rows) == 60
                and len(evaluation_ids) == 60
                and calibration_ids.isdisjoint(evaluation_ids)
                and {str(row["category"]) for row in calibration_rows + evaluation_rows}
                == expected_categories
                and all(
                    sum(str(row["category"]) == category for row in rows) == 12
                    for rows in (calibration_rows, evaluation_rows)
                    for category in expected_categories
                )
            ),
            "calibration_policy_recomputed": (
                candidate_count == 100
                and _stable_floats(selected) == _stable_floats(calibration.get("selected_policy"))
                and calibration_checks == calibration.get("gate_checks")
                and calibration.get("gate_passed") is True
                and all(calibration_checks.values())
            ),
            "evaluation_policy_recomputed": (
                evaluation.get("scored") is True
                and _stable_floats(evaluation_summary) == _stable_floats(evaluation.get("summary"))
                and _stable_floats(bootstrap)
                == _stable_floats(evaluation.get("enrichment_bootstrap"))
                and evaluation_checks == evaluation.get("success_checks")
                and evaluation.get("success") is True
                and all(evaluation_checks.values())
            ),
            "registered_remote_protocol": (
                protocol.get("schema_version") == "far-selective-acceptance-protocol-audit-v2"
                and protocol.get("valid") is True
                and protocol.get("errors") == []
                and protocol.get("preregistration_tag") == "prereg-selective-acceptance-v2"
                and protocol.get("preregistration_commit")
                == "04b60a75960d24f911bef4889e2639e238457ccd"
                and protocol.get("retired_preregistration_tag") == "prereg-selective-acceptance-v1"
                and protocol.get("retired_v1_complete_checkpoint_rows") == 10
                and protocol.get("retired_v1_rows_reused") == 0
                and protocol.get("fresh_restart_after_retired_v1") is True
                and protocol.get("fresh_cache_namespace")
                == "far-qwen3.5-9b-selective-acceptance-v2"
                and protocol.get("model") == "qwen3.5:9b"
                and protocol.get("model_digest")
                == "6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7"
                and protocol.get("keep_alive") == "24h"
                and protocol.get("unload_after_sample") is False
                and protocol.get("performance_amendment") is True
                and protocol.get("model_execution_location") == "windows-gpu"
                and protocol.get("local_model_execution") is False
                and protocol.get("test_accessed") is False
                and protocol.get("human_review") is False
                and protocol.get("publication_gold") is False
                and protocol.get("semantic_correctness") is False
                and protocol.get("dependency_group_disjoint") is True
                and protocol.get("reference_free_operational_input") is True
                and protocol.get("post_generation_policy") is True
            ),
            "bound_complete_run_identity": (
                run.get("source_revision")
                == {
                    "git_commit": "04b60a75960d24f911bef4889e2639e238457ccd",
                    "git_dirty": False,
                }
                and run.get("checkpoint_sha256")
                == "7a11d24a737efe481aab669fa934465d405182b873ff4a92526a571287a05d28"
                and run.get("predictions_sha256") == run.get("checkpoint_sha256")
                and run.get("manifest_sha256")
                == "3dec06783d34c807cb68561201e467e75bfbad34369a30915d9e8e6a9f301147"
                and run.get("identity_sha256")
                == "2fea46cddac7b5d4768a1c0d8ac9bfdd8583b7ca7b61fdc06b971002f5ed5dc5"
                and run.get("implementation_sha256")
                == "2d6094bf0ffc1c2a1b71a3843d5ca0f246e7d622b147dc1e59cdf6009d0a86b2"
                and result.get("packet_manifest_sha256")
                == "a2546f37978aa446f23bada5230b7e9ddddb95959602f5723b7c411bbee88f26"
                and isinstance(run.get("checks"), dict)
                and set(run["checks"])
                == {
                    "checkpoint_matches_predictions",
                    "clean_preregistered_source",
                    "complete_120",
                    "config_hash_bound",
                    "corpus_hash_bound",
                    "method_far",
                    "model_digest_bound",
                    "no_limit",
                    "packet_hash_bound",
                    "packet_valid",
                    "prediction_coverage",
                    "prediction_hash_bound",
                    "train_only",
                    "v2_cache_isolated",
                    "v2_model_lifecycle_bound",
                }
                and all(run["checks"].values())
            ),
            "claim_boundaries_preserved": boundaries
            == {
                "causal_policy_effect": False,
                "dependency_group_disjoint": True,
                "deterministic_preserve_fallback": True,
                "exact_internal_llm_calls_claimed": False,
                "external_validation": False,
                "fresh_v2_run_required": True,
                "human_iaa": False,
                "human_review": False,
                "local_model_execution": False,
                "model_execution_location": "windows-gpu",
                "new_inference": True,
                "performance_amendment": True,
                "pipeline_sample_executions": 120,
                "post_generation_acceptance": True,
                "pre_execution_selector": False,
                "preregistered": True,
                "publication_gold": False,
                "reference_free_policy_features": True,
                "retired_v1_rows_reused": 0,
                "same_corpus_and_construction_process": True,
                "semantic_correctness": False,
                "test_accessed": False,
            },
            "reader_report_matches_json": markdown == render_selective_acceptance_markdown(result),
        }
        errors.extend(name for name, passed in checks.items() if not passed)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "far-selective-acceptance-tracked-report-audit-v1",
        "valid": not errors,
        "errors": errors,
        "checks": checks,
        "registered_outcome": result.get("registered_outcome"),
        "calibration_selected_policy": selected,
        "evaluation_summary": evaluation_summary,
        "enrichment_bootstrap": bootstrap,
        "protocol": result.get("protocol"),
        "run": result.get("run"),
        "boundaries": result.get("boundaries"),
        "report_rows_recomputed": True,
        "raw_outputs_recomputed_by_this_gate": False,
        "json_sha256": sha256_file(json_path) if json_path.is_file() else None,
        "markdown_sha256": sha256_file(markdown_path) if markdown_path.is_file() else None,
    }


def _label_sensitivity(root: Path) -> dict[str, Any]:
    consensus_rows = read_jsonl(
        root / "diagnostics/solo_v1/machine_annotation/machine_consensus_rows.jsonl"
    )
    dispositions = {str(row["sample_id"]): str(row["disposition"]) for row in consensus_rows}
    evaluation_root = root / "diagnostics/solo_v1/experiments/evaluations"
    far_rows = read_jsonl(evaluation_root / "far/scores.jsonl")
    untyped_rows = read_jsonl(evaluation_root / "minus_typed_conflict/scores.jsonl")
    result: dict[str, Any] = {}
    for disposition in ("machine_confirmed", "machine_disputed"):
        sample_ids = {
            sample_id for sample_id, observed in dispositions.items() if observed == disposition
        }
        far_subset = [row for row in far_rows if str(row["sample_id"]) in sample_ids]
        untyped_subset = [row for row in untyped_rows if str(row["sample_id"]) in sample_ids]
        categories: dict[str, int] = {}
        for row in far_subset:
            category = str(row["category"])
            categories[category] = categories.get(category, 0) + 1
        result[disposition] = _stable_floats(
            {
                "samples": len(far_subset),
                "categories": dict(sorted(categories.items())),
                "answer_correctness": paired_bootstrap_comparison(
                    untyped_subset, far_subset, "answer_correctness"
                ),
                "revision_accuracy": paired_bootstrap_comparison(
                    untyped_subset, far_subset, "revision_accuracy"
                ),
                "typed_conflict_correct": paired_bootstrap_comparison(
                    untyped_subset, far_subset, "typed_conflict_correct"
                ),
            }
        )
    return result


def audit_claim_scope(root: Path, paper_text: str) -> dict[str, Any]:
    artifact_dir = root / "diagnostics/solo_v1/experiments/artifacts"
    main = _csv_rows(artifact_dir / "main_results.csv")
    ablations = _csv_rows(artifact_dir / "ablation_results.csv")
    far_answer = _metric(ablations, "far", "answer_correctness")
    untyped_answer = _metric(ablations, "minus_typed_conflict", "answer_correctness")
    far_typed_f1 = _metric(ablations, "far", "typed_conflict_f1")
    untyped_typed_f1 = _metric(ablations, "minus_typed_conflict", "typed_conflict_f1")
    far_revision = _metric(ablations, "far", "revision_accuracy")
    untyped_revision = _metric(ablations, "minus_typed_conflict", "revision_accuracy")
    far_delta = _metric(ablations, "far", "revision_delta_f1")
    untyped_delta = _metric(ablations, "minus_typed_conflict", "revision_delta_f1")
    far_typed_delta = _metric(ablations, "far", "typed_revision_delta_f1")
    untyped_typed_delta = _metric(ablations, "minus_typed_conflict", "typed_revision_delta_f1")
    label_sensitivity = _label_sensitivity(root)
    checks = {
        "typed_answer_advantage": far_answer > untyped_answer,
        "typed_conflict_f1_advantage": far_typed_f1 > untyped_typed_f1,
        "typed_revision_accuracy_advantage": far_revision > untyped_revision,
        "typed_conflict_revision_delta_advantage": far_delta > untyped_delta,
        "typed_conflict_typed_delta_advantage": far_typed_delta > untyped_typed_delta,
        "typed_revision_delta_advantage": far_delta
        > _metric(ablations, "minus_typed_revision", "revision_delta_f1"),
        "raw_baseline_delta_exceeds_far": max(
            _metric(main, method, "revision_delta_f1") for method in main if method != "far"
        )
        > far_delta,
        "refutation_ablation_delta_exceeds_far": _metric(
            ablations, "minus_refutation_query", "revision_delta_f1"
        )
        > far_delta,
        "refutation_ablation_not_positive": _metric(
            ablations, "minus_refutation_query", "answer_correctness"
        )
        >= far_answer,
        "boundary_ablation_not_positive": _metric(
            ablations, "minus_boundary_query", "answer_correctness"
        )
        >= far_answer,
        "typed_revision_answer_tradeoff": _metric(
            ablations, "minus_typed_revision", "answer_correctness"
        )
        > far_answer
        and _metric(ablations, "minus_typed_revision", "revision_accuracy") == 0.0,
        "far_exceeds_all_six_baselines_on_answer": _metric(main, "far", "answer_correctness")
        > max(_metric(main, method, "answer_correctness") for method in main if method != "far"),
        "typed_answer_advantage_same_direction_by_machine_disposition": all(
            group["answer_correctness"]["candidate_minus_baseline"] > 0
            for group in label_sensitivity.values()
        ),
    }
    missing_fragments = [
        fragment for fragment in REQUIRED_PAPER_FRAGMENTS if fragment not in paper_text
    ]
    forbidden_present = [
        fragment for fragment in FORBIDDEN_PAPER_FRAGMENTS if fragment in paper_text
    ]
    valid = all(checks.values()) and not missing_fragments and not forbidden_present
    return {
        "valid": valid,
        "checks": checks,
        "missing_required_disclosures": missing_fragments,
        "forbidden_stale_claims": forbidden_present,
        "observed": {
            "far_answer_correctness": far_answer,
            "typed_minus_untyped_answer_correctness": far_answer - untyped_answer,
            "typed_minus_untyped_conflict_f1": far_typed_f1 - untyped_typed_f1,
            "typed_minus_untyped_revision_accuracy": far_revision - untyped_revision,
            "far_revision_delta_f1": far_delta,
            "far_typed_revision_delta_f1": far_typed_delta,
            "typed_minus_untyped_revision_delta_f1": far_delta - untyped_delta,
            "typed_minus_untyped_typed_revision_delta_f1": (far_typed_delta - untyped_typed_delta),
            "best_baseline_revision_delta_f1": max(
                _metric(main, method, "revision_delta_f1") for method in main if method != "far"
            ),
            "minus_refutation_revision_delta_f1": _metric(
                ablations, "minus_refutation_query", "revision_delta_f1"
            ),
            "minus_typed_revision_revision_delta_f1": _metric(
                ablations, "minus_typed_revision", "revision_delta_f1"
            ),
            "minus_refutation_answer_correctness": _metric(
                ablations, "minus_refutation_query", "answer_correctness"
            ),
            "minus_boundary_answer_correctness": _metric(
                ablations, "minus_boundary_query", "answer_correctness"
            ),
            "minus_typed_revision_answer_correctness": _metric(
                ablations, "minus_typed_revision", "answer_correctness"
            ),
            "minus_typed_revision_revision_accuracy": _metric(
                ablations, "minus_typed_revision", "revision_accuracy"
            ),
        },
        "label_sensitivity": label_sensitivity,
    }


def audit(root: Path, *, paper_path: Path | None = None) -> dict[str, Any]:
    paper = paper_path or root / "paper/main.tex"
    paper_text = paper.read_text(encoding="utf-8")
    solo = verify_solo_release(root / "diagnostics/solo_v1")
    fever = verify_fever_binary(
        root / "bench/external/fever_pair_candidates_v1",
        root / "diagnostics/fever_binary_v1",
    )
    stage_trace = verify_stage_trace_map(
        ramdocs_data_dir=root / "bench/external/ramdocs_v1",
        round1_dir=root / "diagnostics/ramdocs_v2/round1",
        output_json=root / "reports/stage_trace_map.json",
        output_report=root / "reports/stage_trace_map.md",
    )
    p5 = _tracked_p5_evidence(root)
    p6m = _p6m_evidence(root)
    family_delta = _family_revision_delta_evidence(root)
    revision_trace = _revision_trace_evidence(root)
    selective_revision = _selective_revision_evidence(root)
    selective_acceptance = _tracked_selective_acceptance_evidence(root)
    claim_scope = audit_claim_scope(root, paper_text)
    gates = {
        "tracked_solo_evidence": bool(solo.get("valid")),
        "claim_scope_matches_observed_ablations": bool(claim_scope["valid"]),
        "frozen_fever_negative_transfer_disclosed": bool(fever.get("valid")),
        "tracked_stage_trace_map": bool(stage_trace.get("valid")),
        "tracked_registered_p5_report": bool(p5.get("valid")),
        "verified_p6m_negative_stability_audit": bool(p6m.get("valid")),
        "verified_post_hoc_family_revision_delta": bool(family_delta.get("valid")),
        "verified_post_hoc_revision_trace_fidelity": bool(revision_trace.get("valid")),
        "verified_post_hoc_selective_revision_feasibility": bool(selective_revision.get("valid")),
        "verified_preregistered_selective_acceptance": bool(selective_acceptance.get("valid")),
    }
    ready = all(gates.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "study_profile": "single_author_machine_audited_paper",
        "ready": ready,
        "strict_aaai_submission_ready": False,
        "gates": gates,
        "claim_scope": claim_scope,
        "evidence": {
            "solo_release": solo,
            "fever_binary": fever,
            "stage_trace_map": stage_trace,
            "p5_registered_ablations": p5,
            "p6m_machine_ontology_stability": p6m,
            "family_revision_delta_sensitivity": family_delta,
            "revision_trace_fidelity": revision_trace,
            "selective_revision_feasibility": selective_revision,
            "selective_acceptance": selective_acceptance,
            "paper_main_sha256": sha256_file(paper),
            "paper_appendix_sha256": sha256_file(root / "paper/appendix.tex"),
            "paper_supplement_sha256": sha256_file(root / "paper/supplement.tex"),
            "paper_checklist_sha256": sha256_file(
                root / "paper/aaai27/ReproducibilityChecklist.tex"
            ),
        },
        "allowed_claim": (
            "Across eight RAMDocs development methods, errors concentrate after retrieved "
            "evidence and answer transformation; FAR shows a narrower machine-audited typed-"
            "control signal whose transport and ontology stability are explicitly bounded. "
            "A preregistered reference-free post-generation policy also enriched typed "
            "revision-delta on fresh machine-seeded train evidence under explicit "
            "non-semantic and non-deployment boundaries."
        ),
        "required_limitations": [
            "labels are not human-validated gold",
            "evaluation is not externally blind",
            "the broad baseline delta ranking is Qwen-only and does not establish "
            "multi-model generality",
            "refutation and boundary query ablations do not support positive marginal claims",
            "typed revision trades lower answer correctness for non-zero revision behavior",
            "revision-delta metrics are post-hoc lexical diagnostics, not semantic correctness",
            "revision traces frequently miss the construction target or add collateral edits",
            "selective revision feasibility is post-hoc and does not evaluate a "
            "deployable selector",
            "P14 selective acceptance is post-generation, uses construction-derived lexical "
            "outcomes, and does not save inference",
            "P14 calibration and evaluation share one machine-seeded train corpus and are "
            "neither external nor test evidence",
            "raw baseline revision delta exceeds FAR despite zero typed action-conditioned delta",
            "FEVER binary transfer shows no paired accuracy gain",
            "machine-disposition sensitivity is post-hoc and not independent label validation",
            "cross-method trace attribution does not identify detection or action causal gaps",
            "P5 uses upstream-labelled development evidence and H3 remains uncertain",
            "P6-M is machine-panel sensitivity, not population type mappability",
            "the strict human P6 analysis was not completed",
        ],
        "forbidden_claims": [
            "human inter-annotator agreement",
            "human adjudication",
            "externally held blind test",
            "publication-grade benchmark gold",
            "positive marginal contribution from every FAR component",
            "multi-model or external-domain generality",
            "H3 equivalence or H4 confirmation",
            "P6-M as human review, human adjudication, or human IAA",
            "population mappability estimated from the 15 machine-consensus rows",
            "P14 as semantic correctness, deployment safety, inference savings, or causal "
            "policy effect",
            "held-out or test validation from the P14 train-only split",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    observed = report["claim_scope"]["observed"]
    gates = report["gates"]
    limitations = "\n".join(f"- {item}" for item in report["required_limitations"])
    forbidden = "\n".join(f"- {item}" for item in report["forbidden_claims"])
    ready = str(report["ready"]).lower()
    strict_ready = str(report["strict_aaai_submission_ready"]).lower()
    solo_evidence = str(gates["tracked_solo_evidence"]).lower()
    claim_scope = str(gates["claim_scope_matches_observed_ablations"]).lower()
    fever = str(gates["frozen_fever_negative_transfer_disclosed"]).lower()
    stage_trace = str(gates["tracked_stage_trace_map"]).lower()
    p5 = str(gates["tracked_registered_p5_report"]).lower()
    p6m = str(gates["verified_p6m_negative_stability_audit"]).lower()
    family_delta_gate = str(gates["verified_post_hoc_family_revision_delta"]).lower()
    revision_trace_gate = str(gates["verified_post_hoc_revision_trace_fidelity"]).lower()
    selective_revision_gate = str(gates["verified_post_hoc_selective_revision_feasibility"]).lower()
    selective_acceptance_gate = str(gates["verified_preregistered_selective_acceptance"]).lower()
    far_answer = observed["far_answer_correctness"]
    answer_delta = observed["typed_minus_untyped_answer_correctness"]
    f1_delta = observed["typed_minus_untyped_conflict_f1"]
    revision_delta = observed["typed_minus_untyped_revision_accuracy"]
    edit_delta = observed["far_revision_delta_f1"]
    typed_edit_delta = observed["far_typed_revision_delta_f1"]
    edit_advantage = observed["typed_minus_untyped_revision_delta_f1"]
    sensitivity = report["claim_scope"]["label_sensitivity"]
    confirmed = sensitivity["machine_confirmed"]["answer_correctness"]
    disputed = sensitivity["machine_disputed"]["answer_correctness"]
    family_delta = report["evidence"]["family_revision_delta_sensitivity"][
        "post_hoc_revision_delta"
    ]
    trace_evidence = report["evidence"]["revision_trace_fidelity"]
    trace_summary = trace_evidence["qwen_far"]
    trace_comparison = trace_evidence["qwen_typed_minus_untyped"]["trace_delta_f1"]
    selective = report["evidence"]["selective_revision_feasibility"]
    selective_arms = selective["fixed_arms"]
    selective_envelope = selective["reference_arm_choice_envelope"]
    selective_high = selective["confidence_threshold_0_90"]
    selective_high_complete = selective_high["selected_trace_target_complete_rate"]
    acceptance = report["evidence"]["selective_acceptance"]
    acceptance_calibration = acceptance["calibration_selected_policy"]
    acceptance_evaluation = acceptance["evaluation_summary"]
    acceptance_bootstrap = acceptance["enrichment_bootstrap"]
    acceptance_enrichment = acceptance_evaluation["selected_delta_enrichment"]
    acceptance_lower = acceptance_bootstrap["lower"]
    acceptance_upper = acceptance_bootstrap["upper"]
    return f"""# Single-Author Machine-Audited Paper Readiness

This report audits the explicitly relaxed paper profile. It does not certify
strict AAAI submission readiness, human gold, external blindness, or
multi-model generality.

| Item | Status |
|---|---|
| Relaxed machine-audited paper profile | `{ready}` |
| Strict AAAI submission | `{strict_ready}` |
| Tracked solo evidence | `{solo_evidence}` |
| Paper claim scope matches ablations | `{claim_scope}` |
| FEVER negative transfer disclosed | `{fever}` |
| Tracked stage trace map | `{stage_trace}` |
| Tracked registered P5 report | `{p5}` |
| Verified P6-M negative stability audit | `{p6m}` |
| Verified post-hoc family revision-delta sensitivity | `{family_delta_gate}` |
| Verified post-hoc revision-trace fidelity audit | `{revision_trace_gate}` |
| Verified post-hoc selective-revision feasibility audit | `{selective_revision_gate}` |
| Verified preregistered selective-acceptance study | `{selective_acceptance_gate}` |

## Narrow supported claim

{report["allowed_claim"]}

- FAR answer correctness: `{far_answer:.3f}`
- Typed minus untyped answer correctness: `{answer_delta:+.3f}`
- Typed minus untyped conflict F1: `{f1_delta:+.3f}`
- Typed minus untyped revision accuracy: `{revision_delta:+.3f}`
- FAR post-hoc revision delta F1: `{edit_delta:.3f}`
- FAR post-hoc typed revision delta F1: `{typed_edit_delta:.3f}`
- Typed minus untyped revision delta F1: `{edit_advantage:+.3f}`
- Three-family post-hoc raw delta difference: `{family_delta["raw"]["combined_delta"]:+.4f}`
- Three-family post-hoc typed delta difference: `{family_delta["typed"]["combined_delta"]:+.4f}`
- Qwen FAR post-hoc mean trace delta F1: `{trace_summary["mean_trace_delta_f1"]:.4f}`
- Qwen typed minus untyped trace delta F1: `{trace_comparison["candidate_minus_baseline"]:+.4f}`
- Preserved initial-answer soft F1: `{selective_arms["preserve"]["mean_answer_soft_f1"]:.4f}`
- Reference-dependent delta-F1 arm envelope: `{selective_envelope["mean_per_item_max"]:.4f}`
- Envelope gain over always typed: `{selective_envelope["gain_over_always_typed"]:+.4f}`
- Confidence >=0.90 selected trace-complete rate: `{selective_high_complete:.4f}`
- P14 calibration coverage: `{acceptance_calibration["coverage"]:.4f}`
- P14 evaluation coverage: `{acceptance_evaluation["coverage"]:.4f}`
- P14 evaluation selected delta enrichment: `{acceptance_enrichment:+.4f}`
- P14 enrichment 95% interval: `[{acceptance_lower:+.4f}, {acceptance_upper:+.4f}]`
- Machine-confirmed answer delta (`n=35`): `{confirmed["candidate_minus_baseline"]:+.3f}`
- Machine-disputed answer delta (`n=25`): `{disputed["candidate_minus_baseline"]:+.3f}`

## Required limitations

{limitations}

## Forbidden claims

{forbidden}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=repository_root())
    parser.add_argument("--paper", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    report = audit(root, paper_path=args.paper)
    if args.output:
        write_json(args.output, report)
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if not report["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
