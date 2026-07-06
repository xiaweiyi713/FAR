"""Commit-bound intent and sealing for locally held one-shot test evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.build.common import sha256_file, write_json
from experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256, ROOT, verify_active_protocol


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _pretest_evidence(
    ramdocs_gate_manifest: Path,
    jury_labels_manifest: Path,
    sensitivity_report: Path,
    matrix_report: Path,
) -> dict[str, str]:
    ramdocs = _json(ramdocs_gate_manifest)
    if ramdocs.get("schema_version") not in {
        "far-ramdocs-suite-v1",
        "far-ramdocs-method-iteration-v1",
    }:
        raise ValueError("pretest RAMDocs gate uses an unsupported schema")
    if (
        ramdocs.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256
        or ramdocs.get("split") != "dev"
        or ramdocs.get("samples") != 350
        or ramdocs.get("gate_a_passed") is not True
        or ramdocs.get("stop_rule_triggered") is not False
    ):
        raise ValueError("G-A must pass on the complete RAMDocs dev split before test intent")
    if ramdocs.get("schema_version") == "far-ramdocs-method-iteration-v1" and (
        ramdocs.get("phase_b_authorized") is not True
        or ramdocs.get("test_accessed") is not False
    ):
        raise ValueError("RAMDocs Round 2 does not authorize Phase B/test progression")

    labels = _json(jury_labels_manifest)
    labels_path = jury_labels_manifest.parent / str(labels.get("labels_file", ""))
    phase_b_gate = labels.get("phase_b_gate")
    if (
        labels.get("schema_version") != "far-jury-labels-v1"
        or labels.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256
        or labels.get("gate_k_passed") is not True
        or labels.get("gate_s_passed") is not True
        or labels.get("jury_gold") is not True
        or labels.get("publication_gold") is not False
        or labels.get("human_iaa") is not False
        or labels.get("samples") != 300
        or labels.get("excluded_disputed_samples") != []
        or not isinstance(phase_b_gate, dict)
        or phase_b_gate.get("round_manifest_sha256") != sha256_file(ramdocs_gate_manifest)
        or phase_b_gate.get("gate_a_passed") is not True
        or phase_b_gate.get("phase_b_authorized") is not True
        or not labels_path.is_file()
        or labels.get("labels_sha256") != sha256_file(labels_path)
    ):
        raise ValueError("complete G-K/G-S jury labels must be frozen before test intent")

    sensitivity = _json(sensitivity_report)
    if (
        sensitivity.get("schema_version") != "far-jury-label-sensitivity-v1"
        or sensitivity.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256
        or sensitivity.get("family") != "qwen"
        or set(sensitivity.get("views", {}))
        != {"construction", "jury_gold", "unanimous_only"}
        or not sensitivity.get("rows")
        or sensitivity.get("label_granularity") != labels.get("label_granularity")
        or sensitivity.get("publication_gold") is not False
        or sensitivity.get("human_iaa") is not False
    ):
        raise ValueError("three-view Qwen label sensitivity must be frozen before test intent")

    matrix = _json(matrix_report)
    matrix_families = {
        str(row.get("family", ""))
        for row in matrix.get("rows", [])
        if isinstance(row, dict)
    }
    if (
        matrix.get("schema_version") != "far-model-matrix-v1"
        or matrix.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256
        or matrix_families != {"qwen", "mistral", "google"}
        or matrix.get("label_granularity") != labels.get("label_granularity")
        or matrix.get("jury_labels_manifest_sha256") != sha256_file(jury_labels_manifest)
        or matrix.get("publication_gold") is not False
    ):
        raise ValueError("complete three-family dev matrix must be frozen before test intent")
    return {
        "ramdocs_gate_manifest_sha256": sha256_file(ramdocs_gate_manifest),
        "jury_labels_manifest_sha256": sha256_file(jury_labels_manifest),
        "sensitivity_report_sha256": sha256_file(sensitivity_report),
        "matrix_report_sha256": sha256_file(matrix_report),
    }


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def prepare_intent(
    target: str,
    benchmark_input: Path,
    data_manifest: Path,
    methods: list[str],
    output_path: Path,
    *,
    ramdocs_gate_manifest: Path,
    jury_labels_manifest: Path,
    sensitivity_report: Path,
    matrix_report: Path,
) -> dict[str, Any]:
    verify_active_protocol()
    if target not in {"falsirag", "ramdocs"}:
        raise ValueError("one-shot target must be falsirag or ramdocs")
    if not methods or len(set(methods)) != len(methods):
        raise ValueError("one-shot methods must be a non-empty unique list")
    status = _git("status", "--porcelain", "--untracked-files=all")
    if status:
        raise ValueError("one-shot intent must be prepared from a clean worktree")
    pretest_evidence = _pretest_evidence(
        ramdocs_gate_manifest,
        jury_labels_manifest,
        sensitivity_report,
        matrix_report,
    )
    expected_samples = sum(
        bool(line.strip()) for line in benchmark_input.read_text(encoding="utf-8").splitlines()
    )
    registered_samples = 58 if target == "falsirag" else 150
    if expected_samples != registered_samples:
        raise ValueError("one-shot benchmark input does not match the preregistered test size")
    payload = {
        "schema_version": "far-one-shot-intent-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target": target,
        "split": "test",
        "methods": sorted(methods),
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "benchmark_input_sha256": sha256_file(benchmark_input),
        "expected_samples": expected_samples,
        "data_manifest_sha256": sha256_file(data_manifest),
        "pretest_evidence": pretest_evidence,
        "pretest_gate_passed": True,
        "prepared_from_git_commit": _git("rev-parse", "HEAD"),
        "externally_held": False,
        "one_shot": True,
        "evaluation_started": False,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["intent_id"] = hashlib.sha256(encoded).hexdigest()
    write_json(output_path, payload)
    return payload


def committed_intent(intent_path: Path) -> dict[str, Any]:
    resolved = intent_path.resolve()
    try:
        relative = resolved.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("one-shot intent must live inside the repository") from exc
    local = json.loads(resolved.read_text(encoding="utf-8"))
    commit = _git("log", "-1", "--format=%H", "--", relative)
    if not commit:
        raise ValueError("one-shot intent has not been committed")
    committed_bytes = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    if hashlib.sha256(committed_bytes).hexdigest() != sha256_file(resolved):
        raise ValueError("working one-shot intent differs from its committed version")
    if local.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256:
        raise ValueError("one-shot intent uses a stale protocol")
    if (
        local.get("schema_version") != "far-one-shot-intent-v1"
        or local.get("target") not in {"falsirag", "ramdocs"}
        or local.get("split") != "test"
        or local.get("one_shot") is not True
        or local.get("externally_held") is not False
        or local.get("evaluation_started") is not False
        or local.get("pretest_gate_passed") is not True
        or set(local.get("pretest_evidence", {}))
        != {
            "ramdocs_gate_manifest_sha256",
            "jury_labels_manifest_sha256",
            "sensitivity_report_sha256",
            "matrix_report_sha256",
        }
    ):
        raise ValueError("committed one-shot intent is incomplete or unsafe")
    registered_samples = 58 if local["target"] == "falsirag" else 150
    if local.get("expected_samples") != registered_samples or any(
        not str(value).strip() for value in local["pretest_evidence"].values()
    ):
        raise ValueError("committed one-shot intent has invalid sample or evidence fingerprints")
    return {"intent": local, "committed_in": commit, "path": relative}


def authorize_committed_intent(
    intent_path: Path,
    *,
    target: str,
    benchmark_input: Path,
    data_manifest: Path,
    methods: set[str],
) -> dict[str, Any]:
    committed = committed_intent(intent_path)
    intent = committed["intent"]
    if (
        intent.get("target") != target
        or intent.get("benchmark_input_sha256") != sha256_file(benchmark_input)
        or intent.get("data_manifest_sha256") != sha256_file(data_manifest)
        or set(intent.get("methods", [])) != methods
    ):
        raise ValueError("committed one-shot intent does not authorize this exact test suite")
    return committed


def seal_run(
    intent_path: Path,
    suite_manifest_path: Path,
    score_manifest_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    committed = committed_intent(intent_path)
    intent = committed["intent"]
    suite = json.loads(suite_manifest_path.read_text(encoding="utf-8"))
    if suite.get("split") != "test" or suite.get("allow_test") is not True:
        raise ValueError("one-shot suite is not an authorized test run")
    if suite.get("partial") not in {False, None} or suite.get("limit") not in {None}:
        raise ValueError("one-shot suite must cover the complete test split")
    if set(suite.get("methods", [])) != set(intent["methods"]):
        raise ValueError("one-shot suite method set differs from committed intent")
    if (
        suite.get("one_shot_intent_id") != intent.get("intent_id")
        or suite.get("one_shot_intent_sha256") != sha256_file(intent_path)
        or suite.get("one_shot_intent_commit") != committed.get("committed_in")
    ):
        raise ValueError("one-shot suite is not bound to the committed intent")
    if intent["target"] == "falsirag":
        if any(
            (
                suite.get("schema_version") != "far-blind-suite-manifest-v1",
                suite.get("blind_input_sha256") != intent.get("benchmark_input_sha256"),
                suite.get("gold_loaded") is not False,
                suite.get("unscored") is not True,
                suite.get("diagnostic_only") is not False,
            )
        ):
            raise ValueError("FalsiRAG one-shot suite identity is invalid")
        run_manifests = suite.get("run_manifests", {})
        if set(run_manifests) != set(intent["methods"]) or any(
            item.get("partial") is not False
            or item.get("completed") != intent.get("expected_samples")
            for item in run_manifests.values()
        ):
            raise ValueError("FalsiRAG one-shot predictions are incomplete")
    elif any(
        (
            suite.get("schema_version") != "far-ramdocs-suite-v1",
            suite.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256,
            suite.get("samples") != intent.get("expected_samples"),
            suite.get("publication_gold") is not False,
            suite.get("externally_held_blind") is not False,
        )
    ):
        raise ValueError("RAMDocs one-shot suite identity is invalid")
    score = json.loads(score_manifest_path.read_text(encoding="utf-8"))
    if score.get("split") != "test":
        raise ValueError("one-shot score manifest is not a test evaluation")
    if score.get("samples") != intent.get("expected_samples"):
        raise ValueError("one-shot score count differs from committed intent")
    if "methods" in score and set(score.get("methods", [])) != set(intent["methods"]):
        raise ValueError("one-shot score method set differs from committed intent")
    if score.get("protocol_fingerprint") not in {None, PROTOCOL_ACTIVE_SHA256}:
        raise ValueError("one-shot score manifest uses a stale protocol")
    current = _git("rev-parse", "HEAD")
    ancestor = (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", committed["committed_in"], current],
            cwd=ROOT,
        ).returncode
        == 0
    )
    if not ancestor:
        raise ValueError("committed one-shot intent is not an ancestor of the evaluation commit")
    seal = {
        "schema_version": "far-one-shot-seal-v1",
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "target": intent["target"],
        "intent_id": intent["intent_id"],
        "intent_sha256": sha256_file(intent_path),
        "intent_commit": committed["committed_in"],
        "evaluation_commit": current,
        "suite_manifest_sha256": sha256_file(suite_manifest_path),
        "score_manifest_sha256": sha256_file(score_manifest_path),
        "scored_samples": score["samples"],
        "methods": intent["methods"],
        "one_shot": True,
        "externally_held": False,
        "fingerprint_chain_valid": True,
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
    }
    write_json(output_path, seal)
    return seal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--target", choices=("falsirag", "ramdocs"), required=True)
    prepare.add_argument("--benchmark-input", type=Path, required=True)
    prepare.add_argument("--data-manifest", type=Path, required=True)
    prepare.add_argument("--method", action="append", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--ramdocs-gate-manifest", type=Path, required=True)
    prepare.add_argument("--jury-labels-manifest", type=Path, required=True)
    prepare.add_argument("--sensitivity-report", type=Path, required=True)
    prepare.add_argument("--matrix-report", type=Path, required=True)
    verify = subparsers.add_parser("verify-committed")
    verify.add_argument("--intent", type=Path, required=True)
    seal = subparsers.add_parser("seal")
    seal.add_argument("--intent", type=Path, required=True)
    seal.add_argument("--suite-manifest", type=Path, required=True)
    seal.add_argument("--score-manifest", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_intent(
            args.target,
            args.benchmark_input,
            args.data_manifest,
            args.method,
            args.output,
            ramdocs_gate_manifest=args.ramdocs_gate_manifest,
            jury_labels_manifest=args.jury_labels_manifest,
            sensitivity_report=args.sensitivity_report,
            matrix_report=args.matrix_report,
        )
    elif args.command == "verify-committed":
        result = committed_intent(args.intent)
    else:
        result = seal_run(
            args.intent,
            args.suite_manifest,
            args.score_manifest,
            args.output,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
