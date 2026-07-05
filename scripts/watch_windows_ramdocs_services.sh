#!/usr/bin/env bash
# Windows-owned watchdog for the formal RAMDocs dev run.
# Run as WSL root from the Windows keepalive task.

set -u

if (( EUID != 0 )); then
  echo "watch_windows_ramdocs_services.sh must run as WSL root" >&2
  exit 2
fi

training_user="wenyao"
runtime_dir="/run/user/1001"
nvidia_smi="/usr/lib/wsl/lib/nvidia-smi"
ollama_unit="far-ollama-2plus4.service"

if [[ -f /mnt/d/FAR-runtime/ramdocs_dev_v2.keep-running ]]; then
  manifest_profile="round2"
  marker="/mnt/d/FAR-runtime/ramdocs_dev_v2.keep-running"
  waiting_marker="/mnt/d/FAR-runtime/ramdocs_dev_v2.waiting-for-gpu"
  manifest="/mnt/d/FAR-outputs/ramdocs_dev_v2/runs/far/run_manifest.json"
  watchdog_log="/mnt/d/FAR-outputs/ramdocs_dev_v2.watchdog.log"
  suite_unit="far-ramdocs-round2.service"
else
  manifest_profile="round1"
  marker="/mnt/d/FAR-runtime/ramdocs_dev_v1.keep-running"
  waiting_marker="/mnt/d/FAR-runtime/ramdocs_dev_v1.waiting-for-gpu"
  manifest="/mnt/d/FAR-outputs/ramdocs_dev_v1/suite_manifest.json"
  watchdog_log="/mnt/d/FAR-outputs/ramdocs_dev_v1.watchdog.log"
  suite_unit="far-ramdocs-phase-a.service"
fi

user_systemctl() {
  runuser -u "${training_user}" -- env \
    XDG_RUNTIME_DIR="${runtime_dir}" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=${runtime_dir}/bus" \
    systemctl --user "$@"
}

manifest_is_complete() {
  [[ -f "${manifest}" ]] || return 1
  if [[ "${manifest_profile}" == "round1" ]]; then
    return 0
  fi
  command -v python3 >/dev/null 2>&1 || return 1
  python3 - "${manifest}" <<'PY'
import json
import sys
from pathlib import Path

try:
    value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)

complete = all(
    (
        value.get("status") == "complete",
        value.get("partial") is False,
        value.get("split") == "dev",
        value.get("expected") == 350,
        value.get("completed") == 350,
        value.get("gold_loaded_by_runner") is False,
    )
)
raise SystemExit(0 if complete else 1)
PY
}

if manifest_is_complete; then
  rm -f "${marker}" "${waiting_marker}"
  user_systemctl disable --now "${suite_unit}" "${ollama_unit}" >/dev/null 2>&1 || true
  exit 0
fi
[[ -f "${marker}" ]] || exit 0

ollama_active="$(user_systemctl is-active "${ollama_unit}" 2>/dev/null || true)"
suite_active="$(user_systemctl is-active "${suite_unit}" 2>/dev/null || true)"
if [[ "${ollama_active}" == "active" && "${suite_active}" == "active" ]]; then
  rm -f "${waiting_marker}"
  exit 0
fi

# If FAR's Ollama is already active, its GPU allocation is expected and the
# suite may start. Otherwise, avoid claiming a GPU that another task is using.
if [[ "${ollama_active}" != "active" ]]; then
  memory_used="99999"
  utilization="100"
  if [[ -x "${nvidia_smi}" ]]; then
    IFS=, read -r memory_used utilization < <(
      "${nvidia_smi}" \
        --query-gpu=memory.used,utilization.gpu \
        --format=csv,noheader,nounits 2>/dev/null | head -n 1
    )
    memory_used="${memory_used//[[:space:]]/}"
    utilization="${utilization//[[:space:]]/}"
  fi
  if ! [[ "${memory_used}" =~ ^[0-9]+$ && "${utilization}" =~ ^[0-9]+$ ]] \
    || (( memory_used > 1500 || utilization > 20 )); then
    if [[ ! -f "${waiting_marker}" ]]; then
      printf '%s waiting_for_gpu memory_used_mib=%s utilization_pct=%s\n' \
        "$(date --iso-8601=seconds)" "${memory_used}" "${utilization}" \
        >> "${watchdog_log}"
      touch "${waiting_marker}"
    fi
    exit 0
  fi
fi

rm -f "${waiting_marker}"
user_systemctl enable --now "${ollama_unit}" "${suite_unit}" >/dev/null 2>&1 || true
