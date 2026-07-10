#!/usr/bin/env bash
# Start the D:-backed Windows/WSL Qwen open-model suite safely.
#
# Intended to be run on the `windows-gpu` WSL host. It keeps Ollama, model
# caches, workspace, logs, and result bundles under /mnt/d via
# scripts/windows_gpu_env.sh.

set -euo pipefail

FAR_ROOT="${FAR_ROOT:-/mnt/d/FAR-workspace/FAR}"
OLLAMA_SESSION="${OLLAMA_SESSION:-far-ollama}"
SUITE_SESSION="${SUITE_SESSION:-far-qwen-suite}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/mnt/d/FAR-outputs}"
CONFIG="${CONFIG:-far/experiments/configs/qwen_open.yaml}"
DATA_DIR="${DATA_DIR:-bench}"
SPLIT="${SPLIT:-dev}"
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
mkdir -p "${OUTPUT_ROOT}"

if ! curl -fsS --max-time "${API_TIMEOUT_SECONDS}" "http://${OLLAMA_HOST}/api/tags" >/dev/null; then
  if tmux has-session -t "${OLLAMA_SESSION}" 2>/dev/null; then
    echo "Ollama tmux session exists but API is not ready: ${OLLAMA_SESSION}" >&2
  else
    echo "starting Ollama in tmux session: ${OLLAMA_SESSION}"
    tmux new-session -d -s "${OLLAMA_SESSION}" \
      "bash -lc 'source ~/miniconda3/etc/profile.d/conda.sh; conda activate train; cd ${FAR_ROOT}; source scripts/windows_gpu_env.sh; exec ollama serve >> ${OUTPUT_ROOT}/far-ollama.log 2>&1'"
  fi

  until curl -fsS --max-time "${API_TIMEOUT_SECONDS}" "http://${OLLAMA_HOST}/api/tags" >/dev/null; do
    sleep "${POLL_SECONDS}"
  done
fi

if tmux has-session -t "${SUITE_SESSION}" 2>/dev/null; then
  echo "suite tmux session already exists: ${SUITE_SESSION}" >&2
  exit 2
fi

if [[ -z "${SUITE_ROOT:-}" ]]; then
  SUITE_ROOT="${OUTPUT_ROOT}/qwen_open_dev_suite_corrected_96e32b7_restart_$(date +%Y%m%d_%H%M%S)"
fi
SUITE_LOG="${SUITE_LOG:-${SUITE_ROOT}.log}"
LATEST_PATH_FILE="${LATEST_PATH_FILE:-${OUTPUT_ROOT}/latest_far_corrected_suite_path.txt}"

printf '%s\n' "${SUITE_ROOT}" > "${LATEST_PATH_FILE}"
echo "starting suite in tmux session: ${SUITE_SESSION}"
echo "suite root: ${SUITE_ROOT}"
echo "suite log: ${SUITE_LOG}"

tmux new-session -d -s "${SUITE_SESSION}" \
  "bash -lc 'source ~/miniconda3/etc/profile.d/conda.sh; conda activate train; cd ${FAR_ROOT}; source scripts/windows_gpu_env.sh; echo FAR_SUITE_START \$(date -Is) output=${SUITE_ROOT}; CUDA_VISIBLE_DEVICES= falsirag-suite --config ${CONFIG} --data-dir ${DATA_DIR} --output-dir ${SUITE_ROOT} --split ${SPLIT}' >> '${SUITE_LOG}' 2>&1"

tmux list-sessions
echo "latest path file: ${LATEST_PATH_FILE}"
