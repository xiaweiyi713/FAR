#!/usr/bin/env bash
# Read-only remote P6 machine-prelabel status.

set -euo pipefail
remote="${1:-${FAR_WINDOWS_REMOTE:-windows-gpu}}"
packet="${FAR_P6_PACKET_DIR:-/mnt/d/FAR-outputs/type_mappability_v1}"
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- "${packet}" <<'REMOTE'
set -u
packet="$1"
echo "time=$(date -Is)"
systemctl --user show far-p6-prelabels.service far-ollama-p6.service \
  -p ActiveState -p SubState -p MainPID -p Result -p NRestarts --no-pager 2>/dev/null || true
checkpoint="${packet}/machine_prelabel_checkpoint.jsonl"
if [[ -s "${checkpoint}" ]]; then
  printf 'checkpoint='; wc -l < "${checkpoint}"
  tail -n1 "${checkpoint}" | python3 -c 'import json,sys; print("last="+str(json.load(sys.stdin).get("sample_id")))'
else
  echo "checkpoint=0"
fi
ls -l "${packet}/completed/machine_prelabels.jsonl" \
  "${packet}/completed/machine_identity.json" \
  "${packet}/completed/machine_install.json" 2>/dev/null || true
/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used,utilization.gpu,temperature.gpu,pstate \
  --format=csv,noheader,nounits 2>/dev/null || true
tail -n30 /mnt/d/FAR-outputs/type_mappability_v1.log 2>/dev/null || true
grep -Ein 'traceback|exception|out of memory|cuda error|ValueError|HTTP[^0-9]*500|status[^0-9]*500' \
  /mnt/d/FAR-outputs/type_mappability_v1.log 2>/dev/null | tail -n20 || true
REMOTE
