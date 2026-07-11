#!/usr/bin/env bash
# Verify remote completion and copy P5 artifacts locally without model calls.

set -euo pipefail

execute=0
remote="${FAR_WINDOWS_REMOTE:-windows-gpu}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) execute=1 ;;
    --dry-run) execute=0 ;;
    -h|--help)
      echo "usage: scripts/fetch_windows_p5_ablations.sh [--execute] [remote]"
      exit 0
      ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) remote="$1" ;;
  esac
  shift
done
if [[ "${execute}" == "1" && "${FAR_P5_FETCH_ALLOWED:-0}" != "1" ]]; then
  echo "refusing artifact copy; set FAR_P5_FETCH_ALLOWED=1 with --execute" >&2
  exit 3
fi

remote_output="${FAR_P5_OUTPUT_DIR:-/mnt/d/FAR-outputs/p5_ramdocs_v1}"
local_output="${FAR_P5_LOCAL_OUTPUT_DIR:-outputs/p5_ramdocs_v1}"
echo "planned: rsync ${remote}:${remote_output}/ -> ${local_output}/"
if [[ "${execute}" != "1" ]]; then
  echo "dry-run complete; no artifact copied"
  exit 0
fi

ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- "${remote_output}" <<'REMOTE'
set -euo pipefail
output="$1"
for method in far far_minus_typed_revision_aggressive far_flat_claims; do
  python3 - "${output}/runs/${method}/run_manifest.json" <<'PY'
import json
import sys

m = json.load(open(sys.argv[1], encoding="utf-8"))
complete = (
    m.get("status") == "complete"
    and m.get("completed") == 350
    and m.get("expected") == 350
    and m.get("errors") == 0
)
if not complete:
    raise SystemExit(f"incomplete P5 manifest: {sys.argv[1]}")
PY
done
REMOTE
mkdir -p "${local_output}"
rsync -a --delete "${remote}:${remote_output}/" "${local_output}/"
uv run falsirag diag p5-ablations verify \
  --output-dir "${local_output}" \
  --report-json "${local_output}/p5_ramdocs_ablations.json" \
  --report-markdown "${local_output}/p5_ramdocs_ablations.md"
echo "P5 artifacts copied and independently verified without local model calls"
