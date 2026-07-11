#!/usr/bin/env bash
# Read-only, fail-closed preflight for P6 machine prelabels on windows-gpu.

set -euo pipefail

remote="${1:-${FAR_WINDOWS_REMOTE:-windows-gpu}}"
worktree="${FAR_P6_WORKTREE:-/mnt/d/FAR-workspace/FAR-longterm}"
packet_dir="${FAR_P6_PACKET_DIR:-/mnt/d/FAR-outputs/type_mappability_v1}"
require_ollama="${FAR_P6_REQUIRE_OLLAMA:-0}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
expected_commit="${FAR_P6_EXPECTED_COMMIT:-$(git -C "${script_dir}/.." rev-parse HEAD)}"

ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- \
  "${worktree}" "${packet_dir}" "${expected_commit}" "${require_ollama}" <<'REMOTE'
set -euo pipefail
trap 'echo "P6 remote preflight aborted at line ${LINENO}" >&2' ERR
worktree="$1"; packet_dir="$2"; expected_commit="$3"; require_ollama="$4"
errors=()
state() { systemctl --user is-active "$1" 2>/dev/null || true; }

for unit in \
  far-p5-ablations.service far-boundary.service far-family-dev.service \
  far-family-dev@google.service far-family-dev@meta.service far-ramdocs-round2.service \
  far-ollama-p5.service far-ollama-boundary.service far-ollama-family-dev.service \
  far-ollama-2plus4.service; do
  [[ "$(state "${unit}")" != "active" ]] \
    || errors+=("${unit} is active; the GPU is not available for P6")
done
for unit in far-p6-prelabels.service far-ollama-p6.service; do
  systemctl --user cat "${unit}" >/dev/null 2>&1 || errors+=("${unit} is not installed")
done
if [[ "${require_ollama}" == "1" && "$(state far-ollama-p6.service)" != "active" ]]; then
  errors+=("FAR_P6_REQUIRE_OLLAMA=1 but far-ollama-p6.service is not active")
fi

head="$(git -C "${worktree}" rev-parse HEAD 2>/dev/null || true)"
origin="$(git -C "${worktree}" rev-parse origin/main 2>/dev/null || true)"
dirty="$(git -C "${worktree}" status --porcelain --untracked-files=all 2>/dev/null || true)"
[[ "${head}" == "${expected_commit}" ]] || errors+=("worktree HEAD ${head:-missing} != ${expected_commit}")
[[ "${origin}" == "${expected_commit}" ]] || errors+=("origin/main ${origin:-missing} != ${expected_commit}")
[[ -z "${dirty}" ]] || errors+=("remote worktree is dirty")
[[ "$(loginctl show-user "${USER}" -p Linger --value 2>/dev/null || true)" == "yes" ]] \
  || errors+=("systemd linger is not enabled for ${USER}")

config="${worktree}/far/experiments/configs/qwen_boundary.yaml"
if [[ ! -f "${config}" ]]; then
  errors+=("missing P6 machine-prelabel config: ${config}")
else
  observed_config="$(sha256sum "${config}" | awk '{print $1}')"
  [[ "${observed_config}" == "d3a36b59d02eb4c086e87445d0757d466a25e9f3d2428d4bdc9a36bae9acc979" ]] \
    || errors+=("P6 machine-prelabel config fingerprint mismatch")
fi

gpu="$(/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used,utilization.gpu \
  --format=csv,noheader,nounits 2>/dev/null | head -n1 || true)"
memory="${gpu%%,*}"; utilization="${gpu##*,}"
memory="${memory//[[:space:]]/}"; utilization="${utilization//[[:space:]]/}"
if ! [[ "${memory}" =~ ^[0-9]+$ && "${utilization}" =~ ^[0-9]+$ ]]; then
  errors+=("could not read GPU state")
elif (( memory > 1500 || utilization > 20 )) \
  && [[ "$(state far-ollama-p6.service)" != "active" ]]; then
  errors+=("GPU busy: memory_used_mib=${memory}, utilization_pct=${utilization}")
fi

if (( ${#errors[@]} )); then
  printf 'P6 preflight failed:\n' >&2
  printf '  - %s\n' "${errors[@]}" >&2
  exit 1
fi

source "${HOME}/miniconda3/etc/profile.d/conda.sh"
conda activate train
cd "${worktree}"
source scripts/windows_gpu_env.sh
status_json="$(python -m far.experiments.type_mappability status --packet-dir "${packet_dir}")"
printf '%s\n' "${status_json}"
python3 -c '
import json, sys
s=json.load(sys.stdin)
machine=s.get("machine_prelabels", {})
if (
    s.get("valid_packet") is not True
    or machine.get("installed") is True
    or machine.get("identity_installed") is True
):
    raise SystemExit("P6 packet is invalid or machine prelabels are already installed")
' <<<"${status_json}"

if [[ "${require_ollama}" == "1" ]]; then
  tags="$(curl -fsS --max-time 5 http://127.0.0.1:11434/api/tags)"
  python3 -c '
import json, sys
p=json.load(sys.stdin)
expected="6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7"
rows=[m for m in p.get("models", []) if "qwen3.5:9b" in {m.get("name"),m.get("model")}]
if not rows or rows[0].get("digest") != expected:
    raise SystemExit("P6 Ollama model digest mismatch")
' <<<"${tags}"
fi
echo "P6 remote preflight valid: commit=${expected_commit} gpu=${memory}MiB/${utilization}%"
REMOTE
