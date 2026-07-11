#!/usr/bin/env bash
# Guarded stopper for remote P5 services. Default is dry-run.

set -euo pipefail

execute=0
stop_ollama=0
remote="${FAR_WINDOWS_REMOTE:-windows-gpu}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) execute=1 ;;
    --stop-ollama) stop_ollama=1 ;;
    --dry-run) execute=0 ;;
    -h|--help)
      echo "usage: scripts/stop_windows_p5_ablations.sh [--execute] [--stop-ollama] [remote]"
      exit 0
      ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) remote="$1" ;;
  esac
  shift
done

echo "remote=${remote} mode=$([[ ${execute} == 1 ]] && echo execute || echo dry-run) stop_ollama=${stop_ollama}"
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user show far-p5-ablations.service far-ollama-p5.service -p ActiveState -p SubState -p MainPID -p Result --no-pager" || true
echo "planned: systemctl --user stop far-p5-ablations.service"
if [[ "${stop_ollama}" == "1" ]]; then
  echo "planned: systemctl --user stop far-ollama-p5.service"
fi
if [[ "${execute}" != "1" ]]; then
  echo "dry-run complete; no service stopped"
  exit 0
fi
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user stop far-p5-ablations.service"
if [[ "${stop_ollama}" == "1" ]]; then
  ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
    "systemctl --user stop far-ollama-p5.service"
fi
echo "selected P5 services stopped; checkpoints were not deleted"
