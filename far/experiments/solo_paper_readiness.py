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
from far.experiments.stage_trace_map import verify_reports as verify_stage_trace_map
from far.experiments.type_mappability_machine import (
    verify_report as verify_type_mappability_machine_report,
)
from far.paths import repository_root

SCHEMA_VERSION = "far-solo-paper-readiness-v2"
REQUIRED_PAPER_FRAGMENTS = (
    "machine-audited synthetic benchmark",
    "single-model development diagnostic",
    "\\input{../diagnostics/solo_v1/experiments/artifacts/main_results.tex}",
    "\\input{../diagnostics/solo_v1/experiments/artifacts/ablation_results.tex}",
    "0.078 (95\\% paired bootstrap [0.034, 0.124])",
    "Removing refutation queries does not reduce answer correctness",
    "Removing boundary queries is also neutral on answer correctness",
    "Removing typed revision increases answer correctness",
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
                and result.get("dispositions")
                == {"unanimous": 1, "majority": 14, "contested": 202}
            ),
            "machine_only_boundary": (
                result.get("human_annotation_replaced") is False
                and result.get("human_iaa_computed") is False
                and result.get("human_identity_verified") is False
                and result.get("publication_gold") is False
                and result.get("confirmatory_h4") is False
                and result.get("test_accessed") is False
            ),
            "association_not_estimable": result.get("association", {}).get("estimable")
            is False,
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
    label_sensitivity = _label_sensitivity(root)
    checks = {
        "typed_answer_advantage": far_answer > untyped_answer,
        "typed_conflict_f1_advantage": far_typed_f1 > untyped_typed_f1,
        "typed_revision_accuracy_advantage": far_revision > untyped_revision,
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
    claim_scope = audit_claim_scope(root, paper_text)
    gates = {
        "tracked_solo_evidence": bool(solo.get("valid")),
        "claim_scope_matches_observed_ablations": bool(claim_scope["valid"]),
        "frozen_fever_negative_transfer_disclosed": bool(fever.get("valid")),
        "tracked_stage_trace_map": bool(stage_trace.get("valid")),
        "tracked_registered_p5_report": bool(p5.get("valid")),
        "verified_p6m_negative_stability_audit": bool(p6m.get("valid")),
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
            "control signal whose transport and ontology stability are explicitly bounded."
        ),
        "required_limitations": [
            "labels are not human-validated gold",
            "evaluation is not externally blind",
            "one local model does not establish multi-model generality",
            "refutation and boundary query ablations do not support positive marginal claims",
            "typed revision trades lower answer correctness for non-zero revision behavior",
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
    far_answer = observed["far_answer_correctness"]
    answer_delta = observed["typed_minus_untyped_answer_correctness"]
    f1_delta = observed["typed_minus_untyped_conflict_f1"]
    revision_delta = observed["typed_minus_untyped_revision_accuracy"]
    sensitivity = report["claim_scope"]["label_sensitivity"]
    confirmed = sensitivity["machine_confirmed"]["answer_correctness"]
    disputed = sensitivity["machine_disputed"]["answer_correctness"]
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

## Narrow supported claim

{report["allowed_claim"]}

- FAR answer correctness: `{far_answer:.3f}`
- Typed minus untyped answer correctness: `{answer_delta:+.3f}`
- Typed minus untyped conflict F1: `{f1_delta:+.3f}`
- Typed minus untyped revision accuracy: `{revision_delta:+.3f}`
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
