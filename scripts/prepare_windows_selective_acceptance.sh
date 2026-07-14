#!/usr/bin/env bash
# Guarded remote sync, unit install, and input preparation. Default is dry-run.

set -euo pipefail

execute=0
remote="${FAR_WINDOWS_REMOTE:-windows-gpu}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) execute=1 ;;
    --dry-run) execute=0 ;;
    -h|--help)
      echo "usage: scripts/prepare_windows_selective_acceptance.sh [--execute] [remote]"
      exit 0
      ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) remote="$1" ;;
  esac
  shift
done
if [[ "${execute}" == "1" && "${FAR_P14_PREP_ALLOWED:-0}" != "1" ]]; then
  echo "refusing P14 remote changes; set FAR_P14_PREP_ALLOWED=1 with --execute" >&2
  exit 3
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "${script_dir}/.." && pwd)"
expected_commit="${FAR_P14_EXPECTED_COMMIT:-$(git -C "${root}" rev-list -n 1 prereg-selective-acceptance-v2)}"
worktree="${FAR_P14_WORKTREE:-/mnt/d/FAR-workspace/FAR-longterm}"
output_root="/mnt/d/FAR-outputs/selective_acceptance_v2"

echo "remote=${remote} worktree=${worktree} output=${output_root} expected=${expected_commit} mode=$([[ ${execute} == 1 ]] && echo execute || echo dry-run)"
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- "${worktree}" <<'REMOTE'
set -u
worktree="$1"
for unit in far-selective-acceptance.service far-ollama-selective-acceptance.service \
  far-p5-ablations.service far-family-dev.service far-boundary.service; do
  printf '%s=' "${unit}"; systemctl --user is-active "${unit}" 2>/dev/null || true
done
printf 'head='; git -C "${worktree}" rev-parse HEAD 2>/dev/null || true
printf 'dirty='; [[ -n "$(git -C "${worktree}" status --porcelain 2>/dev/null)" ]] && echo yes || echo no
REMOTE
echo "planned: fetch exact prereg tag, fast-forward remote, install P14 units, build and verify label-free packet"
if [[ "${execute}" != "1" ]]; then
  echo "dry-run complete; no remote files or services changed"
  exit 0
fi

ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- \
  "${worktree}" "${output_root}" "${expected_commit}" <<'REMOTE'
set -euo pipefail
worktree="$1"; output_root="$2"; expected_commit="$3"
busy_units=(
  far-boundary.service far-family-dev.service far-family-dev@google.service
  far-family-dev@meta.service far-p5-ablations.service far-p6-prelabels.service
  far-ramdocs-phase-a.service far-ramdocs-round2.service
  far-ollama-boundary.service far-ollama-family-dev.service far-ollama-p5.service
  far-ollama-p6.service far-ollama-2plus4.service
  far-selective-acceptance.service far-ollama-selective-acceptance.service
)
for unit in "${busy_units[@]}"; do
  if [[ "$(systemctl --user is-active "${unit}" 2>/dev/null || true)" == "active" ]]; then
    echo "refusing preparation while ${unit} is active" >&2
    exit 75
  fi
done
[[ -z "$(git -C "${worktree}" status --porcelain --untracked-files=all)" ]] \
  || { echo "remote worktree is dirty" >&2; exit 1; }
git -C "${worktree}" fetch origin main tag prereg-selective-acceptance-v2
[[ "$(git -C "${worktree}" rev-parse origin/main)" == "${expected_commit}" ]] \
  || { echo "origin/main is not the exact P14 preregistration commit" >&2; exit 1; }
[[ "$(git -C "${worktree}" rev-list -n 1 prereg-selective-acceptance-v2)" == "${expected_commit}" ]] \
  || { echo "P14 preregistration tag mismatch" >&2; exit 1; }
git -C "${worktree}" switch main
git -C "${worktree}" merge --ff-only origin/main
[[ "$(git -C "${worktree}" rev-parse HEAD)" == "${expected_commit}" ]] \
  || { echo "remote HEAD differs from P14 preregistration" >&2; exit 1; }
[[ ! -L "${output_root}" ]] || { echo "P14 v2 output root must not be a symlink" >&2; exit 1; }
cache_path="${worktree}/outputs/cache/qwen_selective_acceptance_v2.sqlite3"
run_identity="${output_root}/runs/far/run_identity.json"
if [[ -e "${cache_path}" && ! -f "${run_identity}" ]]; then
  echo "refusing pre-existing P14 v2 cache without a bound run identity" >&2
  exit 1
fi
if [[ -e "${output_root}" && ! -f "${output_root}/input/protocol_manifest.json" ]]; then
  echo "refusing unknown pre-existing P14 v2 output root: ${output_root}" >&2
  exit 1
fi
mkdir -p "${HOME}/.config/systemd/user" "${output_root}"
cp "${worktree}/scripts/systemd/far-selective-acceptance.service" "${HOME}/.config/systemd/user/"
cp "${worktree}/scripts/systemd/far-ollama-selective-acceptance.service" "${HOME}/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user reset-failed far-selective-acceptance.service \
  far-ollama-selective-acceptance.service 2>/dev/null || true
source "${HOME}/miniconda3/etc/profile.d/conda.sh"
conda activate train
cd "${worktree}"
source scripts/windows_gpu_env.sh
python -m far.experiments.selective_acceptance verify-protocol
if [[ -e "${output_root}/input" ]]; then
  python -m far.experiments.selective_acceptance verify-packet --packet-dir "${output_root}/input"
else
  python -m far.experiments.selective_acceptance prepare --output-dir "${output_root}/input"
  python -m far.experiments.selective_acceptance verify-packet --packet-dir "${output_root}/input"
fi
echo "prepared P14 at ${expected_commit}"
REMOTE
