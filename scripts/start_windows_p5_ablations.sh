#!/usr/bin/env bash
# Guarded remote P5 starter. Default is read-only dry-run.

set -euo pipefail

execute=0
remote="${FAR_WINDOWS_REMOTE:-windows-gpu}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) execute=1 ;;
    --dry-run) execute=0 ;;
    -h|--help)
      echo "usage: scripts/start_windows_p5_ablations.sh [--execute] [remote]"
      exit 0
      ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) remote="$1" ;;
  esac
  shift
done
if [[ "${execute}" == "1" && "${FAR_P5_TRAINING_ALLOWED:-0}" != "1" ]]; then
  echo "refusing P5 start; set FAR_P5_TRAINING_ALLOWED=1 with --execute" >&2
  exit 3
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "== offline P5 preflight =="
"${script_dir}/preflight_windows_p5_ablations.sh" "${remote}"
cat <<'EOF'
planned remote actions:
  systemctl --user start far-ollama-p5.service
  exact digest/runtime preflight
  systemctl --user start far-p5-ablations.service
EOF
if [[ "${execute}" != "1" ]]; then
  echo "dry-run complete; no service started"
  exit 0
fi

ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user start far-ollama-p5.service"
if ! ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' <<'REMOTE'
set -euo pipefail
deadline=$((SECONDS + 180))
stable=0
while (( SECONDS < deadline )); do
  if curl -fsS --max-time 5 http://127.0.0.1:11434/api/tags >/dev/null; then
    stable=$((stable + 1))
    (( stable >= 3 )) && exit 0
  else
    stable=0
  fi
  sleep 2
done
echo "P5 Ollama API did not become stable within 180 seconds" >&2
exit 1
REMOTE
then
  ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
    "systemctl --user stop far-ollama-p5.service" || true
  exit 1
fi
if ! FAR_P5_REQUIRE_OLLAMA=1 \
  "${script_dir}/preflight_windows_p5_ablations.sh" "${remote}"; then
  ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
    "systemctl --user stop far-ollama-p5.service" || true
  echo "runtime preflight failed; the P5 Ollama service was stopped" >&2
  exit 1
fi
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user start far-p5-ablations.service"
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user show far-p5-ablations.service far-ollama-p5.service -p ActiveState -p SubState -p MainPID -p Result --no-pager"
echo "P5 started; monitor with scripts/check_windows_p5_ablations.sh"
