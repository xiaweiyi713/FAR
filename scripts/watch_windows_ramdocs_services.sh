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
marker="/mnt/d/FAR-runtime/ramdocs_dev_v1.keep-running"
waiting_marker="/mnt/d/FAR-runtime/ramdocs_dev_v1.waiting-for-gpu"
manifest="/mnt/d/FAR-outputs/ramdocs_dev_v1/suite_manifest.json"
watchdog_log="/mnt/d/FAR-outputs/ramdocs_dev_v1.watchdog.log"
nvidia_smi="/usr/lib/wsl/lib/nvidia-smi"
ollama_unit="far-ollama-2plus4.service"
suite_unit="far-ramdocs-phase-a.service"

user_systemctl() {
  runuser -u "${training_user}" -- env \
    XDG_RUNTIME_DIR="${runtime_dir}" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=${runtime_dir}/bus" \
    systemctl --user "$@"
}

if [[ -f "${manifest}" ]]; then
  rm -f "${marker}" "${waiting_marker}"
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
