#!/usr/bin/env bash
# Start or resume the D:-backed RAMDocs Phase A suite on the Windows/WSL GPU host.
#
# Intended to be run on `windows-gpu` inside WSL. The RAMDocs runner is
# checkpointed, so reusing the same output directory resumes incomplete methods
# and skips completed samples. This script deliberately sources
# scripts/windows_gpu_env.sh both for the parent shell and inside tmux so manual
# recovery cannot silently fall back to C: or miss the pinned HuggingFace cache.

set -euo pipefail

FAR_ROOT="${FAR_ROOT:-/mnt/d/FAR-workspace/FAR-2plus4}"
OLLAMA_SESSION="${OLLAMA_SESSION:-far-ollama-2plus4}"
SUITE_SESSION="${SUITE_SESSION:-far-ramdocs-phase-a}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/mnt/d/FAR-outputs}"
OUTPUT_DIR="${OUTPUT_DIR:-${OUTPUT_ROOT}/ramdocs_dev_v1}"
SUITE_LOG="${SUITE_LOG:-${OUTPUT_DIR}.log}"
CONFIG="${CONFIG:-experiments/configs/ramdocs_qwen.yaml}"
DATA_DIR="${DATA_DIR:-bench/external/ramdocs_v1}"
SPLIT="${SPLIT:-dev}"
POLL_SECONDS="${POLL_SECONDS:-2}"
API_TIMEOUT_SECONDS="${API_TIMEOUT_SECONDS:-5}"
TMUX_SERVER_UNIT="${TMUX_SERVER_UNIT:-far-tmux-server.service}"

if [[ ! -d "${FAR_ROOT}" ]]; then
  echo "FAR workspace not found: ${FAR_ROOT}" >&2
  exit 2
fi

source "${HOME}/miniconda3/etc/profile.d/conda.sh"
conda activate train
cd "${FAR_ROOT}"
source scripts/windows_gpu_env.sh
mkdir -p "${OUTPUT_ROOT}" "$(dirname "${SUITE_LOG}")"

linger="$(loginctl show-user "${USER}" -p Linger --value 2>/dev/null || true)"
if [[ "${linger}" != "yes" ]]; then
  cat >&2 <<EOF
systemd linger is not enabled for ${USER}; detached tmux jobs may be interrupted
after the last SSH session disconnects. From Windows PowerShell run:
  wsl.exe -d Ubuntu-24.04 -u root -- loginctl enable-linger ${USER}
Then rerun this launcher.
EOF
  exit 2
fi

if ! systemctl --user is-active --quiet "${TMUX_SERVER_UNIT}"; then
  if ! systemctl --user cat "${TMUX_SERVER_UNIT}" >/dev/null 2>&1; then
    cat >&2 <<EOF
the persistent tmux server unit is not installed. Install it once with:
  mkdir -p ~/.config/systemd/user
  cp scripts/systemd/far-tmux-server.service ~/.config/systemd/user/
  systemctl --user daemon-reload
  systemctl --user enable --now far-tmux-server.service
Then rerun this launcher.
EOF
    exit 2
  fi
  systemctl --user start "${TMUX_SERVER_UNIT}"
fi

if ! curl -fsS --max-time "${API_TIMEOUT_SECONDS}" "http://${OLLAMA_HOST}/api/tags" >/dev/null; then
  if tmux has-session -t "${OLLAMA_SESSION}" 2>/dev/null; then
    echo "Ollama tmux session exists but API is not ready: ${OLLAMA_SESSION}" >&2
  else
    echo "starting Ollama in tmux session: ${OLLAMA_SESSION}"
    tmux new-session -d -s "${OLLAMA_SESSION}" \
      "bash -lc 'source ~/miniconda3/etc/profile.d/conda.sh; conda activate train; cd ${FAR_ROOT}; source scripts/windows_gpu_env.sh; echo OLLAMA_START \$(date -Is) models=\${OLLAMA_MODELS}; exec ollama serve >> ${OUTPUT_ROOT}/far-ollama-2plus4.log 2>&1'"
  fi

  until curl -fsS --max-time "${API_TIMEOUT_SECONDS}" "http://${OLLAMA_HOST}/api/tags" >/dev/null; do
    sleep "${POLL_SECONDS}"
  done
fi

if tmux has-session -t "${SUITE_SESSION}" 2>/dev/null; then
  echo "RAMDocs suite tmux session already exists: ${SUITE_SESSION}" >&2
  exit 2
fi

echo "starting/resuming RAMDocs suite in tmux session: ${SUITE_SESSION}"
echo "output dir: ${OUTPUT_DIR}"
echo "suite log: ${SUITE_LOG}"
echo "commit: $(git rev-parse HEAD)"

tmux new-session -d -s "${SUITE_SESSION}" \
  "bash -lc 'source ~/miniconda3/etc/profile.d/conda.sh; conda activate train; cd ${FAR_ROOT}; source scripts/windows_gpu_env.sh; echo RAMDOCS_SUITE_START \$(date -Is) commit=\$(git rev-parse HEAD) output=${OUTPUT_DIR} HF_HOME=\${HF_HOME} HUGGINGFACE_HUB_CACHE=\${HUGGINGFACE_HUB_CACHE} OLLAMA_MODELS=\${OLLAMA_MODELS}; python -m experiments.ramdocs_suite run --config ${CONFIG} --data-dir ${DATA_DIR} --output-dir ${OUTPUT_DIR} --split ${SPLIT}; status=\$?; echo RAMDOCS_SUITE_EXIT \$(date -Is) status=\$status; exit \$status' >> '${SUITE_LOG}' 2>&1"

tmux list-sessions
