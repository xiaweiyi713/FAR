#!/usr/bin/env bash
# Guarded P14 pause. Default is read-only; execute preserves the v2 checkpoint.

set -euo pipefail
execute=0
remote="${FAR_WINDOWS_REMOTE:-windows-gpu}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) execute=1 ;;
    --dry-run) execute=0 ;;
    -h|--help)
      echo "usage: scripts/pause_windows_selective_acceptance.sh [--execute] [remote]"
      exit 0
      ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) remote="$1" ;;
  esac
  shift
done
if [[ "${execute}" == "1" && "${FAR_P14_PAUSE_ALLOWED:-0}" != "1" ]]; then
  echo "refusing P14 pause; set FAR_P14_PAUSE_ALLOWED=1 with --execute" >&2
  exit 3
fi

output_root="/mnt/d/FAR-outputs/selective_acceptance_v2"
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- \
  "${execute}" "${output_root}" <<'REMOTE'
set -euo pipefail
execute="$1"; output_root="$2"
show_state() {
  systemctl --user show far-selective-acceptance.service \
    far-ollama-selective-acceptance.service \
    -p Id -p ActiveState -p SubState -p MainPID -p NRestarts -p Result --no-pager
  checkpoint="${output_root}/runs/far/checkpoint.jsonl"
  printf 'checkpoint_rows='; [[ -f "${checkpoint}" ]] && wc -l <"${checkpoint}" || echo 0
}
show_state
if [[ "${execute}" != "1" ]]; then
  echo "dry-run complete; no service was stopped"
  exit 0
fi

systemctl --user stop --no-block far-selective-acceptance.service
deadline=$((SECONDS + 45))
while (( SECONDS < deadline )); do
  state="$(systemctl --user is-active far-selective-acceptance.service 2>/dev/null || true)"
  [[ "${state}" != "active" && "${state}" != "activating" && "${state}" != "deactivating" ]] \
    && break
  sleep 1
done
systemctl --user stop --no-block far-ollama-selective-acceptance.service
deadline=$((SECONDS + 30))
while (( SECONDS < deadline )); do
  state="$(systemctl --user is-active far-ollama-selective-acceptance.service 2>/dev/null || true)"
  [[ "${state}" != "active" && "${state}" != "activating" && "${state}" != "deactivating" ]] \
    && break
  sleep 1
done

for unit in far-selective-acceptance.service far-ollama-selective-acceptance.service; do
  state="$(systemctl --user is-active "${unit}" 2>/dev/null || true)"
  if [[ "${state}" == "active" || "${state}" == "activating" || "${state}" == "deactivating" ]]; then
    echo "P14 pause timed out while ${unit} remained ${state}" >&2
    exit 1
  fi
done
systemctl --user reset-failed far-selective-acceptance.service \
  far-ollama-selective-acceptance.service 2>/dev/null || true
show_state
printf 'gpu='; /usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used,utilization.gpu \
  --format=csv,noheader,nounits 2>/dev/null || true
echo "P14 paused; checkpoint retained"
REMOTE
