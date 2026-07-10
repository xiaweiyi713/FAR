#!/usr/bin/env bash
# Queue the complete Qwen dev suite behind an already-running FAR job.

set -euo pipefail

WAIT_FOR_SESSION="${WAIT_FOR_SESSION:-far-qwen-dev}"
FAR_ROOT="${FAR_ROOT:-/mnt/d/FAR-workspace/FAR}"
UPSTREAM_FAR_RUN="${UPSTREAM_FAR_RUN:-/mnt/d/FAR-outputs/qwen_open_dev}"
SUITE_ROOT="${SUITE_ROOT:-/mnt/d/FAR-outputs/qwen_open_dev_suite}"
POLL_SECONDS="${POLL_SECONDS:-30}"

if [[ ! -d "${FAR_ROOT}" ]]; then
  echo "FAR workspace not found: ${FAR_ROOT}" >&2
  exit 2
fi

source "${HOME}/miniconda3/etc/profile.d/conda.sh"
conda activate train
cd "${FAR_ROOT}"
source scripts/windows_gpu_env.sh

echo "waiting for tmux session: ${WAIT_FOR_SESSION}"
while tmux has-session -t "${WAIT_FOR_SESSION}" 2>/dev/null; do
  sleep "${POLL_SECONDS}"
done

python - "${UPSTREAM_FAR_RUN}/run_manifest.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(f"upstream FAR manifest is missing: {path}")
manifest = json.loads(path.read_text(encoding="utf-8"))
if manifest.get("status") != "complete" or manifest.get("partial"):
    raise SystemExit(f"upstream FAR run is not complete: {manifest}")
if manifest.get("split") != "dev" or manifest.get("method") != "far":
    raise SystemExit(f"unexpected upstream FAR identity: {manifest}")
print(
    "upstream FAR verified:",
    manifest["completed"],
    manifest["predictions_sha256"],
)
PY

mkdir -p "${SUITE_ROOT}/runs"
FAR_LINK="${SUITE_ROOT}/runs/far"
if [[ -L "${FAR_LINK}" ]]; then
  if [[ "$(readlink -f "${FAR_LINK}")" != "$(readlink -f "${UPSTREAM_FAR_RUN}")" ]]; then
    echo "existing FAR link targets a different run: ${FAR_LINK}" >&2
    exit 2
  fi
elif [[ -e "${FAR_LINK}" ]]; then
  echo "refusing to replace existing non-symlink path: ${FAR_LINK}" >&2
  exit 2
else
  ln -s "${UPSTREAM_FAR_RUN}" "${FAR_LINK}"
fi

echo "starting complete Qwen dev suite at ${SUITE_ROOT}"
CUDA_VISIBLE_DEVICES= falsirag-suite \
  --config far/experiments/configs/qwen_open.yaml \
  --data-dir bench \
  --output-dir "${SUITE_ROOT}" \
  --split dev
echo "complete Qwen dev suite finished"
