#!/usr/bin/env bash
# Guarded remote sync, unit install, and blank P6 packet preparation.

set -euo pipefail
execute=0; remote="${FAR_WINDOWS_REMOTE:-windows-gpu}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) execute=1 ;;
    --dry-run) execute=0 ;;
    -h|--help) echo "usage: scripts/prepare_windows_p6_prelabels.sh [--execute] [remote]"; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) remote="$1" ;;
  esac
  shift
done
if [[ "${execute}" == "1" && "${FAR_P6_PREP_ALLOWED:-0}" != "1" ]]; then
  echo "refusing remote changes; set FAR_P6_PREP_ALLOWED=1 with --execute" >&2
  exit 3
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "${script_dir}/.." && pwd)"
expected_commit="${FAR_P6_EXPECTED_COMMIT:-$(git -C "${root}" rev-parse HEAD)}"
worktree="${FAR_P6_WORKTREE:-/mnt/d/FAR-workspace/FAR-longterm}"
packet_dir="${FAR_P6_PACKET_DIR:-/mnt/d/FAR-outputs/type_mappability_v1}"
echo "remote=${remote} expected_commit=${expected_commit} packet=${packet_dir} mode=$([[ ${execute} == 1 ]] && echo execute || echo dry-run)"
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- "${worktree}" "${packet_dir}" <<'REMOTE'
set -u
worktree="$1"; packet_dir="$2"
printf 'head='; git -C "${worktree}" rev-parse HEAD 2>/dev/null || true
printf 'origin_main='; git -C "${worktree}" rev-parse origin/main 2>/dev/null || true
printf 'dirty='; [[ -n "$(git -C "${worktree}" status --porcelain 2>/dev/null)" ]] && echo yes || echo no
printf 'packet='; [[ -f "${packet_dir}/packet_manifest.json" ]] && echo present || echo absent
for unit in far-p6-prelabels.service far-ollama-p6.service far-p5-ablations.service; do
  printf '%s=' "${unit}"; systemctl --user is-active "${unit}" 2>/dev/null || true
done
REMOTE
echo "planned: exact origin/main sync, install P6 units, prepare external blank packet"
if [[ "${execute}" != "1" ]]; then
  echo "dry-run complete; no remote files changed"
  exit 0
fi

ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- \
  "${worktree}" "${packet_dir}" "${expected_commit}" <<'REMOTE'
set -euo pipefail
worktree="$1"; packet_dir="$2"; expected_commit="$3"
for unit in far-p6-prelabels.service far-ollama-p6.service far-p5-ablations.service far-boundary.service far-family-dev.service far-ramdocs-round2.service; do
  [[ "$(systemctl --user is-active "${unit}" 2>/dev/null || true)" != "active" ]] \
    || { echo "${unit} is active" >&2; exit 75; }
done
[[ -z "$(git -C "${worktree}" status --porcelain --untracked-files=all)" ]] \
  || { echo "remote worktree is dirty" >&2; exit 1; }
git -C "${worktree}" fetch origin main
[[ "$(git -C "${worktree}" rev-parse origin/main)" == "${expected_commit}" ]] \
  || { echo "origin/main is not the exact expected commit" >&2; exit 1; }
git -C "${worktree}" switch main
git -C "${worktree}" merge --ff-only origin/main
mkdir -p "${HOME}/.config/systemd/user"
cp "${worktree}/scripts/systemd/far-ollama-p6.service" "${HOME}/.config/systemd/user/"
cp "${worktree}/scripts/systemd/far-p6-prelabels.service" "${HOME}/.config/systemd/user/"
systemctl --user daemon-reload
source "${HOME}/miniconda3/etc/profile.d/conda.sh"
conda activate train
cd "${worktree}"
source scripts/windows_gpu_env.sh
if [[ ! -e "${packet_dir}" ]]; then
  python -m far.experiments.type_mappability prepare --output-dir "${packet_dir}"
else
  status_json="$(python -m far.experiments.type_mappability status --packet-dir "${packet_dir}")"
  python3 -c '
import json, sys
if json.load(sys.stdin).get("valid_packet") is not True:
    raise SystemExit("existing remote P6 packet is invalid")
' <<<"${status_json}"
fi
echo "prepared P6 remote packet at ${packet_dir}"
REMOTE
