"""Run and audit the preregistered RAMDocs development comparison suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json
from eval.ramdocs import compare_ramdocs, evaluate_ramdocs
from experiments.one_shot import authorize_committed_intent
from experiments.protocol_2plus4 import (
    PROTOCOL_ACTIVE_SHA256,
    PROTOCOL_PHASE_A_SHA256,
    verify_active_protocol,
)
from experiments.run_ramdocs import METHODS, initialize_answers, run_method
from experiments.runner import one_shot_test_scope

REQUIRED_METHODS = (
    "far",
    "far_minus_typed_conflict",
    "vanilla_rag",
    "multi_query_rag",
    "reflective_rag",
    "crag_style_reproduction",
    "self_rag_style_reproduction",
    "counterrefine_style_reproduction",
)


def _run_suite_authorized(
    config_path: Path,
    data_dir: Path,
    output_dir: Path,
    *,
    methods: tuple[str, ...] = REQUIRED_METHODS,
    split: str = "dev",
    limit: int | None = None,
    allow_test: bool = False,
) -> dict[str, Any]:
    verify_active_protocol()
    if any(method not in METHODS for method in methods):
        raise ValueError("RAMDocs suite contains an unknown method")
    if split == "test" and set(methods) != set(REQUIRED_METHODS):
        raise ValueError("held-out RAMDocs suite must run the complete preregistered method set")
    initial_dir = output_dir / "initial_answers"
    initialize_answers(
        config_path,
        data_dir,
        initial_dir,
        split=split,
        limit=limit,
        allow_test=allow_test,
    )
    initial_path = initial_dir / "predictions.jsonl"
    reports: dict[str, str] = {}
    run_manifests: dict[str, str] = {}
    for method in methods:
        run_dir = output_dir / "runs" / method
        run_method(
            config_path,
            data_dir,
            initial_path,
            run_dir,
            method=method,
            split=split,
            limit=limit,
            allow_test=allow_test,
        )
        evaluation_dir = output_dir / "evaluations" / method
        evaluate_ramdocs(
            data_dir / "tasks.jsonl",
            run_dir / "predictions.jsonl",
            data_dir / "corpus.jsonl",
            evaluation_dir,
            split=split,
            allow_partial=limit is not None,
        )
        reports[method] = sha256_file(evaluation_dir / "report.json")
        run_manifests[method] = sha256_file(run_dir / "run_manifest.json")
    comparisons: dict[str, dict[str, Any]] = {}
    far_scores = output_dir / "evaluations" / "far" / "scores.jsonl"
    for method in methods:
        if method == "far":
            continue
        comparison_path = output_dir / "comparisons" / f"far_vs_{method}.json"
        comparisons[method] = compare_ramdocs(
            output_dir / "evaluations" / method / "scores.jsonl",
            far_scores,
            comparison_path,
        )
    baseline_methods = [method for method in methods if not method.startswith("far")]
    aggregate_reports = {
        method: json.loads(
            (output_dir / "evaluations" / method / "report.json").read_text(encoding="utf-8")
        )
        for method in methods
    }
    strongest = max(
        baseline_methods,
        key=lambda method: (
            float(aggregate_reports[method]["metrics"]["ramdocs_exact_match"]),
            method,
        ),
    )
    gate_a = comparisons[strongest]["gate_a_passed"]
    manifest = {
        "schema_version": "far-ramdocs-suite-v1",
        "study_profile": "external_upstream_labeled_evaluation",
        "protocol_fingerprint": (
            PROTOCOL_PHASE_A_SHA256 if split == "dev" else PROTOCOL_ACTIVE_SHA256
        ),
        "split": split,
        "allow_test": allow_test,
        "partial": limit is not None,
        "samples": len(read_jsonl(initial_path)),
        "methods": list(methods),
        "strongest_baseline": strongest,
        "gate_a_passed": gate_a,
        "stop_rule_triggered": split == "dev" and not gate_a,
        "reports": reports,
        "run_manifests": run_manifests,
        "comparisons": {
            method: sha256_file(output_dir / "comparisons" / f"far_vs_{method}.json")
            for method in comparisons
        },
        "publication_gold": False,
        "externally_held_blind": False,
    }
    write_json(output_dir / "suite_manifest.json", manifest)
    return manifest


def run_suite(
    config_path: Path,
    data_dir: Path,
    output_dir: Path,
    *,
    methods: tuple[str, ...] = REQUIRED_METHODS,
    split: str = "dev",
    limit: int | None = None,
    allow_test: bool = False,
    one_shot_intent: Path | None = None,
) -> dict[str, Any]:
    if split != "test":
        if one_shot_intent is not None:
            raise ValueError("one-shot intent may only authorize the test split")
        return _run_suite_authorized(
            config_path,
            data_dir,
            output_dir,
            methods=methods,
            split=split,
            limit=limit,
            allow_test=allow_test,
        )
    if not allow_test or one_shot_intent is None or limit is not None:
        raise ValueError("complete RAMDocs test suite requires --allow-test and --one-shot-intent")
    committed = authorize_committed_intent(
        one_shot_intent,
        target="ramdocs",
        benchmark_input=data_dir / "splits/test_inputs.jsonl",
        data_manifest=data_dir / "manifest.json",
        methods=set(methods),
    )
    with one_shot_test_scope():
        manifest = _run_suite_authorized(
            config_path,
            data_dir,
            output_dir,
            methods=methods,
            split="test",
            limit=None,
            allow_test=True,
        )
    manifest.update(
        {
            "one_shot_intent_id": committed["intent"]["intent_id"],
            "one_shot_intent_sha256": sha256_file(one_shot_intent),
            "one_shot_intent_commit": committed["committed_in"],
        }
    )
    write_json(output_dir / "suite_manifest.json", manifest)
    return manifest


def verify_suite(output_dir: Path, data_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        verify_active_protocol()
        manifest = json.loads((output_dir / "suite_manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return {
            "schema_version": "far-ramdocs-suite-audit-v1",
            "valid": False,
            "errors": [str(exc)],
        }
    if manifest.get("schema_version") != "far-ramdocs-suite-v1":
        errors.append("unsupported RAMDocs suite schema")
    expected_protocol = (
        PROTOCOL_PHASE_A_SHA256
        if manifest.get("split") == "dev"
        else PROTOCOL_ACTIVE_SHA256
    )
    if manifest.get("protocol_fingerprint") != expected_protocol:
        errors.append("RAMDocs suite uses a stale protocol")
    if manifest.get("publication_gold") is not False:
        errors.append("RAMDocs suite incorrectly claims publication gold")
    methods = manifest.get("methods", [])
    if manifest.get("partial") is not False or set(methods) != set(REQUIRED_METHODS):
        errors.append("RAMDocs formal suite is incomplete")
    expected_samples = 350 if manifest.get("split") == "dev" else 150
    if manifest.get("samples") != expected_samples:
        errors.append("RAMDocs suite sample count does not match its split")
    for method in methods:
        run_dir = output_dir / "runs" / method
        evaluation_dir = output_dir / "evaluations" / method
        try:
            run_manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            report = json.loads((evaluation_dir / "report.json").read_text(encoding="utf-8"))
            if run_manifest.get("status") != "complete" or run_manifest.get("partial") is not False:
                errors.append(f"{method}: run is incomplete")
            if report.get("samples") != expected_samples:
                errors.append(f"{method}: evaluation sample count mismatch")
            if manifest.get("run_manifests", {}).get(method) != sha256_file(
                run_dir / "run_manifest.json"
            ):
                errors.append(f"{method}: run manifest fingerprint mismatch")
            if manifest.get("reports", {}).get(method) != sha256_file(
                evaluation_dir / "report.json"
            ):
                errors.append(f"{method}: report fingerprint mismatch")
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            errors.append(f"{method}: {exc}")
    return {
        "schema_version": "far-ramdocs-suite-audit-v1",
        "valid": not errors,
        "errors": errors,
        "split": manifest.get("split"),
        "gate_a_passed": manifest.get("gate_a_passed"),
        "data_manifest_sha256": sha256_file(data_dir / "manifest.json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--config", type=Path, required=True)
    run_parser.add_argument("--data-dir", type=Path, required=True)
    run_parser.add_argument("--output-dir", type=Path, required=True)
    run_parser.add_argument("--method", action="append", choices=METHODS)
    run_parser.add_argument("--split", choices=("dev", "test"), default="dev")
    run_parser.add_argument("--limit", type=int)
    run_parser.add_argument("--allow-test", action="store_true")
    run_parser.add_argument("--one-shot-intent", type=Path)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--data-dir", type=Path, required=True)
    verify_parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = (
        run_suite(
            args.config,
            args.data_dir,
            args.output_dir,
            methods=tuple(args.method or REQUIRED_METHODS),
            split=args.split,
            limit=args.limit,
            allow_test=args.allow_test,
            one_shot_intent=args.one_shot_intent,
        )
        if args.command == "run"
        else verify_suite(args.output_dir, args.data_dir)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "verify" and not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
