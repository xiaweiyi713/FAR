#!/usr/bin/env bash
# Report status for the D:-backed Windows/WSL Qwen suite.
#
# Intended to be run on the `windows-gpu` WSL host. From the Mac:
#   ssh windows-gpu 'bash /mnt/d/FAR-workspace/FAR/scripts/check_windows_qwen_suite.sh'

set -euo pipefail

OUTPUT_ROOT="${OUTPUT_ROOT:-/mnt/d/FAR-outputs}"
LATEST_PATH_FILE="${LATEST_PATH_FILE:-${OUTPUT_ROOT}/latest_far_corrected_suite_path.txt}"
TAIL_LINES="${TAIL_LINES:-80}"

if [[ -n "${SUITE_ROOT:-}" ]]; then
  RUN_ROOT="${SUITE_ROOT}"
elif [[ -f "${LATEST_PATH_FILE}" ]]; then
  RUN_ROOT="$(<"${LATEST_PATH_FILE}")"
else
  echo "No SUITE_ROOT provided and latest path file is missing: ${LATEST_PATH_FILE}" >&2
  exit 2
fi

echo "time: $(date -Is)"
echo "suite_root: ${RUN_ROOT}"
echo "latest_path_file: ${LATEST_PATH_FILE}"

echo
echo "tmux sessions:"
tmux ls 2>/dev/null || true

echo
echo "FAR/Ollama processes:"
pgrep -af "[f]alsirag-suite|[o]llama" || true

echo
echo "checkpoint counts:"
find "${RUN_ROOT}/runs" -name checkpoint.jsonl -print -exec wc -l {} \; 2>/dev/null || true

echo
echo "run manifests:"
find "${RUN_ROOT}/runs" -maxdepth 2 -name run_manifest.json -print0 2>/dev/null |
  while IFS= read -r -d '' manifest; do
    python - "${manifest}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
summary = {
    "path": str(path),
    "method": data.get("method"),
    "split": data.get("split"),
    "status": data.get("status"),
    "completed": data.get("completed"),
    "total": data.get("total"),
    "partial": data.get("partial"),
    "errors": data.get("errors"),
    "predictions_sha256": data.get("predictions_sha256"),
}
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
PY
  done

echo
echo "latest log tail:"
tail -n "${TAIL_LINES}" "${RUN_ROOT}.log" 2>/dev/null || true

echo
echo "gpu:"
/usr/lib/wsl/lib/nvidia-smi \
  --query-gpu=utilization.gpu,memory.used,memory.total \
  --format=csv,noheader 2>/dev/null || true

echo
echo "disk:"
df -h /mnt/c /mnt/d 2>/dev/null || true
