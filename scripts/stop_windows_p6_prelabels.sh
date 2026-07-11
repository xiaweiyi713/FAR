#!/usr/bin/env bash
# Guarded stopper for remote P6 services. Default is dry-run.

set -euo pipefail
execute=0; stop_ollama=0; remote="${FAR_WINDOWS_REMOTE:-windows-gpu}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) execute=1 ;;
    --stop-ollama) stop_ollama=1 ;;
    --dry-run) execute=0 ;;
    -h|--help) echo "usage: scripts/stop_windows_p6_prelabels.sh [--execute] [--stop-ollama] [remote]"; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) remote="$1" ;;
  esac
  shift
done
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user show far-p6-prelabels.service far-ollama-p6.service -p ActiveState -p SubState -p MainPID -p Result --no-pager" || true
echo "planned: stop far-p6-prelabels.service"
[[ "${stop_ollama}" == "1" ]] && echo "planned: stop far-ollama-p6.service"
if [[ "${execute}" != "1" ]]; then
  echo "dry-run complete; no service stopped"
  exit 0
fi
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user stop far-p6-prelabels.service"
if [[ "${stop_ollama}" == "1" ]]; then
  ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
    "systemctl --user stop far-ollama-p6.service"
fi
echo "selected P6 services stopped; checkpoints were not deleted"
