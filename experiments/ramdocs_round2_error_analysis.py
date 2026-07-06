"""Build the deterministic dev error analysis for a failed RAMDocs Round 2."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256, verify_active_protocol
from experiments.ramdocs_error_analysis import (
    _by_id,
    _group_summary,
    _outcome,
    _prediction_summary,
    _write_markdown,
)
from experiments.ramdocs_round2 import verify_round


def build_analysis(
    data_dir: Path,
    round1_dir: Path,
    round2_dir: Path,
    config_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    verify_active_protocol()
    audit = verify_round(data_dir, round1_dir, round2_dir, config_path)
    if audit.get("valid") is not True:
        raise ValueError(f"RAMDocs Round 2 is invalid: {audit.get('errors', [])}")
    decision = json.loads((round2_dir / "round_manifest.json").read_text(encoding="utf-8"))
    if (
        decision.get("gate_a_passed") is not False
        or decision.get("stop_rule_triggered") is not True
    ):
        raise ValueError("Round 2 error analysis is only valid after a failed G-A stop decision")
    baseline_method = str(decision["reused_round1_artifacts"]["baseline_method"])

    tasks = _by_id(
        [row for row in read_jsonl(data_dir / "tasks.jsonl") if row.get("split") == "dev"],
        "id",
    )
    far_scores_path = round2_dir / "evaluations/far/scores.jsonl"
    baseline_scores_path = round1_dir / f"evaluations/{baseline_method}/scores.jsonl"
    far_predictions_path = round2_dir / "runs/far/predictions.jsonl"
    baseline_predictions_path = round1_dir / f"runs/{baseline_method}/predictions.jsonl"
    comparison_path = round2_dir / f"comparisons/far_vs_{baseline_method}.json"
    far_scores = _by_id(read_jsonl(far_scores_path), "sample_id")
    baseline_scores = _by_id(read_jsonl(baseline_scores_path), "sample_id")
    far_predictions = _by_id(read_jsonl(far_predictions_path), "sample_id")
    baseline_predictions = _by_id(read_jsonl(baseline_predictions_path), "sample_id")
    expected_ids = set(tasks)
    for name, rows in (
        ("far_scores", far_scores),
        ("baseline_scores", baseline_scores),
        ("far_predictions", far_predictions),
        ("baseline_predictions", baseline_predictions),
    ):
        if set(rows) != expected_ids:
            raise ValueError(f"{name} sample IDs differ from frozen dev tasks")

    outcome_ids: dict[str, list[str]] = defaultdict(list)
    category_outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    gold_count_outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    wrong_count_outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    cases: list[dict[str, Any]] = []
    for sample_id in sorted(expected_ids):
        task = tasks[sample_id]
        outcome = _outcome(far_scores[sample_id], baseline_scores[sample_id])
        outcome_ids[outcome].append(sample_id)
        category_outcomes[str(task["category"])][outcome] += 1
        gold_count_outcomes[str(len(task["gold_answers"]))][outcome] += 1
        wrong_count_outcomes[str(len(task["wrong_answers"]))][outcome] += 1
        if outcome in {"far_only", "baseline_only"}:
            cases.append(
                {
                    "sample_id": sample_id,
                    "outcome": outcome,
                    "category": task["category"],
                    "question": task["question"],
                    "gold_answers": task["gold_answers"],
                    "wrong_answers": task["wrong_answers"],
                    "document_count": len(task["document_ids"]),
                    "far_score": far_scores[sample_id],
                    "baseline_score": baseline_scores[sample_id],
                    "far_answer": far_predictions[sample_id]["answer"],
                    "baseline_answer": baseline_predictions[sample_id]["answer"],
                    "far_prediction_summary": _prediction_summary(far_predictions[sample_id]),
                    "baseline_prediction_summary": _prediction_summary(
                        baseline_predictions[sample_id]
                    ),
                    "final_answer_consolidation": far_predictions[sample_id]
                    .get("metadata", {})
                    .get("final_answer_consolidation"),
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    cases_path = output_dir / "discordant_cases.jsonl"
    write_jsonl(cases_path, cases)
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    outcome_order = ("both_correct", "far_only", "baseline_only", "both_incorrect")
    report = {
        "schema_version": "far-ramdocs-dev-error-analysis-v2",
        "round": 2,
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "split": "dev",
        "samples": len(expected_ids),
        "candidate_method": "far_round2_answer_consolidation",
        "baseline_method": baseline_method,
        "gate_a_passed": False,
        "stop_rule_triggered": True,
        "paper_downgrade_required": True,
        "paired_comparison": comparison,
        "paired_outcomes": {
            outcome: len(outcome_ids.get(outcome, [])) for outcome in outcome_order
        },
        "method_summaries": {
            "far": _group_summary(sorted(expected_ids), far_scores, far_predictions),
            baseline_method: _group_summary(
                sorted(expected_ids), baseline_scores, baseline_predictions
            ),
        },
        "discordant_summaries": {
            outcome: {
                "far": _group_summary(outcome_ids[outcome], far_scores, far_predictions),
                baseline_method: _group_summary(
                    outcome_ids[outcome], baseline_scores, baseline_predictions
                ),
            }
            for outcome in ("far_only", "baseline_only")
        },
        "segments": {
            "category": {
                key: {outcome: value.get(outcome, 0) for outcome in outcome_order}
                for key, value in sorted(category_outcomes.items())
            },
            "gold_answer_count": {
                key: {outcome: value.get(outcome, 0) for outcome in outcome_order}
                for key, value in sorted(gold_count_outcomes.items(), key=lambda item: int(item[0]))
            },
            "wrong_answer_count": {
                key: {outcome: value.get(outcome, 0) for outcome in outcome_order}
                for key, value in sorted(
                    wrong_count_outcomes.items(), key=lambda item: int(item[0])
                )
            },
        },
        "source_fingerprints": {
            "round_manifest": sha256_file(round2_dir / "round_manifest.json"),
            "round1_suite_manifest": sha256_file(round1_dir / "suite_manifest.json"),
            "tasks": sha256_file(data_dir / "tasks.jsonl"),
            "far_scores": sha256_file(far_scores_path),
            "baseline_scores": sha256_file(baseline_scores_path),
            "far_predictions": sha256_file(far_predictions_path),
            "baseline_predictions": sha256_file(baseline_predictions_path),
            "discordant_cases": sha256_file(cases_path),
        },
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }
    write_json(output_dir / "report.json", report)
    _write_markdown(output_dir / "README.md", report)
    verification = verify_analysis(
        data_dir,
        round1_dir,
        round2_dir,
        config_path,
        output_dir,
    )
    if verification.get("valid") is not True:
        raise ValueError(f"created Round 2 error analysis is invalid: {verification['errors']}")
    return report


def verify_analysis(
    data_dir: Path,
    round1_dir: Path,
    round2_dir: Path,
    config_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        verify_active_protocol()
        round_audit = verify_round(data_dir, round1_dir, round2_dir, config_path)
        decision = json.loads((round2_dir / "round_manifest.json").read_text(encoding="utf-8"))
        report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
        cases_path = output_dir / "discordant_cases.jsonl"
        cases = read_jsonl(cases_path)
        baseline = str(decision["reused_round1_artifacts"]["baseline_method"])
        comparison_path = round2_dir / f"comparisons/far_vs_{baseline}.json"
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        task_ids = {
            str(row["id"])
            for row in read_jsonl(data_dir / "tasks.jsonl")
            if row.get("split") == "dev"
        }
        far_scores = _by_id(
            read_jsonl(round2_dir / "evaluations/far/scores.jsonl"),
            "sample_id",
        )
        baseline_scores = _by_id(
            read_jsonl(round1_dir / f"evaluations/{baseline}/scores.jsonl"),
            "sample_id",
        )
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return {
            "schema_version": "far-ramdocs-dev-error-analysis-audit-v2",
            "valid": False,
            "errors": [str(exc)],
        }
    if round_audit.get("valid") is not True:
        errors.append("Round 2 evidence is invalid")
        errors.extend(str(item) for item in round_audit.get("errors", []))
    expected = {
        "schema_version": "far-ramdocs-dev-error-analysis-v2",
        "round": 2,
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "split": "dev",
        "samples": 350,
        "baseline_method": baseline,
        "gate_a_passed": False,
        "stop_rule_triggered": True,
        "paper_downgrade_required": True,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }
    for key, value in expected.items():
        if report.get(key) != value:
            errors.append(f"error-analysis field mismatch: {key}")
    if (
        decision.get("gate_a_passed") is not False
        or decision.get("stop_rule_triggered") is not True
    ):
        errors.append("Round 2 decision is not a failed G-A stop decision")
    if report.get("paired_comparison") != comparison:
        errors.append("error analysis embeds a different paired comparison")
    if len(task_ids) != 350 or set(far_scores) != task_ids or set(baseline_scores) != task_ids:
        errors.append("error-analysis inputs do not cover the frozen 350-sample dev set")
    recomputed_outcomes = Counter(
        _outcome(far_scores[sample_id], baseline_scores[sample_id])
        for sample_id in task_ids & set(far_scores) & set(baseline_scores)
    )
    outcome_names = {"both_correct", "far_only", "baseline_only", "both_incorrect"}
    outcomes = report.get("paired_outcomes", {})
    try:
        outcome_counts = {key: int(value) for key, value in outcomes.items()}
    except (AttributeError, TypeError, ValueError):
        outcome_counts = {}
    if set(outcome_counts) != outcome_names or sum(outcome_counts.values()) != 350:
        errors.append("paired outcome counts do not cover 350 dev samples")
    if outcome_counts != {name: recomputed_outcomes.get(name, 0) for name in outcome_names}:
        errors.append("paired outcome counts differ from the frozen score files")
    case_ids = [str(row.get("sample_id", "")) for row in cases]
    expected_cases = outcome_counts.get("far_only", 0) + outcome_counts.get("baseline_only", 0)
    if (
        len(cases) != expected_cases
        or len(case_ids) != len(set(case_ids))
        or any(row.get("outcome") not in {"far_only", "baseline_only"} for row in cases)
    ):
        errors.append("discordant case file does not match paired outcomes")
    expected_case_outcomes = {
        sample_id: _outcome(far_scores[sample_id], baseline_scores[sample_id])
        for sample_id in task_ids & set(far_scores) & set(baseline_scores)
        if _outcome(far_scores[sample_id], baseline_scores[sample_id])
        in {"far_only", "baseline_only"}
    }
    actual_case_outcomes = {
        str(row.get("sample_id", "")): str(row.get("outcome", "")) for row in cases
    }
    if actual_case_outcomes != expected_case_outcomes:
        errors.append("discordant cases differ from the frozen score files")
    fingerprints = report.get("source_fingerprints", {})
    paths = {
        "round_manifest": round2_dir / "round_manifest.json",
        "round1_suite_manifest": round1_dir / "suite_manifest.json",
        "tasks": data_dir / "tasks.jsonl",
        "far_scores": round2_dir / "evaluations/far/scores.jsonl",
        "baseline_scores": round1_dir / f"evaluations/{baseline}/scores.jsonl",
        "far_predictions": round2_dir / "runs/far/predictions.jsonl",
        "baseline_predictions": round1_dir / f"runs/{baseline}/predictions.jsonl",
        "discordant_cases": cases_path,
    }
    for key, path in paths.items():
        if fingerprints.get(key) != sha256_file(path):
            errors.append(f"error-analysis source fingerprint mismatch: {key}")
    return {
        "schema_version": "far-ramdocs-dev-error-analysis-audit-v2",
        "valid": not errors,
        "errors": errors,
        "samples": report.get("samples"),
        "baseline_method": report.get("baseline_method"),
        "paper_downgrade_required": report.get("paper_downgrade_required"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--round1-dir", type=Path, required=True)
    parser.add_argument("--round2-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build_analysis(
        args.data_dir,
        args.round1_dir,
        args.round2_dir,
        args.config,
        args.output_dir,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
