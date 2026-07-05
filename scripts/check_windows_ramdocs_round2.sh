#!/usr/bin/env bash
# Read-only status check for the D:-backed RAMDocs Round 2 FAR-only run.
#
# Intended to be run on windows-gpu inside WSL. It does not start, stop, or
# modify services. Use it to distinguish a genuinely stalled run from a slow
# in-flight Ollama generation that has not yet appended the next checkpoint row.

set -u

OUTPUT_DIR="${OUTPUT_DIR:-/mnt/d/FAR-outputs/ramdocs_dev_v2}"
RUN_DIR="${RUN_DIR:-${OUTPUT_DIR}/runs/far}"
CHECKPOINT="${CHECKPOINT:-${RUN_DIR}/checkpoint.jsonl}"
ROUND2_UNIT="${ROUND2_UNIT:-far-ramdocs-round2.service}"
OLLAMA_UNIT="${OLLAMA_UNIT:-far-ollama-2plus4.service}"
OLLAMA_LOG="${OLLAMA_LOG:-/mnt/d/FAR-outputs/far-ollama-2plus4.log}"
RUN_LOG="${RUN_LOG:-${OUTPUT_DIR}.log}"
NVIDIA_SMI="${NVIDIA_SMI:-/usr/lib/wsl/lib/nvidia-smi}"

echo "time=$(date -Is)"
echo "services:"
systemctl --user is-active "${ROUND2_UNIT}" "${OLLAMA_UNIT}" 2>/dev/null || true
systemctl --user show "${ROUND2_UNIT}" "${OLLAMA_UNIT}" \
  -p ActiveState -p SubState -p MainPID -p Result -p NRestarts --no-pager 2>/dev/null || true

echo "markers:"
ls -l /mnt/d/FAR-runtime/ramdocs_dev_v2.keep-running \
  /mnt/d/FAR-runtime/ramdocs_dev_v2.waiting-for-gpu 2>/dev/null || true

echo "checkpoint:"
if [[ -f "${CHECKPOINT}" ]]; then
  wc -l "${CHECKPOINT}"
  stat -c "%s %y" "${CHECKPOINT}"
  tail -n 1 "${CHECKPOINT}" | python3 -c '
import json
import sys

row = json.loads(sys.stdin.read())
meta = row.get("metadata") or {}
consolidation = meta.get("final_answer_consolidation") or {}
print({
    "sample_id": row.get("sample_id"),
    "method": row.get("method"),
    "final_answer_consolidation_applied": bool(consolidation.get("applied")),
})
'
else
  echo "missing ${CHECKPOINT}"
fi
ls -l "${RUN_DIR}/run_manifest.json" "${RUN_DIR}/predictions.jsonl" 2>/dev/null || true

echo "gpu:"
if [[ -x "${NVIDIA_SMI}" ]]; then
  "${NVIDIA_SMI}" --query-gpu=memory.used,utilization.gpu,temperature.gpu,pstate \
    --format=csv,noheader,nounits 2>/dev/null || true
else
  echo "nvidia-smi not found at ${NVIDIA_SMI}"
fi

echo "processes:"
ps -eo pid,ppid,stat,pcpu,pmem,etime,cmd |
  grep -E "experiments.run_ramdocs|FAR-runtime/ollama|ollama serve|llama-server" |
  grep -v grep || true

echo "ollama_decode_tail:"
if [[ -f "${OLLAMA_LOG}" ]]; then
  grep -E "task [0-9]+|n_decoded|slot print_timing|error|panic|CUDA|out of memory" \
    "${OLLAMA_LOG}" | tail -n 20 || true
else
  echo "missing ${OLLAMA_LOG}"
fi

echo "run_errors:"
if [[ -f "${RUN_LOG}" ]]; then
  grep -Ein "traceback|exception|out of memory|cuda error|run failed|ValueError|500" \
    "${RUN_LOG}" | tail -n 20 || true
else
  echo "missing ${RUN_LOG}"
fi
