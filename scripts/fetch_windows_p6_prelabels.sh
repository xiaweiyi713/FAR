#!/usr/bin/env bash
# Fetch remote P6 prelabels and install them locally with full raw provenance.

set -euo pipefail
execute=0; remote="${FAR_WINDOWS_REMOTE:-windows-gpu}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) execute=1 ;;
    --dry-run) execute=0 ;;
    -h|--help) echo "usage: scripts/fetch_windows_p6_prelabels.sh [--execute] [remote]"; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) remote="$1" ;;
  esac
  shift
done
if [[ "${execute}" == "1" && "${FAR_P6_FETCH_ALLOWED:-0}" != "1" ]]; then
  echo "refusing P6 artifact install; set FAR_P6_FETCH_ALLOWED=1 with --execute" >&2
  exit 3
fi
remote_packet="${FAR_P6_PACKET_DIR:-/mnt/d/FAR-outputs/type_mappability_v1}"
local_copy="${FAR_P6_LOCAL_COPY:-outputs/type_mappability_v1_remote}"
target_packet="${FAR_P6_TARGET_PACKET:-diagnostics/type_mappability_v1}"
echo "planned: verify ${remote}:${remote_packet}, copy to ${local_copy}, install into ${target_packet}"
if [[ "${execute}" != "1" ]]; then
  echo "dry-run complete; no artifact copied or installed"
  exit 0
fi
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- "${remote_packet}" <<'REMOTE'
set -euo pipefail
packet="$1"
for file in machine_prelabels.jsonl machine_identity.json machine_install.json; do
  [[ -f "${packet}/completed/${file}" ]] || { echo "missing completed/${file}" >&2; exit 1; }
done
[[ -f "${packet}/machine_prelabel_attempt_log.jsonl" ]] || {
  echo "missing machine_prelabel_attempt_log.jsonl" >&2
  exit 1
}
python3 - \
  "${packet}/completed/machine_install.json" \
  "${packet}/machine_prelabel_attempt_log.jsonl" <<'PY'
import hashlib
import json
import sys

m=json.load(open(sys.argv[1], encoding="utf-8"))
if m.get("schema_version") != "far-type-mappability-machine-prelabel-v1" or m.get("samples") != 217:
    raise SystemExit("remote P6 machine manifest is incomplete")
observed = hashlib.sha256(open(sys.argv[2], "rb").read()).hexdigest()
attempts = sum(1 for line in open(sys.argv[2], encoding="utf-8") if line.strip())
if m.get("attempt_log_sha256") != observed or m.get("attempts") != attempts:
    raise SystemExit("remote P6 attempt log differs from its manifest")
PY
REMOTE
mkdir -p "${local_copy}"
rsync -a --delete "${remote}:${remote_packet}/" "${local_copy}/"
uv run falsirag diag type-mappability install-machine \
  --packet-dir "${target_packet}" \
  --input "${local_copy}/completed/machine_prelabels.jsonl" \
  --identity "${local_copy}/completed/machine_identity.json"
uv run falsirag diag type-mappability status --packet-dir "${target_packet}"
echo "P6 machine prelabels installed locally with raw response provenance; no local model call"
