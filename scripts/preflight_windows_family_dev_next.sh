#!/usr/bin/env bash
# Fail-closed, read-only preflight for the next WS2 family-dev run on windows-gpu.
#
# This script does not start/stop systemd units, run predictions, inspect any
# held-out/test split, or write remote files.  It verifies that the frozen D:
# worktree/output can safely advance to the requested next preregistered family.
#
# Usage:
#   scripts/preflight_windows_family_dev_next.sh google
#   FAR_FAMILY_DEV_REQUIRE_OLLAMA=1 scripts/preflight_windows_family_dev_next.sh google

set -euo pipefail

family="${1:-google}"
remote="${2:-${FAR_WINDOWS_REMOTE:-windows-gpu}}"

case "${family}" in
  google|meta) ;;
  *)
    echo "family must be google or meta; got ${family}" >&2
    exit 2
    ;;
esac

output_dir="${FAR_FAMILY_DEV_OUTPUT_DIR:-/mnt/d/FAR-outputs/family_dev_v1}"
input_dir="${FAR_FAMILY_DEV_INPUT_DIR:-/mnt/d/FAR-outputs/family_dev_input_v1}"
worktree="${FAR_FAMILY_DEV_WORKTREE:-/mnt/d/FAR-workspace/FAR-longterm}"
expected_commit="${FAR_FAMILY_DEV_EXPECTED_COMMIT:-bd57585716b4c046db97311209a0d9f7ec340e6d}"
require_ollama="${FAR_FAMILY_DEV_REQUIRE_OLLAMA:-0}"

ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- \
  "${family}" "${output_dir}" "${input_dir}" "${worktree}" "${expected_commit}" \
  "${require_ollama}" <<'REMOTE'
set -euo pipefail

family="$1"
output_dir="$2"
input_dir="$3"
worktree="$4"
expected_commit="$5"
require_ollama="$6"

python3 - "$family" "$output_dir" "$input_dir" "$worktree" "$expected_commit" \
  "$require_ollama" <<'PY'
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

family, output_dir_text, input_dir_text, worktree_text, expected_commit, require_ollama = (
    sys.argv[1:7]
)
output_dir = Path(output_dir_text)
input_dir = Path(input_dir_text)
worktree = Path(worktree_text)
require_ollama_bool = require_ollama == "1"

MODEL_SPECS: dict[str, dict[str, str]] = {
    "mistral": {
        "model": "mistral:7b-instruct",
        "digest": "6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf",
        "config_sha256": "31035391d672883e2d6f347ca3acd937cd91f2c345e960695292be88774d4b5b",
    },
    "google": {
        "model": "gemma2:9b",
        "digest": "ff02c3702f322b9e075e9568332d96c0a7028002f1a5a056e0a6784320a4db0b",
        "config_sha256": "2c348c6a530b31d5154b992e9f111528b81d78541ea40b48e121e6c1511098e1",
    },
    "meta": {
        "model": "llama3.1:8b",
        "digest": "46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e",
        "config_sha256": "127eff6e860dc81b1252a8d8507fe499da4b5bad1e095097686f3c696e6f4090",
    },
}
FAMILY_ORDER = ("mistral", "google", "meta")
METHODS = ("far", "minus_typed_conflict")
DEV_SHA256 = "63db7916ef42d3da7e70fe977471a6958afec2a760bcad3d43526052ecd5dff3"
CORPUS_SHA256 = "cca5f62db0fbb51e1bae8111ea85fe169fba7be5a8e63847a9c1c048cdae25cd"
PROTOCOL_SHA256 = "5acc611bf8bb79740a996cc7bc9bd262bc55a661373f070670da19f7aa48433b"


def run(command: list[str], *, cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=check)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def service_active(unit: str) -> str:
    result = run(["systemctl", "--user", "is-active", unit])
    return result.stdout.strip() or result.stderr.strip() or "unknown"


def check_manifest_family(name: str, errors: list[str]) -> None:
    manifest_path = output_dir / "family_manifests" / f"{name}.json"
    if not manifest_path.is_file():
        errors.append(f"missing predecessor family manifest: {manifest_path}")
        return
    manifest = read_json(manifest_path)
    spec = MODEL_SPECS[name]
    expected_fields = {
        "schema_version": "far-family-dev-family-run-v1",
        "protocol_fingerprint": PROTOCOL_SHA256,
        "family": name,
        "model": spec["model"],
        "digest": spec["digest"],
        "config_sha256": spec["config_sha256"],
        "source_commit": expected_commit,
    }
    for key, expected in expected_fields.items():
        if manifest.get(key) != expected:
            errors.append(f"{name} family manifest {key} mismatch")
    for flag in ("publication_gold", "human_iaa", "test_accessed"):
        if manifest.get(flag) is not False:
            errors.append(f"{name} family manifest {flag} must be false")
    for method in METHODS:
        run_dir = output_dir / "runs" / name / method
        checkpoint = run_dir / "checkpoint.jsonl"
        run_manifest_path = run_dir / "run_manifest.json"
        if not checkpoint.is_file():
            errors.append(f"missing checkpoint: {checkpoint}")
            continue
        rows = read_jsonl(checkpoint)
        ids = [str(row.get("sample_id", row.get("id"))) for row in rows]
        if len(rows) != 60 or len(set(ids)) != 60:
            errors.append(f"{name}/{method} checkpoint is not exactly 60 unique rows")
        if any(count > 1 for count in Counter(ids).values()):
            errors.append(f"{name}/{method} checkpoint contains duplicate sample IDs")
        if not run_manifest_path.is_file():
            errors.append(f"missing run manifest: {run_manifest_path}")
            continue
        run_manifest = read_json(run_manifest_path)
        if (
            run_manifest.get("status") != "complete"
            or run_manifest.get("completed") != 60
            or run_manifest.get("expected") != 60
            or run_manifest.get("partial") is not False
            or run_manifest.get("errors") != 0
        ):
            errors.append(f"{name}/{method} run manifest is not complete 60/60")


errors: list[str] = []
warnings: list[str] = []

if family not in ("google", "meta"):
    errors.append(f"unsupported family: {family}")

for unit in (
    "far-family-dev-mistral-resume.service",
    "far-family-dev.service",
    "far-family-dev@google.service",
    "far-family-dev@meta.service",
    "far-boundary.service",
):
    state = service_active(unit)
    if state == "active":
        errors.append(f"{unit} is active; do not start another family")

template = run(["systemctl", "--user", "cat", "far-family-dev@.service"])
if template.returncode != 0:
    errors.append("far-family-dev@.service is not installed for the user")
ollama_state = service_active("far-ollama-family-dev.service")
if require_ollama_bool and ollama_state != "active":
    errors.append("FAR_FAMILY_DEV_REQUIRE_OLLAMA=1 but far-ollama-family-dev.service is not active")

processes = run(["ps", "-eo", "pid,etime,cmd"]).stdout
for raw in processes.splitlines():
    if "grep" in raw:
        continue
    if "python -m far.experiments.family_dev" in raw:
        errors.append(f"family-dev runner already active: {raw.strip()}")
    if "train.py" in raw:
        errors.append(f"train.py process already active: {raw.strip()}")
    if "ollama serve" in raw and not require_ollama_bool:
        warnings.append(f"ollama serve is active: {raw.strip()}")

if not worktree.is_dir():
    errors.append(f"missing worktree: {worktree}")
else:
    head = run(["git", "rev-parse", "HEAD"], cwd=worktree)
    if head.returncode != 0 or head.stdout.strip() != expected_commit:
        errors.append(f"worktree HEAD is not the frozen commit {expected_commit}")
    status = run(["git", "status", "--porcelain"], cwd=worktree)
    if status.stdout.strip():
        errors.append("remote frozen worktree is dirty")

manifest_path = input_dir / "manifest.json"
if not manifest_path.is_file():
    errors.append(f"missing input manifest: {manifest_path}")
else:
    manifest = read_json(manifest_path)
    expected_input = {
        "schema_version": "far-family-dev-input-v1",
        "protocol_fingerprint": PROTOCOL_SHA256,
        "source": "bench/splits/dev.jsonl",
        "dev_sha256": DEV_SHA256,
        "corpus_sha256": CORPUS_SHA256,
        "samples": 60,
        "split": "dev",
        "contains_train": False,
        "contains_test": False,
        "test_accessed": False,
    }
    for key, expected in expected_input.items():
        if manifest.get(key) != expected:
            errors.append(f"input manifest {key} mismatch")
    files = {
        input_dir / "falsirag_bench.jsonl": DEV_SHA256,
        input_dir / "corpus.jsonl": CORPUS_SHA256,
    }
    for path, expected_sha in files.items():
        if not path.is_file():
            errors.append(f"missing input file: {path}")
        elif sha256_file(path) != expected_sha:
            errors.append(f"input fingerprint mismatch: {path}")

target_manifest = output_dir / "family_manifests" / f"{family}.json"
if target_manifest.is_file():
    errors.append(f"target family already has a completion manifest: {target_manifest}")

predecessors = FAMILY_ORDER[: FAMILY_ORDER.index(family)]
for predecessor in predecessors:
    check_manifest_family(predecessor, errors)

if family == "google" and (output_dir / "family_manifests" / "meta.json").is_file():
    errors.append("meta manifest already exists; requested google is no longer the next family")
if family == "meta" and not (output_dir / "family_manifests" / "google.json").is_file():
    errors.append("meta cannot start before google completion manifest exists")

if require_ollama_bool:
    spec = MODEL_SPECS[family]
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
            tags = json.loads(response.read().decode("utf-8"))
        records = [
            item
            for item in tags.get("models", [])
            if item.get("name") == spec["model"] or item.get("model") == spec["model"]
        ]
        if not records:
            errors.append(f"Ollama tag is unavailable: {spec['model']}")
        elif records[0].get("digest") != spec["digest"]:
            errors.append(f"Ollama digest mismatch for {spec['model']}")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        errors.append(f"could not query Ollama tags: {exc}")

result = {
    "schema_version": "far-family-dev-preflight-v1",
    "valid": not errors,
    "family": family,
    "next_action_if_valid": (
        "FAR_FAMILY_DEV_TRAINING_ALLOWED=1 "
        f"scripts/start_windows_family_dev_next.sh {family} --execute"
    ),
    "remote": {
        "output_dir": str(output_dir),
        "input_dir": str(input_dir),
        "worktree": str(worktree),
        "expected_commit": expected_commit,
        "ollama_required": require_ollama_bool,
        "ollama_state": ollama_state,
    },
    "warnings": warnings,
    "errors": errors,
}
print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
if errors:
    raise SystemExit(1)
PY
REMOTE
