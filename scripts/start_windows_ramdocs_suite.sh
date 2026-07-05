#!/usr/bin/env bash
# Start or resume the D:-backed RAMDocs Phase A suite on the Windows/WSL GPU host.
#
# Intended to be run on `windows-gpu` inside WSL. The RAMDocs runner is
# checkpointed, so reusing the same output directory resumes incomplete methods
# and skips completed samples. This script deliberately sources
# scripts/windows_gpu_env.sh for the parent shell. The long-lived Ollama and
# suite processes run as systemd user services, because WSL can interrupt tmux
# pane scopes after the final SSH session disconnects even when the tmux server
# itself is persistent.

set -euo pipefail

FAR_ROOT="/mnt/d/FAR-workspace/FAR-2plus4"
OLLAMA_UNIT="${OLLAMA_UNIT:-far-ollama-2plus4.service}"
SUITE_UNIT="${SUITE_UNIT:-far-ramdocs-phase-a.service}"
OUTPUT_ROOT="/mnt/d/FAR-outputs"
OUTPUT_DIR="${OUTPUT_ROOT}/ramdocs_dev_v1"
SUITE_LOG="${OUTPUT_DIR}.log"
RUN_MARKER="/mnt/d/FAR-runtime/ramdocs_dev_v1.keep-running"
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
mkdir -p "${OUTPUT_ROOT}" "$(dirname "${SUITE_LOG}")"

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
for unit in "${OLLAMA_UNIT}" "${SUITE_UNIT}"; do
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
  cp scripts/systemd/far-ramdocs-phase-a.service ~/.config/systemd/user/
  systemctl --user daemon-reload
Then rerun this launcher.
EOF
  exit 2
fi

if [[ ! -f "${OUTPUT_DIR}/suite_manifest.json" ]]; then
  mkdir -p "$(dirname "${RUN_MARKER}")"
  touch "${RUN_MARKER}"
fi

systemctl --user enable --now "${OLLAMA_UNIT}"
until curl -fsS --max-time "${API_TIMEOUT_SECONDS}" "http://${OLLAMA_HOST}/api/tags" >/dev/null; do
  sleep "${POLL_SECONDS}"
done

echo "starting/resuming RAMDocs suite as systemd user service: ${SUITE_UNIT}"
echo "output dir: ${OUTPUT_DIR}"
echo "suite log: ${SUITE_LOG}"
echo "commit: $(git rev-parse HEAD)"
systemctl --user enable --now "${SUITE_UNIT}"
systemctl --user --no-pager --full status "${OLLAMA_UNIT}" "${SUITE_UNIT}" || true
