#!/usr/bin/env bash
# Run one frozen P6-M juror on the authorized Windows/WSL host without downloading models.

set -euo pipefail

juror_id="${1:-}"
if [[ "${FAR_P6M_ALLOWED:-0}" != "1" ]]; then
  echo "refusing P6-M model execution; set FAR_P6M_ALLOWED=1" >&2
  exit 3
fi
case "${juror_id}" in
  J1) config_name="p6m_deepseek.yaml"; model="deepseek-chat" ;;
  J2) config_name="p6m_glm.yaml"; model="glm4:9b" ;;
  J3) config_name="p6m_llama.yaml"; model="llama3.1:8b" ;;
  *) echo "usage: FAR_P6M_ALLOWED=1 $0 J1|J2|J3" >&2; exit 2 ;;
esac

worktree="${FAR_P6M_WORKTREE:-/mnt/d/FAR-workspace/FAR-longterm}"
packet_dir="${FAR_P6M_PACKET_DIR:-/mnt/d/FAR-outputs/type_mappability_v1}"
output_root="${FAR_P6M_OUTPUT_ROOT:-/mnt/d/FAR-outputs/p6m}"
config="${worktree}/far/experiments/configs/${config_name}"
output_dir="${output_root}/${juror_id}"

[[ -d "${worktree}/.git" ]] || { echo "missing P6-M worktree" >&2; exit 1; }
[[ -f "${packet_dir}/packet_manifest.json" ]] || { echo "missing P6 packet" >&2; exit 1; }
[[ -f "${config}" ]] || { echo "missing P6-M config" >&2; exit 1; }
[[ -z "$(git -C "${worktree}" status --porcelain --untracked-files=all)" ]] || {
  echo "P6-M requires a clean remote worktree" >&2
  exit 1
}
if [[ "$(git -C "${worktree}" rev-parse HEAD)" != "$(git -C "${worktree}" rev-parse origin/main)" ]]; then
  echo "P6-M remote HEAD must equal origin/main" >&2
  exit 1
fi

source "${HOME}/miniconda3/etc/profile.d/conda.sh"
conda activate train
cd "${worktree}"
source scripts/windows_gpu_env.sh

if [[ "${juror_id}" == "J1" ]]; then
  [[ -n "${DEEPSEEK_API_KEY:-}" ]] || { echo "DEEPSEEK_API_KEY is not set" >&2; exit 1; }
else
  nvidia_smi="/usr/lib/wsl/lib/nvidia-smi"
  while true; do
    IFS=, read -r memory_used utilization < <(
      "${nvidia_smi}" --query-gpu=memory.used,utilization.gpu --format=csv,noheader,nounits |
        head -n1
    )
    memory_used="${memory_used//[[:space:]]/}"
    utilization="${utilization//[[:space:]]/}"
    if [[ "${memory_used}" =~ ^[0-9]+$ && "${utilization}" =~ ^[0-9]+$ ]] \
      && (( memory_used <= 1500 && utilization <= 20 )); then
      break
    fi
    printf '%s P6-M %s waiting_for_gpu memory_used_mib=%s utilization_pct=%s\n' \
      "$(date --iso-8601=seconds)" "${juror_id}" "${memory_used}" "${utilization}"
    sleep 60
  done
  tags="$(curl -fsS --max-time 5 http://127.0.0.1:11434/api/tags)" || {
    echo "Ollama is not available; start the existing remote service without pulling models" >&2
    exit 1
  }
  python3 -c '
import json, sys
model=sys.argv[1]
rows=json.load(sys.stdin).get("models", [])
matches=[row for row in rows if model in {row.get("name"), row.get("model")}]
if not matches or len(str(matches[0].get("digest", ""))) != 64:
    raise SystemExit(f"required preinstalled model is missing or unpinned: {model}")
' "${model}" <<<"${tags}"
fi

mkdir -p "${output_root}"
python -m far.experiments.type_mappability_machine annotate \
  --packet-dir "${packet_dir}" \
  --config "${config}" \
  --output-dir "${output_dir}" \
  --juror-id "${juror_id}" \
  --resume
