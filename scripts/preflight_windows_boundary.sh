#!/usr/bin/env bash
# Fail-closed, read-only preflight for WS3 boundary mapping on windows-gpu.
#
# This script does not start/stop systemd units, run predictions, inspect any
# held-out/test split, or write remote files. It verifies that the D:-backed
# worktree/output can safely start or resume the preregistered WS3 boundary run.
#
# Usage:
#   scripts/preflight_windows_boundary.sh
#   FAR_BOUNDARY_REQUIRE_OLLAMA=1 scripts/preflight_windows_boundary.sh

set -euo pipefail

remote="${1:-${FAR_WINDOWS_REMOTE:-windows-gpu}}"
output_dir="${FAR_BOUNDARY_OUTPUT_DIR:-/mnt/d/FAR-outputs/boundary_v1}"
worktree="${FAR_BOUNDARY_WORKTREE:-/mnt/d/FAR-workspace/FAR-longterm}"
require_ollama="${FAR_BOUNDARY_REQUIRE_OLLAMA:-0}"

if [[ -n "${FAR_BOUNDARY_EXPECTED_COMMIT:-}" ]]; then
  expected_commit="${FAR_BOUNDARY_EXPECTED_COMMIT}"
else
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  expected_commit="$(git -C "${script_dir}/.." rev-parse HEAD)"
fi

ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- \
  "${output_dir}" "${worktree}" "${expected_commit}" "${require_ollama}" <<'REMOTE'
set -euo pipefail

output_dir="$1"
worktree="$2"
expected_commit="$3"
require_ollama="$4"

python3 - "$output_dir" "$worktree" "$expected_commit" "$require_ollama" <<'PY'
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

output_dir_text, worktree_text, expected_commit, require_ollama = sys.argv[1:5]
output_dir = Path(output_dir_text)
worktree = Path(worktree_text)
require_ollama_bool = require_ollama == "1"

BOUNDARY_PLAN_SHA256 = "a8aa260aec7b92f2d51bc4c14ce78b0f355b2b61e543c5ace0cff52c5c1d34a3"
CONFIG_SHA256 = "d3a36b59d02eb4c086e87445d0757d466a25e9f3d2428d4bdc9a36bae9acc979"
QWEN_MODEL = "qwen3.5:9b"
QWEN_DIGEST = "6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7"
DATASETS: dict[str, dict[str, Any]] = {
    "wikicontradict": {
        "path": "bench/external/wikicontradict_v1",
        "kind": "wiki",
        "manifest_sha256": "b3b3b80c44600579e15cfe4e9071040cfd99cc3d49ed716ee9dd603435a07765",
        "benchmark": "wikicontradict",
    },
    "rag_conflicts": {
        "path": "bench/external/rag_conflicts_v1",
        "kind": "conflicts",
        "manifest_sha256": "ec12941a2e98461219858d56a6a07545ba4d5ac70eca96dac2f6148b4ccb86e5",
        "benchmark": "google_rag_conflicts",
    },
}
METHODS = ("far", "far_minus_typed_conflict")


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


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


def completed_run(path: Path, *, expected: int, partial: bool) -> bool:
    manifest_path = path / "run_manifest.json"
    predictions_path = path / "predictions.jsonl"
    if not manifest_path.is_file() or not predictions_path.is_file():
        return False
    try:
        manifest = read_json(manifest_path)
    except (OSError, json.JSONDecodeError):
        return False
    return (
        manifest.get("status") == "complete"
        and int(manifest.get("completed", -1)) == expected
        and int(manifest.get("errors", -1)) == 0
        and bool(manifest.get("partial")) is partial
        and predictions_path.is_file()
        and sha256_file(predictions_path) == manifest.get("predictions_sha256")
    )


errors: list[str] = []
warnings: list[str] = []

states = {
    unit: service_active(unit)
    for unit in (
        "far-boundary.service",
        "far-ollama-boundary.service",
        "far-family-dev@google.service",
        "far-family-dev@meta.service",
        "far-family-dev-mistral-resume.service",
        "far-family-dev.service",
        "far-ollama-family-dev.service",
    )
}
for unit in (
    "far-boundary.service",
    "far-family-dev@google.service",
    "far-family-dev@meta.service",
    "far-family-dev-mistral-resume.service",
    "far-family-dev.service",
):
    if states[unit] == "active":
        errors.append(f"{unit} is active; do not start WS3 boundary")

for unit in ("far-boundary.service", "far-ollama-boundary.service"):
    template = run(["systemctl", "--user", "cat", unit])
    if template.returncode != 0:
        errors.append(f"{unit} is not installed for the user")

if require_ollama_bool and states["far-ollama-boundary.service"] != "active":
    errors.append("FAR_BOUNDARY_REQUIRE_OLLAMA=1 but far-ollama-boundary.service is not active")

processes = run(["ps", "-eo", "pid,etime,cmd"]).stdout
for raw in processes.splitlines():
    if "grep" in raw:
        continue
    if "python -m experiments.boundary" in raw:
        errors.append(f"boundary runner already active: {raw.strip()}")
    if "python -m experiments.family_dev" in raw:
        errors.append(f"family-dev runner already active: {raw.strip()}")
    if "train.py" in raw:
        errors.append(f"train.py process already active: {raw.strip()}")
    if "ollama serve" in raw and not require_ollama_bool:
        warnings.append(f"ollama serve is active: {raw.strip()}")

if not worktree.is_dir():
    errors.append(f"missing worktree: {worktree}")
else:
    head = run(["git", "rev-parse", "HEAD"], cwd=worktree)
    origin = run(["git", "rev-parse", "origin/main"], cwd=worktree)
    status = run(["git", "status", "--porcelain"], cwd=worktree)
    if head.returncode != 0:
        errors.append("could not read remote worktree HEAD")
    elif head.stdout.strip() != expected_commit:
        errors.append(f"worktree HEAD is not expected commit {expected_commit}")
    if origin.returncode != 0:
        errors.append("could not read remote origin/main")
    elif origin.stdout.strip() != expected_commit:
        errors.append(f"remote origin/main is not expected commit {expected_commit}")
    if status.stdout.strip():
        errors.append("remote boundary worktree is dirty")
    files = {
        "docs/PLAN_BOUNDARY_MAPPING.md": BOUNDARY_PLAN_SHA256,
        "experiments/configs/qwen_boundary.yaml": CONFIG_SHA256,
    }
    for relative, expected_sha in files.items():
        path = worktree / relative
        if not path.is_file():
            errors.append(f"missing frozen file: {path}")
        elif sha256_file(path) != expected_sha:
            errors.append(f"fingerprint mismatch: {path}")
    for dataset, spec in DATASETS.items():
        data_dir = worktree / str(spec["path"])
        manifest_path = data_dir / "manifest.json"
        tasks_path = data_dir / "tasks.jsonl"
        corpus_path = data_dir / "corpus.jsonl"
        if not manifest_path.is_file():
            errors.append(f"missing {dataset} manifest: {manifest_path}")
            continue
        if sha256_file(manifest_path) != spec["manifest_sha256"]:
            errors.append(f"{dataset} import manifest fingerprint mismatch")
        try:
            manifest = read_json(manifest_path)
        except json.JSONDecodeError as exc:
            errors.append(f"{dataset} manifest invalid: {exc}")
            continue
        expected_fields = {
            "kind": spec["kind"],
            "samples": 150,
            "split": "dev",
            "test_accessed": False,
        }
        for key, expected in expected_fields.items():
            if manifest.get(key) != expected:
                errors.append(f"{dataset} manifest {key} mismatch")
        for path in (tasks_path, corpus_path):
            if not path.is_file():
                errors.append(f"missing {dataset} input file: {path}")
        if tasks_path.is_file():
            rows = read_jsonl(tasks_path)
            if len(rows) != 150 or {str(row.get("split")) for row in rows} != {"dev"}:
                errors.append(f"{dataset} tasks must contain exactly 150 dev rows")
            if {str(row.get("benchmark")) for row in rows} != {str(spec["benchmark"])}:
                errors.append(f"{dataset} benchmark field mismatch")

release_manifest = output_dir / "manifest.json"
if release_manifest.is_file():
    errors.append(f"boundary release is already finalized: {release_manifest}")

if output_dir.exists():
    for dataset in DATASETS:
        for method in METHODS:
            calibration_dir = output_dir / "calibration" / dataset / method
            formal_dir = output_dir / "runs" / dataset / method
            if (calibration_dir / "run_manifest.json").is_file() and not completed_run(
                calibration_dir, expected=5, partial=True
            ):
                warnings.append(f"incomplete or non-final calibration checkpoint: {calibration_dir}")
            if (formal_dir / "run_manifest.json").is_file() and not completed_run(
                formal_dir, expected=150, partial=False
            ):
                warnings.append(f"incomplete or non-final formal checkpoint: {formal_dir}")

if require_ollama_bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
            tags = json.loads(response.read().decode("utf-8"))
        records = [
            item
            for item in tags.get("models", [])
            if item.get("name") == QWEN_MODEL or item.get("model") == QWEN_MODEL
        ]
        if not records:
            errors.append(f"Ollama tag is unavailable: {QWEN_MODEL}")
        elif records[0].get("digest") != QWEN_DIGEST:
            errors.append(f"Ollama digest mismatch for {QWEN_MODEL}")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        errors.append(f"could not query Ollama tags: {exc}")

result = {
    "schema_version": "far-boundary-preflight-v1",
    "valid": not errors,
    "next_action_if_valid": (
        "FAR_BOUNDARY_TRAINING_ALLOWED=1 "
        "scripts/start_windows_boundary.sh --execute"
    ),
    "remote": {
        "output_dir": str(output_dir),
        "worktree": str(worktree),
        "expected_commit": expected_commit,
        "ollama_required": require_ollama_bool,
        "service_states": states,
    },
    "warnings": warnings,
    "errors": errors,
}
print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
if errors:
    raise SystemExit(1)
PY
REMOTE
