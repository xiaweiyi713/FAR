#!/usr/bin/env bash
# Start or resume the D:-backed RAMDocs dev Round 2 FAR-only run on Windows/WSL.
#
# This launcher is intentionally conservative: it creates the Round 2 keep-running
# marker, but if another workload is using the GPU it only records
# ramdocs_dev_v2.waiting-for-gpu and exits without starting FAR/Ollama. The
# Windows watchdog can then resume the same checkpoint when the GPU is idle.

set -euo pipefail

FAR_ROOT="${FAR_ROOT:-/mnt/d/FAR-workspace/FAR-2plus4}"
OLLAMA_UNIT="${OLLAMA_UNIT:-far-ollama-2plus4.service}"
ROUND2_UNIT="${ROUND2_UNIT:-far-ramdocs-round2.service}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/mnt/d/FAR-outputs}"
OUTPUT_DIR="${OUTPUT_ROOT}/ramdocs_dev_v2"
ROUND1_DIR="${OUTPUT_ROOT}/ramdocs_dev_v1"
RUN_DIR="${OUTPUT_DIR}/runs/far"
RUN_MARKER="/mnt/d/FAR-runtime/ramdocs_dev_v2.keep-running"
WAITING_MARKER="/mnt/d/FAR-runtime/ramdocs_dev_v2.waiting-for-gpu"
WATCHDOG_LOG="${OUTPUT_DIR}.watchdog.log"
NVIDIA_SMI="${NVIDIA_SMI:-/usr/lib/wsl/lib/nvidia-smi}"
MAX_IDLE_MEMORY_MIB="${MAX_IDLE_MEMORY_MIB:-1500}"
MAX_IDLE_UTILIZATION_PCT="${MAX_IDLE_UTILIZATION_PCT:-20}"
POLL_SECONDS="${POLL_SECONDS:-2}"
API_TIMEOUT_SECONDS="${API_TIMEOUT_SECONDS:-5}"

if [[ ! -d "${FAR_ROOT}" ]]; then
  echo "FAR workspace not found: ${FAR_ROOT}" >&2
  exit 2
fi

source "${HOME}/miniconda3/etc/profile.d/conda.sh"
conda activate train
cd "${FAR_ROOT}"
source scripts/windows_gpu_env.sh
mkdir -p "${OUTPUT_ROOT}" "${RUN_DIR}" "$(dirname "${RUN_MARKER}")"

current_commit="$(git rev-parse HEAD)"
dirty_status="$(git status --porcelain --untracked-files=all)"
if [[ -f "${RUN_DIR}/run_identity.json" ]]; then
  stored_commit="$(
    python3 - "${RUN_DIR}/run_identity.json" <<'PY'
import json
import sys
from pathlib import Path

identity = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print((identity.get("source_revision") or {}).get("git_commit") or "")
PY
  )"
  if [[ -n "${stored_commit}" && "${stored_commit}" != "${current_commit}" ]]; then
    cat >&2 <<EOF
refusing to resume Round 2 from a different Git commit.
  existing run commit: ${stored_commit}
  current checkout:     ${current_commit}
Use the original detached checkout for this checkpoint, or start a new output
directory after recording a new method-iteration round.
EOF
    exit 2
  fi
fi
if [[ -n "${dirty_status}" ]]; then
  cat >&2 <<EOF
refusing to start a formal RAMDocs Round 2 run from a dirty worktree.
The run identity binds the Git revision and dirty state; clean or stash local
changes before starting/resuming this checkpoint.
EOF
  exit 2
fi

if [[ ! -f "${ROUND1_DIR}/suite_manifest.json" ]]; then
  echo "Round 1 suite manifest is required before Round 2: ${ROUND1_DIR}/suite_manifest.json" >&2
  exit 2
fi

if [[ -f "${RUN_DIR}/run_manifest.json" ]]; then
  echo "Round 2 FAR run already has a manifest: ${RUN_DIR}/run_manifest.json"
  rm -f "${RUN_MARKER}" "${WAITING_MARKER}"
  exit 0
fi

linger="$(loginctl show-user "${USER}" -p Linger --value 2>/dev/null || true)"
if [[ "${linger}" != "yes" ]]; then
  cat >&2 <<EOF
systemd linger is not enabled for ${USER}; user services may be interrupted after
the last SSH session disconnects. From Windows PowerShell run:
  wsl.exe -d Ubuntu-24.04 -u root -- loginctl enable-linger ${USER}
Then rerun this launcher.
EOF
  exit 2
fi

missing=()
for unit in "${OLLAMA_UNIT}" "${ROUND2_UNIT}"; do
  if ! systemctl --user cat "${unit}" >/dev/null 2>&1; then
    missing+=("${unit}")
  fi
done
if (( ${#missing[@]} )); then
  cat >&2 <<EOF
required systemd user units are not installed: ${missing[*]}
Install them once with:
  mkdir -p ~/.config/systemd/user
  cp scripts/systemd/far-ollama-2plus4.service ~/.config/systemd/user/
  cp scripts/systemd/far-ramdocs-round2.service ~/.config/systemd/user/
  systemctl --user daemon-reload
Then rerun this launcher.
EOF
  exit 2
fi

touch "${RUN_MARKER}"

ollama_active="$(systemctl --user is-active "${OLLAMA_UNIT}" 2>/dev/null || true)"
round2_active="$(systemctl --user is-active "${ROUND2_UNIT}" 2>/dev/null || true)"
if [[ "${ollama_active}" == "active" && "${round2_active}" == "active" ]]; then
  rm -f "${WAITING_MARKER}"
  systemctl --user --no-pager --full status "${OLLAMA_UNIT}" "${ROUND2_UNIT}" || true
  exit 0
fi

if [[ "${ollama_active}" != "active" ]]; then
  memory_used="99999"
  utilization="100"
  if [[ -x "${NVIDIA_SMI}" ]]; then
    IFS=, read -r memory_used utilization < <(
      "${NVIDIA_SMI}" \
        --query-gpu=memory.used,utilization.gpu \
        --format=csv,noheader,nounits 2>/dev/null | head -n 1
    )
    memory_used="${memory_used//[[:space:]]/}"
    utilization="${utilization//[[:space:]]/}"
  fi
  if ! [[ "${memory_used}" =~ ^[0-9]+$ && "${utilization}" =~ ^[0-9]+$ ]] \
    || (( memory_used > MAX_IDLE_MEMORY_MIB || utilization > MAX_IDLE_UTILIZATION_PCT )); then
    printf '%s waiting_for_gpu memory_used_mib=%s utilization_pct=%s\n' \
      "$(date --iso-8601=seconds)" "${memory_used}" "${utilization}" \
      >> "${WATCHDOG_LOG}"
    touch "${WAITING_MARKER}"
    echo "GPU is busy; Round 2 marker is set and FAR was not started."
    echo "memory_used_mib=${memory_used} utilization_pct=${utilization}"
    exit 0
  fi
fi

rm -f "${WAITING_MARKER}"
systemctl --user enable --now "${OLLAMA_UNIT}"
until curl -fsS --max-time "${API_TIMEOUT_SECONDS}" "http://${OLLAMA_HOST}/api/tags" >/dev/null; do
  sleep "${POLL_SECONDS}"
done

echo "starting/resuming RAMDocs Round 2 as systemd user service: ${ROUND2_UNIT}"
echo "checkpoint: ${RUN_DIR}/checkpoint.jsonl"
echo "log: ${OUTPUT_DIR}.log"
echo "commit: ${current_commit}"
systemctl --user enable --now "${ROUND2_UNIT}"
systemctl --user --no-pager --full status "${OLLAMA_UNIT}" "${ROUND2_UNIT}" || true
