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
) -> dict[str, Any]:
    verify_active_protocol()
    if target not in {"falsirag", "ramdocs"}:
        raise ValueError("one-shot target must be falsirag or ramdocs")
    if not methods or len(set(methods)) != len(methods):
        raise ValueError("one-shot methods must be a non-empty unique list")
    status = _git("status", "--porcelain", "--untracked-files=all")
    if status:
        raise ValueError("one-shot intent must be prepared from a clean worktree")
    payload = {
        "schema_version": "far-one-shot-intent-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target": target,
        "split": "test",
        "methods": sorted(methods),
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "benchmark_input_sha256": sha256_file(benchmark_input),
        "data_manifest_sha256": sha256_file(data_manifest),
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
    return {"intent": local, "committed_in": commit, "path": relative}


def seal_run(intent_path: Path, suite_manifest_path: Path, output_path: Path) -> dict[str, Any]:
    committed = committed_intent(intent_path)
    intent = committed["intent"]
    suite = json.loads(suite_manifest_path.read_text(encoding="utf-8"))
    if suite.get("split") != "test" or suite.get("allow_test") is not True:
        raise ValueError("one-shot suite is not an authorized test run")
    if suite.get("partial") not in {False, None} or suite.get("limit") not in {None}:
        raise ValueError("one-shot suite must cover the complete test split")
    if set(suite.get("methods", [])) != set(intent["methods"]):
        raise ValueError("one-shot suite method set differs from committed intent")
    current = _git("rev-parse", "HEAD")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", committed["committed_in"], current],
        cwd=ROOT,
    ).returncode == 0
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
    verify = subparsers.add_parser("verify-committed")
    verify.add_argument("--intent", type=Path, required=True)
    seal = subparsers.add_parser("seal")
    seal.add_argument("--intent", type=Path, required=True)
    seal.add_argument("--suite-manifest", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_intent(
            args.target,
            args.benchmark_input,
            args.data_manifest,
            args.method,
            args.output,
        )
    elif args.command == "verify-committed":
        result = committed_intent(args.intent)
    else:
        result = seal_run(args.intent, args.suite_manifest, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
