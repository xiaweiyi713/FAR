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
    if decision.get("gate_a_passed") is not False or decision.get("stop_rule_triggered") is not True:
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
                for key, value in sorted(wrong_count_outcomes.items(), key=lambda item: int(item[0]))
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
    return report


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
