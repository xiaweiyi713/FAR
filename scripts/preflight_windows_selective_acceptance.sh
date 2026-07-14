#!/usr/bin/env bash
# Read-only, fail-closed P14 preflight. It never starts a service.

set -euo pipefail

remote="${1:-${FAR_WINDOWS_REMOTE:-windows-gpu}}"
worktree="${FAR_P14_WORKTREE:-/mnt/d/FAR-workspace/FAR-longterm}"
output_root="${FAR_P14_OUTPUT_ROOT:-/mnt/d/FAR-outputs/selective_acceptance_v1}"
require_ollama="${FAR_P14_REQUIRE_OLLAMA:-0}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
expected_commit="${FAR_P14_EXPECTED_COMMIT:-$(git -C "${script_dir}/.." rev-list -n 1 prereg-selective-acceptance-v1)}"

ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- \
  "${worktree}" "${output_root}" "${expected_commit}" "${require_ollama}" <<'REMOTE'
set -euo pipefail

worktree="$1"
output_root="$2"
expected_commit="$3"
require_ollama="$4"
errors=()
state() { systemctl --user is-active "$1" 2>/dev/null || true; }

busy_units=(
  far-boundary.service far-family-dev.service far-family-dev@google.service
  far-family-dev@meta.service far-p5-ablations.service far-p6-prelabels.service
  far-ramdocs-phase-a.service far-ramdocs-round2.service
  far-ollama-boundary.service far-ollama-family-dev.service far-ollama-p5.service
  far-ollama-p6.service far-ollama-2plus4.service
)
for unit in "${busy_units[@]}"; do
  [[ "$(state "${unit}")" != "active" ]] \
    || errors+=("${unit} is active; windows-gpu is not available for P14")
done
for unit in far-selective-acceptance.service far-ollama-selective-acceptance.service; do
  systemctl --user cat "${unit}" >/dev/null 2>&1 || errors+=("${unit} is not installed")
done
if [[ "${require_ollama}" != "1" ]] \
  && [[ "$(state far-selective-acceptance.service)" == "active" ]]; then
  errors+=("far-selective-acceptance.service is already active; inspect it instead of starting again")
fi
if [[ "${require_ollama}" == "1" ]] \
  && [[ "$(state far-ollama-selective-acceptance.service)" != "active" ]]; then
  errors+=("P14 requires Ollama but its dedicated service is not active")
fi

if [[ ! -d "${worktree}/.git" ]]; then
  errors+=("missing worktree: ${worktree}")
else
  head="$(git -C "${worktree}" rev-parse HEAD 2>/dev/null || true)"
  tag="$(git -C "${worktree}" rev-list -n 1 prereg-selective-acceptance-v1 2>/dev/null || true)"
  dirty="$(git -C "${worktree}" status --porcelain --untracked-files=all 2>/dev/null || true)"
  [[ "${head}" == "${expected_commit}" ]] \
    || errors+=("worktree HEAD ${head:-missing} != ${expected_commit}")
  [[ "${tag}" == "${expected_commit}" ]] \
    || errors+=("remote preregistration tag ${tag:-missing} != ${expected_commit}")
  [[ -z "${dirty}" ]] || errors+=("remote worktree is dirty")
fi

gpu="$(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used,utilization.gpu \
  --format=csv,noheader,nounits 2>/dev/null | head -n1 || true)"
memory="${gpu%%,*}"; utilization="${gpu##*,}"
memory="${memory//[[:space:]]/}"; utilization="${utilization//[[:space:]]/}"
if ! [[ "${memory}" =~ ^[0-9]+$ && "${utilization}" =~ ^[0-9]+$ ]]; then
  errors+=("could not read GPU state")
elif (( memory > 1500 || utilization > 20 )); then
  errors+=("GPU busy: memory_used_mib=${memory}, utilization_pct=${utilization}")
fi
compute_apps="$(/usr/lib/wsl/lib/nvidia-smi --query-compute-apps=pid,process_name \
  --format=csv,noheader 2>/dev/null || true)"
if [[ -n "${compute_apps}" ]]; then
  errors+=("GPU has active compute applications: ${compute_apps//$'\n'/; }")
fi
foreign_processes="$(pgrep -af 'far\.experiments|llama-server|train\.py' || true)"
if [[ -n "${foreign_processes}" ]]; then
  errors+=("model or FAR process already active: ${foreign_processes//$'\n'/; }")
fi
if [[ "${require_ollama}" != "1" ]]; then
  ollama_processes="$(pgrep -af 'ollama serve' || true)"
  if [[ -n "${ollama_processes}" ]]; then
    errors+=("Ollama is already active outside the P14 start sequence: ${ollama_processes//$'\n'/; }")
  fi
fi

free_kib="$(df -Pk "$(dirname "${output_root}")" 2>/dev/null | awk 'NR==2 {print $4}')"
if ! [[ "${free_kib}" =~ ^[0-9]+$ ]] || (( free_kib < 10485760 )); then
  errors+=("P14 output volume has less than 10 GiB free")
fi
if (( ${#errors[@]} )); then
  printf 'P14 preflight failed:\n' >&2
  printf '  - %s\n' "${errors[@]}" >&2
  exit 1
fi

source "${HOME}/miniconda3/etc/profile.d/conda.sh"
conda activate train
cd "${worktree}"
source scripts/windows_gpu_env.sh
python -m far.experiments.selective_acceptance verify-protocol >/tmp/far-p14-protocol.json
python -m far.experiments.selective_acceptance verify-packet \
  --packet-dir "${output_root}/input" >/tmp/far-p14-packet.json
python3 -c '
import json
from pathlib import Path
for name in ("protocol", "packet"):
    value = json.loads(Path(f"/tmp/far-p14-{name}.json").read_text())
    if value.get("valid") is not True:
        errors = value.get("errors")
        raise SystemExit(f"P14 {name} audit failed: {errors}")
' 
if [[ "${require_ollama}" == "1" ]]; then
  python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=10) as response:
    payload = json.load(response)
matches = [
    row for row in payload.get("models", [])
    if "qwen3.5:9b" in {row.get("name"), row.get("model")}
]
expected = "6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7"
if len(matches) != 1 or matches[0].get("digest") != expected:
    raise SystemExit("P14 Ollama model digest mismatch")
PY
fi
echo "P14 preflight valid: commit=${expected_commit} gpu=${memory}MiB/${utilization}%"
REMOTE
