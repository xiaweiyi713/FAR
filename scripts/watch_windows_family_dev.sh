#!/usr/bin/env bash
# Read-only monitor for the WS2 family-dev run on the Windows GPU WSL host.
#
# This script prints service health, checkpoint integrity, manifest locations,
# recent logs, and GPU status.  It intentionally does not start/stop units,
# write markers, inspect held-out/test inputs, or finalize results.

set -euo pipefail

remote="${1:-${FAR_WINDOWS_REMOTE:-windows-gpu}}"
output_dir="${FAR_FAMILY_DEV_OUTPUT_DIR:-/mnt/d/FAR-outputs/family_dev_v1}"
input_dir="${FAR_FAMILY_DEV_INPUT_DIR:-/mnt/d/FAR-outputs/family_dev_input_v1}"

ssh "${remote}" 'bash -s' -- "${output_dir}" "${input_dir}" <<'REMOTE'
set -u

output_dir="$1"
input_dir="$2"
nvidia_smi="/usr/lib/wsl/lib/nvidia-smi"

echo "== FAR WS2 family-dev read-only monitor =="
date -Is
echo "output_dir=${output_dir}"
echo "input_dir=${input_dir}"

echo
echo "== systemd user services =="
for unit in \
  far-family-dev-mistral-resume.service \
  far-family-dev@mistral.service \
  far-family-dev@google.service \
  far-family-dev@meta.service \
  far-family-dev.service \
  far-ollama-family-dev.service \
  far-boundary.service \
  far-ollama-boundary.service; do
  printf "%s: " "${unit}"
  systemctl --user is-active "${unit}" 2>/dev/null || true
done

echo
echo "== active service health =="
for unit in \
  far-family-dev@mistral.service \
  far-family-dev@google.service \
  far-family-dev@meta.service \
  far-ollama-family-dev.service; do
  if [[ "$(systemctl --user is-active "${unit}" 2>/dev/null || true)" == "active" ]]; then
    systemctl --user show "${unit}" \
      -p Id -p ActiveState -p SubState -p MainPID -p NRestarts -p Result \
      --no-pager 2>/dev/null || true
  fi
done

echo
echo "== input view =="
if [[ -f "${input_dir}/manifest.json" ]]; then
  echo "${input_dir}/manifest.json"
  sed -n '1,80p' "${input_dir}/manifest.json"
else
  echo "missing ${input_dir}/manifest.json"
fi
if [[ -f "${input_dir}/falsirag_bench.jsonl" ]]; then
  echo "${input_dir}/falsirag_bench.jsonl $(wc -l < "${input_dir}/falsirag_bench.jsonl")"
fi

echo
echo "== checkpoints and manifests =="
for family in mistral google meta; do
  for root in calibration runs; do
    for method in far minus_typed_conflict; do
      run_dir="${output_dir}/${root}/${family}/${method}"
      checkpoint="${run_dir}/checkpoint.jsonl"
      manifest="${run_dir}/run_manifest.json"
      if [[ -f "${checkpoint}" ]]; then
        echo "${checkpoint} $(wc -l < "${checkpoint}")"
      fi
      if [[ -f "${manifest}" ]]; then
        echo "${manifest}"
      fi
    done
  done
done
for family in mistral google meta; do
  candidate="${output_dir}/family_manifests/${family}.json"
  if [[ -f "${candidate}" ]]; then
    echo "${candidate}"
  fi
done
for candidate in "${output_dir}/manifest.json" "${output_dir}/result.json" "${output_dir}/family_dev_report.md" "${output_dir}/release_manifest.json"; do
  [[ -f "${candidate}" ]] && echo "${candidate}"
done

echo
echo "== checkpoint integrity =="
python3 - "${output_dir}" <<'PY' 2>/dev/null || true
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
for family in ("mistral", "google", "meta"):
    for phase, expected in (("calibration", 5), ("runs", 60)):
        for method in ("far", "minus_typed_conflict"):
            path = root / phase / family / method / "checkpoint.jsonl"
            if not path.is_file():
                continue
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
            ids = [str(row.get("sample_id", row.get("id", ""))) for row in rows]
            unique = len(set(ids))
            duplicates = len(ids) - unique
            print(
                f"{family}/{phase}/{method}: rows={len(rows)}/{expected} "
                f"unique={unique} duplicates={duplicates}"
            )
PY

echo
echo "== recent family-dev log =="
if [[ -f "${output_dir}.log" ]]; then
  tail -n 80 "${output_dir}.log"
else
  journalctl --user \
    -u far-family-dev-mistral-resume.service \
    -u 'far-family-dev@*.service' \
    -u far-family-dev.service \
    -n 80 --no-pager 2>/dev/null || true
fi

echo
echo "== active processes =="
ps -eo pid,etime,pcpu,pmem,cmd \
  | grep -E 'python -m far.experiments.family_dev|ollama serve|llama-server' \
  | grep -v grep || true

echo
echo "== GPU =="
if [[ -x "${nvidia_smi}" ]]; then
  "${nvidia_smi}" \
    --query-gpu=timestamp,name,utilization.gpu,memory.used,memory.total \
    --format=csv,noheader || true
else
  echo "missing ${nvidia_smi}"
fi
REMOTE
