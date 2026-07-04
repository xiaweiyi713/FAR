"""Audit the relaxed, transparent single-author machine-audited paper profile."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json
from eval.stats import paired_bootstrap_comparison
from experiments.diagnostic_release import verify_solo_release
from experiments.evaluate_fever_binary import verify_evaluation as verify_fever_binary

SCHEMA_VERSION = "far-solo-paper-readiness-v1"
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
    claim_scope = audit_claim_scope(root, paper_text)
    gates = {
        "tracked_solo_evidence": bool(solo.get("valid")),
        "claim_scope_matches_observed_ablations": bool(claim_scope["valid"]),
        "frozen_fever_negative_transfer_disclosed": bool(fever.get("valid")),
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
            "paper_main_sha256": sha256_file(paper),
            "paper_supplement_sha256": sha256_file(root / "paper/supplement.tex"),
            "paper_checklist_sha256": sha256_file(
                root / "paper/aaai27/ReproducibilityChecklist.tex"
            ),
        },
        "allowed_claim": (
            "On a construction-derived, machine-audited 60-item Qwen development diagnostic, "
            "typed conflict control improves over its untyped ablation."
        ),
        "required_limitations": [
            "labels are not human-validated gold",
            "evaluation is not externally blind",
            "one local model does not establish multi-model generality",
            "refutation and boundary query ablations do not support positive marginal claims",
            "typed revision trades lower answer correctness for non-zero revision behavior",
            "FEVER binary transfer shows no paired accuracy gain",
            "machine-disposition sensitivity is post-hoc and not independent label validation",
        ],
        "forbidden_claims": [
            "human inter-annotator agreement",
            "human adjudication",
            "externally held blind test",
            "publication-grade benchmark gold",
            "positive marginal contribution from every FAR component",
            "multi-model or external-domain generality",
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
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
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
