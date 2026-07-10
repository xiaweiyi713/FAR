"""Finalize and verify the dev-only RAMDocs Round 2 method iteration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from far.bench.build.common import sha256_file, write_json
from far.eval.ramdocs import compare_ramdocs, evaluate_ramdocs
from far.experiments.protocol_2plus4 import PROTOCOL_PHASE_A_SHA256, verify_active_protocol
from far.experiments.ramdocs_suite import verify_suite

SCHEMA_VERSION = "far-ramdocs-method-iteration-v1"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def finalize_round(
    data_dir: Path,
    round1_dir: Path,
    round2_dir: Path,
    config_path: Path,
) -> dict[str, Any]:
    """Score the changed FAR method against the frozen Round 1 strongest baseline."""

    verify_active_protocol()
    round1_audit = verify_suite(round1_dir, data_dir)
    if round1_audit.get("valid") is not True:
        raise ValueError(f"Round 1 suite is invalid: {round1_audit.get('errors', [])}")
    round1_manifest = _load(round1_dir / "suite_manifest.json")
    if round1_manifest.get("split") != "dev" or round1_manifest.get("samples") != 350:
        raise ValueError("Round 1 must be the complete 350-sample dev suite")
    if round1_manifest.get("gate_a_passed") is not False:
        raise ValueError("Round 2 is only defined after the failed Round 1 G-A gate")
    baseline = str(round1_manifest["strongest_baseline"])

    candidate_run_dir = round2_dir / "runs" / "far"
    candidate_manifest = _load(candidate_run_dir / "run_manifest.json")
    candidate_identity = _load(candidate_run_dir / "run_identity.json")
    if any(
        (
            candidate_manifest.get("status") != "complete",
            candidate_manifest.get("partial") is not False,
            candidate_manifest.get("split") != "dev",
            candidate_manifest.get("completed") != 350,
            candidate_manifest.get("expected") != 350,
            candidate_manifest.get("gold_loaded_by_runner") is not False,
        )
    ):
        raise ValueError("Round 2 FAR run is not a complete, gold-free 350-sample dev run")
    if candidate_identity.get("source_revision", {}).get("git_dirty") is not False:
        raise ValueError("Round 2 FAR run was not bound to a clean Git revision")
    if candidate_identity.get("config_sha256") != sha256_file(config_path):
        raise ValueError("Round 2 FAR run does not match the supplied configuration")
    round1_initial = round1_dir / "initial_answers" / "predictions.jsonl"
    if candidate_identity.get("initial_answers_sha256") != sha256_file(round1_initial):
        raise ValueError("Round 2 did not reuse the frozen Round 1 initial answers")

    candidate_eval_dir = round2_dir / "evaluations" / "far"
    candidate_report = evaluate_ramdocs(
        data_dir / "tasks.jsonl",
        candidate_run_dir / "predictions.jsonl",
        data_dir / "corpus.jsonl",
        candidate_eval_dir,
        split="dev",
        allow_partial=False,
    )
    baseline_scores = round1_dir / "evaluations" / baseline / "scores.jsonl"
    comparison_path = round2_dir / "comparisons" / f"far_vs_{baseline}.json"
    comparison = compare_ramdocs(
        baseline_scores,
        candidate_eval_dir / "scores.jsonl",
        comparison_path,
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "round": 2,
        "protocol_fingerprint": PROTOCOL_PHASE_A_SHA256,
        "split": "dev",
        "samples": 350,
        "changed_methods": ["far"],
        "reused_round1_artifacts": {
            "suite_manifest_sha256": sha256_file(round1_dir / "suite_manifest.json"),
            "initial_answers_sha256": sha256_file(round1_initial),
            "baseline_method": baseline,
            "baseline_scores_sha256": sha256_file(baseline_scores),
        },
        "candidate_artifacts": {
            "config_sha256": sha256_file(config_path),
            "run_identity_sha256": sha256_file(candidate_run_dir / "run_identity.json"),
            "run_manifest_sha256": sha256_file(candidate_run_dir / "run_manifest.json"),
            "predictions_sha256": sha256_file(candidate_run_dir / "predictions.jsonl"),
            "evaluation_report_sha256": sha256_file(candidate_eval_dir / "report.json"),
            "scores_sha256": sha256_file(candidate_eval_dir / "scores.jsonl"),
            "comparison_sha256": sha256_file(comparison_path),
        },
        "candidate_metrics": candidate_report["metrics"],
        "paired_comparison": comparison["comparison"],
        "mcnemar": comparison["mcnemar"],
        "gate_a_passed": comparison["gate_a_passed"],
        "stop_rule_triggered": not comparison["gate_a_passed"],
        "phase_b_authorized": comparison["gate_a_passed"],
        "test_accessed": False,
        "publication_gold": False,
        "human_iaa": False,
    }
    write_json(round2_dir / "round_manifest.json", manifest)
    return manifest


def verify_round(
    data_dir: Path,
    round1_dir: Path,
    round2_dir: Path,
    config_path: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        verify_active_protocol()
        manifest = _load(round2_dir / "round_manifest.json")
        round1_audit = verify_suite(round1_dir, data_dir)
        candidate_run = _load(round2_dir / "runs" / "far" / "run_manifest.json")
        candidate_identity = _load(round2_dir / "runs" / "far" / "run_identity.json")
        candidate_report = _load(round2_dir / "evaluations" / "far" / "report.json")
        comparison_path = (
            round2_dir
            / "comparisons"
            / (f"far_vs_{manifest['reused_round1_artifacts']['baseline_method']}.json")
        )
        comparison = _load(comparison_path)
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return {
            "schema_version": "far-ramdocs-method-iteration-audit-v1",
            "valid": False,
            "errors": [str(exc)],
        }

    if round1_audit.get("valid") is not True:
        errors.append("Round 1 suite is invalid")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "round": 2,
        "protocol_fingerprint": PROTOCOL_PHASE_A_SHA256,
        "split": "dev",
        "samples": 350,
        "changed_methods": ["far"],
        "test_accessed": False,
        "publication_gold": False,
        "human_iaa": False,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            errors.append(f"manifest field mismatch: {key}")
    if candidate_run.get("status") != "complete" or candidate_run.get("completed") != 350:
        errors.append("candidate FAR run is incomplete")
    if (
        candidate_run.get("partial") is not False
        or candidate_run.get("gold_loaded_by_runner") is not False
    ):
        errors.append("candidate FAR run is partial or not gold-free")
    if candidate_identity.get("source_revision", {}).get("git_dirty") is not False:
        errors.append("candidate FAR source revision is dirty")
    if candidate_identity.get("config_sha256") != sha256_file(config_path):
        errors.append("candidate configuration fingerprint mismatch")
    round1_initial = round1_dir / "initial_answers" / "predictions.jsonl"
    if candidate_identity.get("initial_answers_sha256") != sha256_file(round1_initial):
        errors.append("frozen initial-answer fingerprint mismatch")
    if candidate_report.get("samples") != 350 or candidate_report.get("partial") is not False:
        errors.append("candidate evaluation is incomplete")
    provenance = candidate_report.get("provenance", {})
    if provenance.get("tasks_sha256") != sha256_file(data_dir / "tasks.jsonl"):
        errors.append("candidate task fingerprint mismatch")
    if provenance.get("corpus_sha256") != sha256_file(data_dir / "corpus.jsonl"):
        errors.append("candidate corpus fingerprint mismatch")
    baseline = manifest.get("reused_round1_artifacts", {}).get("baseline_method")
    baseline_scores = round1_dir / "evaluations" / str(baseline) / "scores.jsonl"
    if manifest.get("reused_round1_artifacts", {}).get("baseline_scores_sha256") != sha256_file(
        baseline_scores
    ):
        errors.append("frozen baseline score fingerprint mismatch")
    artifact_paths = {
        "config_sha256": config_path,
        "run_identity_sha256": round2_dir / "runs" / "far" / "run_identity.json",
        "run_manifest_sha256": round2_dir / "runs" / "far" / "run_manifest.json",
        "predictions_sha256": round2_dir / "runs" / "far" / "predictions.jsonl",
        "evaluation_report_sha256": round2_dir / "evaluations" / "far" / "report.json",
        "scores_sha256": round2_dir / "evaluations" / "far" / "scores.jsonl",
        "comparison_sha256": comparison_path,
    }
    for key, path in artifact_paths.items():
        if manifest.get("candidate_artifacts", {}).get(key) != sha256_file(path):
            errors.append(f"candidate artifact fingerprint mismatch: {key}")
    gate = comparison.get("gate_a_passed")
    if manifest.get("gate_a_passed") is not gate:
        errors.append("G-A result disagrees with paired comparison")
    if manifest.get("stop_rule_triggered") is not (not gate):
        errors.append("stop-rule state disagrees with G-A")
    if manifest.get("phase_b_authorized") is not gate:
        errors.append("Phase B authorization disagrees with G-A")
    return {
        "schema_version": "far-ramdocs-method-iteration-audit-v1",
        "valid": not errors,
        "errors": errors,
        "round": 2,
        "split": manifest.get("split"),
        "samples": manifest.get("samples"),
        "gate_a_passed": manifest.get("gate_a_passed"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("finalize", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--data-dir", type=Path, required=True)
        subparser.add_argument("--round1-dir", type=Path, required=True)
        subparser.add_argument("--round2-dir", type=Path, required=True)
        subparser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    function = finalize_round if args.command == "finalize" else verify_round
    result = function(args.data_dir, args.round1_dir, args.round2_dir, args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "verify" and not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
