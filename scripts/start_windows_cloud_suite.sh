#!/usr/bin/env bash
# Start a D:-backed Windows/WSL cloud-model FAR suite safely.
#
# Intended to be run on the `windows-gpu` WSL host after rotated cloud
# credentials are exported in the current shell. It avoids printing key values,
# keeps logs/results under /mnt/d, and refuses to overlap with an active
# local-Qwen suite unless ALLOW_CONCURRENT=1 is set.

set -euo pipefail

FAR_ROOT="${FAR_ROOT:-/mnt/d/FAR-workspace/FAR}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/mnt/d/FAR-outputs}"
CONFIG="${CONFIG:-far/experiments/configs/deepseek.yaml}"
DATA_DIR="${DATA_DIR:-bench}"
SPLIT="${SPLIT:-dev}"
ALLOW_CONCURRENT="${ALLOW_CONCURRENT:-0}"
ALLOW_DIRTY="${ALLOW_DIRTY:-0}"

if [[ ! -d "${FAR_ROOT}" ]]; then
  echo "FAR workspace not found: ${FAR_ROOT}" >&2
  exit 2
fi

if [[ "${OUTPUT_ROOT}" != /mnt/d/* ]]; then
  echo "cloud suite output root must be on D: under /mnt/d, got: ${OUTPUT_ROOT}" >&2
  exit 2
fi

source "${HOME}/miniconda3/etc/profile.d/conda.sh"
conda activate train
cd "${FAR_ROOT}"
source scripts/windows_gpu_env.sh

case "${CONFIG}" in
  far/experiments/configs/deepseek.yaml)
    REQUIRED_ENV=DEEPSEEK_API_KEY
    SUITE_NAME=deepseek
    ;;
  far/experiments/configs/qwen_plus.yaml)
    REQUIRED_ENV=DASHSCOPE_API_KEY
    SUITE_NAME=qwen_plus
    ;;
  *)
    echo "unsupported cloud config for guarded starter: ${CONFIG}" >&2
    echo "expected far/experiments/configs/deepseek.yaml or far/experiments/configs/qwen_plus.yaml" >&2
    exit 2
    ;;
esac

PREFLIGHT_ARGS=(--config "${CONFIG}" --output-root "${OUTPUT_ROOT}" --require-keys)
if [[ "${ALLOW_DIRTY}" == "1" ]]; then
  PREFLIGHT_ARGS+=(--allow-dirty)
fi
bash scripts/check_cloud_run_readiness.sh "${PREFLIGHT_ARGS[@]}"

if [[ "${ALLOW_CONCURRENT}" != "1" ]]; then
  if pgrep -af "[f]alsirag-suite|[l]lama-server" >/dev/null; then
    echo "active FAR suite or Ollama llama-server detected; refusing concurrent cloud run" >&2
    echo "wait for the current suite to finish, or set ALLOW_CONCURRENT=1 intentionally" >&2
    pgrep -af "[f]alsirag-suite|[l]lama-server" >&2 || true
    exit 2
  fi
fi

if [[ -z "${!REQUIRED_ENV:-}" ]]; then
  echo "${REQUIRED_ENV} is not set" >&2
  exit 2
fi

SUITE_SESSION="${SUITE_SESSION:-far-cloud-${SUITE_NAME}-${SPLIT}}"
if tmux has-session -t "${SUITE_SESSION}" 2>/dev/null; then
  echo "suite tmux session already exists: ${SUITE_SESSION}" >&2
  exit 2
fi

if [[ -z "${SUITE_ROOT:-}" ]]; then
  SUITE_ROOT="${OUTPUT_ROOT}/${SUITE_NAME}_${SPLIT}_suite_$(date +%Y%m%d_%H%M%S)"
fi
SUITE_LOG="${SUITE_LOG:-${SUITE_ROOT}.log}"
LATEST_PATH_FILE="${LATEST_PATH_FILE:-${OUTPUT_ROOT}/latest_far_cloud_suite_path.txt}"

mkdir -p "${OUTPUT_ROOT}"
printf '%s\n' "${SUITE_ROOT}" > "${LATEST_PATH_FILE}"

# tmux servers do not reliably inherit arbitrary API-key variables from a later
# client shell. Set only the required redacted-at-output key in tmux's private
# environment instead of embedding it in the visible command string.
tmux start-server
cleanup_tmux_key() {
  tmux set-environment -gu "${REQUIRED_ENV}" 2>/dev/null || true
}
trap cleanup_tmux_key EXIT
tmux set-environment -g "${REQUIRED_ENV}" "${!REQUIRED_ENV}"

echo "starting cloud suite in tmux session: ${SUITE_SESSION}"
echo "suite root: ${SUITE_ROOT}"
echo "suite log: ${SUITE_LOG}"
echo "config: ${CONFIG}"
echo "required env: ${REQUIRED_ENV} (value redacted)"

PREFLIGHT_CMD="bash scripts/check_cloud_run_readiness.sh --config ${CONFIG} --output-root ${OUTPUT_ROOT} --require-keys"
if [[ "${ALLOW_DIRTY}" == "1" ]]; then
  PREFLIGHT_CMD="${PREFLIGHT_CMD} --allow-dirty"
fi

tmux new-session -d -s "${SUITE_SESSION}" \
  "bash -lc 'source ~/miniconda3/etc/profile.d/conda.sh; conda activate train; cd ${FAR_ROOT}; source scripts/windows_gpu_env.sh; echo FAR_CLOUD_SUITE_START \$(date -Is) output=${SUITE_ROOT} config=${CONFIG}; ${PREFLIGHT_CMD}; falsirag-suite --config ${CONFIG} --data-dir ${DATA_DIR} --output-dir ${SUITE_ROOT} --split ${SPLIT}' >> '${SUITE_LOG}' 2>&1"

# The new session has already inherited the key. Remove the global tmux copy so
# unrelated future sessions do not inherit the credential.
cleanup_tmux_key
trap - EXIT

tmux list-sessions
echo "latest cloud path file: ${LATEST_PATH_FILE}"
