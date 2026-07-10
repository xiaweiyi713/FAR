#!/usr/bin/env bash
set -euo pipefail

FAR_ROOT="${FAR_ROOT:-/mnt/d/FAR-workspace/FAR}"
LATEST_PATH_FILE="${LATEST_PATH_FILE:-/mnt/d/FAR-outputs/latest_far_corrected_suite_path.txt}"
WAIT_FOR_SESSION="${WAIT_FOR_SESSION:-far-qwen-suite-v3}"
POLL_SECONDS="${POLL_SECONDS:-60}"

if [[ ! -f "${LATEST_PATH_FILE}" ]]; then
  echo "missing corrected-suite path marker: ${LATEST_PATH_FILE}" >&2
  exit 1
fi
SUITE_ROOT="${SUITE_ROOT:-$(<"${LATEST_PATH_FILE}")}"
if [[ "${SUITE_ROOT}" != /mnt/d/* ]]; then
  echo "refusing non-D: suite root: ${SUITE_ROOT}" >&2
  exit 1
fi

source "${HOME}/miniconda3/etc/profile.d/conda.sh"
conda activate train
source "${FAR_ROOT}/scripts/windows_gpu_env.sh"
cd "${FAR_ROOT}"

echo "waiting for tmux session ${WAIT_FOR_SESSION} before adding CounterRefine baseline"
while tmux has-session -t "${WAIT_FOR_SESSION}" 2>/dev/null; do
  sleep "${POLL_SECONDS}"
done

python - "${SUITE_ROOT}/suite_manifest.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(f"source suite did not finish cleanly; missing {path}")
manifest = json.loads(path.read_text(encoding="utf-8"))
expected = {
    "far",
    "minus_typed_conflict",
    "minus_refutation_query",
    "minus_boundary_query",
    "minus_typed_revision",
    "vanilla_rag",
    "multi_query_rag",
    "reflective_rag",
    "crag_style_reproduction",
    "self_rag_style_reproduction",
}
runs = manifest.get("run_manifests", {})
missing = sorted(expected - set(runs))
invalid = sorted(
    label
    for label in expected & set(runs)
    if runs[label].get("completed") != 60 or runs[label].get("partial") is not False
)
if missing or invalid:
    raise SystemExit(f"source suite is incomplete; missing={missing}, invalid={invalid}")
print("source suite complete: FAR + four ablations + original five baselines")
PY

falsirag-baselines \
  --config far/experiments/configs/qwen_open.yaml \
  --data-dir bench \
  --output-dir "${SUITE_ROOT}/runs/baselines" \
  --method counterrefine_style_reproduction \
  --split dev

python - "${SUITE_ROOT}/runs/baselines/counterrefine_style_reproduction/run_manifest.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
manifest = json.loads(path.read_text(encoding="utf-8"))
checks = {
    "method": manifest.get("method") == "counterrefine_style_reproduction",
    "status": manifest.get("status") == "complete",
    "completed": manifest.get("completed") == 60,
    "errors": manifest.get("errors") == 0,
    "partial": manifest.get("partial") is False,
}
failed = sorted(name for name, passed in checks.items() if not passed)
if failed:
    raise SystemExit(f"CounterRefine run failed completion checks: {failed}")
print(f"CounterRefine complete: {manifest.get('predictions_sha256')}")
PY

falsirag-suite \
  --config far/experiments/configs/qwen_open.yaml \
  --data-dir bench \
  --output-dir "${SUITE_ROOT}" \
  --split dev \
  --reports-only

echo "six-baseline Qwen reports-only merge complete: ${SUITE_ROOT}"
