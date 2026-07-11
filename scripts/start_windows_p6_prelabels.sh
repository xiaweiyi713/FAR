#!/usr/bin/env bash
# Guarded remote starter for P6 machine prelabels. Default is dry-run.

set -euo pipefail
execute=0; remote="${FAR_WINDOWS_REMOTE:-windows-gpu}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) execute=1 ;;
    --dry-run) execute=0 ;;
    -h|--help) echo "usage: scripts/start_windows_p6_prelabels.sh [--execute] [remote]"; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) remote="$1" ;;
  esac
  shift
done
if [[ "${execute}" == "1" && "${FAR_P6_PRELABEL_ALLOWED:-0}" != "1" ]]; then
  echo "refusing P6 model start; set FAR_P6_PRELABEL_ALLOWED=1 with --execute" >&2
  exit 3
fi
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${script_dir}/preflight_windows_p6_prelabels.sh" "${remote}"
echo "planned: start far-ollama-p6, verify digest, start far-p6-prelabels"
if [[ "${execute}" != "1" ]]; then
  echo "dry-run complete; no service started"
  exit 0
fi
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user start far-ollama-p6.service"
if ! FAR_P6_REQUIRE_OLLAMA=1 \
  "${script_dir}/preflight_windows_p6_prelabels.sh" "${remote}"; then
  ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
    "systemctl --user stop far-ollama-p6.service" || true
  echo "runtime preflight failed; P6 Ollama was stopped" >&2
  exit 1
fi
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user start far-p6-prelabels.service"
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user show far-p6-prelabels.service far-ollama-p6.service -p ActiveState -p SubState -p MainPID -p Result --no-pager"
