#!/usr/bin/env bash
# Fetch complete remote P6-M jurors, then analyze and verify locally without model calls.

set -euo pipefail

execute=0
remote="${FAR_WINDOWS_REMOTE:-windows-gpu}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) execute=1 ;;
    --dry-run) execute=0 ;;
    -h|--help) echo "usage: scripts/fetch_windows_p6m.sh [--execute] [remote]"; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) remote="$1" ;;
  esac
  shift
done
if [[ "${execute}" == "1" && "${FAR_P6M_FETCH_ALLOWED:-0}" != "1" ]]; then
  echo "refusing P6-M fetch; set FAR_P6M_FETCH_ALLOWED=1 with --execute" >&2
  exit 3
fi

remote_root="${FAR_P6M_OUTPUT_ROOT:-/mnt/d/FAR-outputs/p6m}"
local_root="${FAR_P6M_LOCAL_ROOT:-outputs/p6m_remote}"
packet_dir="${FAR_P6M_LOCAL_PACKET:-diagnostics/type_mappability_v1}"
report_dir="${FAR_P6M_REPORT_DIR:-reports/type_mappability_machine}"
echo "planned: fetch ${remote}:${remote_root}/J1..J3, analyze into ${report_dir}, verify"
if [[ "${execute}" != "1" ]]; then
  echo "dry-run complete; no remote artifacts copied"
  exit 0
fi

ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- "${remote_root}" <<'REMOTE'
set -euo pipefail
root="$1"
for juror in J1 J2 J3; do
  manifest="${root}/${juror}/juror_manifest.json"
  [[ -f "${manifest}" ]] || { echo "missing ${manifest}" >&2; exit 1; }
  python3 -c '
import json, sys
m=json.load(open(sys.argv[1], encoding="utf-8"))
if (
    m.get("schema_version") != "far-p6m-juror-manifest-v1"
    or m.get("complete") is not True
    or m.get("expected_samples") != 217
    or m.get("rows") != 434
    or m.get("human_annotator") is not False
    or m.get("publication_gold") is not False
):
    raise SystemExit(f"incomplete or mislabeled P6-M juror: {sys.argv[1]}")
' "${manifest}"
done
REMOTE

mkdir -p "${local_root}"
for juror in J1 J2 J3; do
  rsync -a --delete "${remote}:${remote_root}/${juror}/" "${local_root}/${juror}/"
done
uv run --locked falsirag diag type-mappability-machine analyze \
  --packet-dir "${packet_dir}" \
  --juror-dir "${local_root}/J1" \
  --juror-dir "${local_root}/J2" \
  --juror-dir "${local_root}/J3" \
  --output-dir "${report_dir}"
uv run --locked falsirag diag type-mappability-machine verify \
  --packet-dir "${packet_dir}" \
  --juror-dir "${local_root}/J1" \
  --juror-dir "${local_root}/J2" \
  --juror-dir "${local_root}/J3" \
  --report-dir "${report_dir}"
