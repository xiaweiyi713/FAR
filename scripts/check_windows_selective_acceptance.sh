#!/usr/bin/env bash
# Read-only progress/status snapshot for P14.

set -euo pipefail
remote="${1:-${FAR_WINDOWS_REMOTE:-windows-gpu}}"
output_root="${FAR_P14_OUTPUT_ROOT:-/mnt/d/FAR-outputs/selective_acceptance_v1}"
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- "${output_root}" <<'REMOTE'
set -euo pipefail
output_root="$1"
systemctl --user show far-selective-acceptance.service \
  far-ollama-selective-acceptance.service \
  -p Id -p ActiveState -p SubState -p MainPID -p NRestarts -p Result --no-pager
checkpoint="${output_root}/runs/far/checkpoint.jsonl"
predictions="${output_root}/runs/far/predictions.jsonl"
printf 'checkpoint_rows='; [[ -f "${checkpoint}" ]] && wc -l <"${checkpoint}" || echo 0
printf 'predictions_rows='; [[ -f "${predictions}" ]] && wc -l <"${predictions}" || echo 0
[[ -f "${output_root}/selective_acceptance.json" ]] \
  && python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("outcome="+str(r.get("registered_outcome")))' "${output_root}/selective_acceptance.json"
/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used,utilization.gpu \
  --format=csv,noheader,nounits 2>/dev/null || true
journalctl --user -u far-selective-acceptance.service -n 25 --no-pager
REMOTE
