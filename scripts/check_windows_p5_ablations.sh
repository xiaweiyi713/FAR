#!/usr/bin/env bash
# Read-only status for the remote registered P5 run.

set -euo pipefail
remote="${1:-${FAR_WINDOWS_REMOTE:-windows-gpu}}"
output_dir="${FAR_P5_OUTPUT_DIR:-/mnt/d/FAR-outputs/p5_ramdocs_v1}"

ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- "${output_dir}" <<'REMOTE'
set -u
output_dir="$1"
echo "time=$(date -Is)"
systemctl --user show far-p5-ablations.service far-ollama-p5.service \
  -p ActiveState -p SubState -p MainPID -p Result -p NRestarts --no-pager 2>/dev/null || true
for method in far far_minus_typed_revision_aggressive far_flat_claims; do
  checkpoint="${output_dir}/runs/${method}/checkpoint.jsonl"
  manifest="${output_dir}/runs/${method}/run_manifest.json"
  if [[ -f "${checkpoint}" ]]; then
    printf '%s checkpoint=' "${method}"; wc -l < "${checkpoint}"
    tail -n1 "${checkpoint}" | python3 -c 'import json,sys; r=json.load(sys.stdin); print("last="+str(r.get("sample_id")))'
  else
    echo "${method} checkpoint=0"
  fi
  if [[ -f "${manifest}" ]]; then
    python3 - "${manifest}" <<'PY'
import json
import sys

m = json.load(open(sys.argv[1], encoding="utf-8"))
print({key: m.get(key) for key in ("method", "status", "completed", "expected", "errors")})
PY
  fi
done
/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used,utilization.gpu,temperature.gpu,pstate \
  --format=csv,noheader,nounits 2>/dev/null || true
echo "log_tail:"
tail -n30 /mnt/d/FAR-outputs/p5_ramdocs_v1.log 2>/dev/null || true
echo "errors:"
grep -Ein 'traceback|exception|out of memory|cuda error|run failed|ValueError|HTTP[^0-9]*500|status[^0-9]*500' \
  /mnt/d/FAR-outputs/p5_ramdocs_v1.log 2>/dev/null | tail -n20 || true
REMOTE
