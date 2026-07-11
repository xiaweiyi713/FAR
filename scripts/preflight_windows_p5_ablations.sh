#!/usr/bin/env bash
# Read-only, fail-closed preflight for the registered P5 run on windows-gpu.

set -euo pipefail

remote="${1:-${FAR_WINDOWS_REMOTE:-windows-gpu}}"
worktree="${FAR_P5_WORKTREE:-/mnt/d/FAR-workspace/FAR-longterm}"
output_dir="${FAR_P5_OUTPUT_DIR:-/mnt/d/FAR-outputs/p5_ramdocs_v1}"
require_ollama="${FAR_P5_REQUIRE_OLLAMA:-0}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
expected_commit="${FAR_P5_EXPECTED_COMMIT:-$(git -C "${script_dir}/.." rev-parse HEAD)}"

ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- \
  "${worktree}" "${output_dir}" "${expected_commit}" "${require_ollama}" <<'REMOTE'
set -euo pipefail

worktree="$1"
output_dir="$2"
expected_commit="$3"
require_ollama="$4"
errors=()

state() { systemctl --user is-active "$1" 2>/dev/null || true; }
for unit in \
  far-boundary.service far-family-dev.service far-family-dev@google.service \
  far-family-dev@meta.service far-ramdocs-round2.service \
  far-ollama-boundary.service far-ollama-family-dev.service \
  far-ollama-2plus4.service; do
  if [[ "$(state "${unit}")" == "active" ]]; then
    errors+=("${unit} is active; the GPU is not available for P5")
  fi
done
for unit in far-p5-ablations.service far-ollama-p5.service; do
  if ! systemctl --user cat "${unit}" >/dev/null 2>&1; then
    errors+=("${unit} is not installed")
  fi
done
if [[ "${require_ollama}" == "1" && "$(state far-ollama-p5.service)" != "active" ]]; then
  errors+=("FAR_P5_REQUIRE_OLLAMA=1 but far-ollama-p5.service is not active")
fi

if [[ ! -d "${worktree}/.git" ]]; then
  errors+=("missing worktree: ${worktree}")
else
  head="$(git -C "${worktree}" rev-parse HEAD 2>/dev/null || true)"
  origin="$(git -C "${worktree}" rev-parse origin/main 2>/dev/null || true)"
  dirty="$(git -C "${worktree}" status --porcelain --untracked-files=all 2>/dev/null || true)"
  [[ "${head}" == "${expected_commit}" ]] || errors+=("worktree HEAD ${head:-missing} != ${expected_commit}")
  [[ "${origin}" == "${expected_commit}" ]] || errors+=("origin/main ${origin:-missing} != ${expected_commit}")
  [[ -z "${dirty}" ]] || errors+=("remote worktree is dirty")
fi

if [[ "$(loginctl show-user "${USER}" -p Linger --value 2>/dev/null || true)" != "yes" ]]; then
  errors+=("systemd linger is not enabled for ${USER}")
fi
gpu="$(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used,utilization.gpu \
  --format=csv,noheader,nounits 2>/dev/null | head -n1 || true)"
memory="${gpu%%,*}"
utilization="${gpu##*,}"
memory="${memory//[[:space:]]/}"
utilization="${utilization//[[:space:]]/}"
if ! [[ "${memory}" =~ ^[0-9]+$ && "${utilization}" =~ ^[0-9]+$ ]]; then
  errors+=("could not read GPU state")
elif (( memory > 1500 || utilization > 20 )) \
  && [[ "$(state far-ollama-p5.service)" != "active" ]]; then
  errors+=("GPU busy: memory_used_mib=${memory}, utilization_pct=${utilization}")
fi
free_kib="$(df -Pk "$(dirname "${output_dir}")" 2>/dev/null | awk 'NR==2 {print $4}')"
if ! [[ "${free_kib}" =~ ^[0-9]+$ ]] || (( free_kib < 10485760 )); then
  errors+=("P5 output volume has less than 10 GiB free")
fi

if (( ${#errors[@]} )); then
  printf 'P5 preflight failed:\n' >&2
  printf '  - %s\n' "${errors[@]}" >&2
  exit 1
fi

source "${HOME}/miniconda3/etc/profile.d/conda.sh"
conda activate train
cd "${worktree}"
source scripts/windows_gpu_env.sh
args=(status --output-dir "${output_dir}")
if [[ "${require_ollama}" != "1" ]]; then
  args+=(--skip-runtime)
fi
status_json="$(FAR_OLLAMA_IDENTITY_RETRY_SECONDS=0 \
  python -m far.experiments.p5_ablations "${args[@]}")"
printf '%s\n' "${status_json}"
python3 -c '
import json, sys
status = json.load(sys.stdin)
ready = status.get("valid_inputs") is True and status.get("source_ready") is True
if sys.argv[1] == "1":
    ready = ready and status.get("runtime_ready") is True and status.get("ready_to_run") is True
if not ready:
    raise SystemExit("P5 application preflight is not ready")
' "${require_ollama}" <<<"${status_json}"
echo "P5 remote preflight valid: commit=${expected_commit} gpu=${memory}MiB/${utilization}%"
REMOTE
