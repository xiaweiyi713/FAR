#!/usr/bin/env bash
# Check cloud-backed FAR run readiness without printing or storing secrets.
#
# Usage:
#   bash scripts/check_cloud_run_readiness.sh
#   bash scripts/check_cloud_run_readiness.sh --require-keys
#   bash scripts/check_cloud_run_readiness.sh --config experiments/configs/deepseek.yaml --require-keys
#   bash scripts/check_cloud_run_readiness.sh --output-root /mnt/d/FAR-outputs --require-keys

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_ROOT="${OUTPUT_ROOT:-outputs/suites}"
VERARAG_PATH="${VERARAG_PATH:-/Users/xuwenyao/VeraRAG}"
if [[ ! -d "${VERARAG_PATH}" && -d /mnt/d/FAR-workspace/VeraRAG ]]; then
  VERARAG_PATH=/mnt/d/FAR-workspace/VeraRAG
fi
REQUIRE_KEYS=0
ALLOW_DIRTY=0
CONFIGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --require-keys)
      REQUIRE_KEYS=1
      shift
      ;;
    --config)
      if [[ $# -lt 2 ]]; then
        echo "--config requires a value" >&2
        exit 2
      fi
      CONFIGS+=("$2")
      shift 2
      ;;
    --output-root)
      if [[ $# -lt 2 ]]; then
        echo "--output-root requires a value" >&2
        exit 2
      fi
      OUTPUT_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      sed -n '1,12p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

cd "${ROOT}"

status=0

check_ok() {
  echo "ok: $*"
}

check_fail() {
  echo "fail: $*" >&2
  status=1
}

check_warn() {
  echo "warn: $*" >&2
}

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  TRACKED_STATUS="$(git status --porcelain --untracked-files=no)"
  if [[ "${ALLOW_DIRTY}" -eq 0 && -n "${TRACKED_STATUS}" ]]; then
    check_fail "tracked worktree is dirty; commit or stash before a formal cloud run"
  elif [[ "${ALLOW_DIRTY}" -eq 1 && -n "${TRACKED_STATUS}" ]]; then
    check_warn "tracked worktree is dirty; allowed for this diagnostic preflight"
  else
    check_ok "tracked worktree is clean"
  fi
elif [[ "${ALLOW_DIRTY}" -eq 1 ]]; then
  check_warn "Git metadata is unavailable; allowed only for this explicit rsync diagnostic"
else
  check_fail "Git metadata is unavailable; formal cloud runs require a recorded source revision"
fi

if [[ ! -d "${VERARAG_PATH}" ]]; then
  check_warn "VeraRAG checkout not found at ${VERARAG_PATH} on this host"
else
  check_ok "VeraRAG checkout is present at ${VERARAG_PATH}"
fi

if [[ "${#CONFIGS[@]}" -eq 0 ]]; then
  CONFIGS=(experiments/configs/deepseek.yaml experiments/configs/qwen_plus.yaml)
fi

for config in "${CONFIGS[@]}"; do
  if [[ ! -f "${config}" ]]; then
    check_fail "missing config: ${config}"
  fi
done

python3 - "$REQUIRE_KEYS" "$OUTPUT_ROOT" "${CONFIGS[@]}" <<'PY'
import os
import sys
from pathlib import Path

require_keys = bool(int(sys.argv[1]))
output_root = Path(sys.argv[2])
requested_configs = set(sys.argv[3:])

expected = {
    "experiments/configs/deepseek.yaml": {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "api_key_env": "DEEPSEEK_API_KEY",
        "cache_path": "outputs/cache/deepseek.sqlite3",
    },
    "experiments/configs/qwen_plus.yaml": {
        "provider": "dashscope",
        "model": "qwen3.7-plus-2026-05-26",
        "api_key_env": "DASHSCOPE_API_KEY",
        "cache_path": "outputs/cache/qwen_plus.sqlite3",
    },
}

status = 0
unknown_configs = sorted(requested_configs - set(expected))
if unknown_configs:
    for path in unknown_configs:
        print(f"fail: unsupported cloud preflight config: {path}", file=sys.stderr)
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"ok: {message}")


def warn(message: str) -> None:
    print(f"warn: {message}", file=sys.stderr)


def fail(message: str) -> None:
    global status
    status = 1
    print(f"fail: {message}", file=sys.stderr)


for path, checks in expected.items():
    if requested_configs and path not in requested_configs:
        continue
    data = {}
    current = None
    nested = None
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if indent == 0 and line.endswith(":"):
            current = line[:-1]
            nested = None
            data.setdefault(current, {})
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if indent == 2 and not value:
            nested = key
            data[current].setdefault(nested, {})
            continue
        target = data[current]
        if indent == 4 and nested and isinstance(target.get(nested), dict):
            target = target[nested]  # type: ignore[assignment]
        if value.lower() == "true":
            parsed: object = True
        elif value.lower() == "false":
            parsed = False
        elif value.replace(".", "", 1).isdigit():
            parsed = float(value) if "." in value else int(value)
        else:
            parsed = value.strip("\"'")
        target[key] = parsed  # type: ignore[index]

    llm = data.get("llm", {})
    retrieval = data.get("retrieval", {})
    conflict = data.get("conflict_graph", {})
    for key, value in checks.items():
        if str(llm.get(key)) != value:
            fail(f"{path}: llm.{key}={llm.get(key)!r}, expected {value!r}")
    if not llm.get("enabled"):
        fail(f"{path}: llm.enabled must be true for a cloud run")
    if retrieval.get("backend") != "vera_hybrid":
        fail(f"{path}: retrieval.backend must be vera_hybrid")
    if retrieval.get("allow_dense_fallback") is not False:
        fail(f"{path}: allow_dense_fallback must be false")
    if retrieval.get("dense", {}).get("local_files_only") is not True:
        fail(f"{path}: dense.local_files_only must be true")
    if retrieval.get("rerank", {}).get("local_files_only") is not True:
        fail(f"{path}: rerank.local_files_only must be true")
    if conflict.get("require_nli") is not True:
        fail(f"{path}: conflict_graph.require_nli must be true")
    if conflict.get("nli_local_files_only") is not True:
        fail(f"{path}: nli_local_files_only must be true")

    env_name = checks["api_key_env"]
    env_value = os.environ.get(env_name, "")
    if env_value:
        ok(f"{path}: {env_name} is set (value redacted)")
        if env_value.startswith("sk-") and len(env_value) < 24:
            fail(f"{path}: {env_name} looks too short to be a real provider key")
    elif require_keys:
        fail(f"{path}: {env_name} is not set")
    else:
        warn(f"{path}: {env_name} is not set; pass --require-keys before spending API budget")

    ok(f"{path}: provider/model/cache/retrieval/NLI checks passed")

if output_root.is_absolute() and not str(output_root).startswith("/mnt/d/"):
    warn(f"absolute output root is not under /mnt/d: {output_root}")
elif str(output_root).startswith("/mnt/c/"):
    fail(f"output root must not be on C: {output_root}")
else:
    ok(f"output root looks storage-safe: {output_root}")

raise SystemExit(status)
PY

if [[ "${OUTPUT_ROOT}" == /mnt/c/* ]]; then
  check_fail "OUTPUT_ROOT must not be on C: ${OUTPUT_ROOT}"
fi

if [[ "${OUTPUT_ROOT}" == /mnt/d/* ]]; then
  check_ok "remote output root is on D:"
elif [[ "${OUTPUT_ROOT}" == outputs/* ]]; then
  check_ok "local output root is under ignored outputs/"
else
  check_warn "output root is neither /mnt/d nor local outputs/: ${OUTPUT_ROOT}"
fi

if [[ "${status}" -ne 0 ]]; then
  exit "${status}"
fi

echo "cloud run readiness preflight passed"
