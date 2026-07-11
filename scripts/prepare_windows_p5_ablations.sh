#!/usr/bin/env bash
# Guarded sync/unit installer for the remote P5 worktree. Default is dry-run.

set -euo pipefail

execute=0
remote="${FAR_WINDOWS_REMOTE:-windows-gpu}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) execute=1 ;;
    --dry-run) execute=0 ;;
    -h|--help)
      echo "usage: scripts/prepare_windows_p5_ablations.sh [--execute] [remote]"
      exit 0
      ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) remote="$1" ;;
  esac
  shift
done
if [[ "${execute}" == "1" && "${FAR_P5_PREP_ALLOWED:-0}" != "1" ]]; then
  echo "refusing remote changes; set FAR_P5_PREP_ALLOWED=1 with --execute" >&2
  exit 3
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "${script_dir}/.." && pwd)"
expected_commit="${FAR_P5_EXPECTED_COMMIT:-$(git -C "${root}" rev-parse HEAD)}"
worktree="${FAR_P5_WORKTREE:-/mnt/d/FAR-workspace/FAR-longterm}"

echo "remote=${remote} worktree=${worktree} expected_commit=${expected_commit} mode=$([[ ${execute} == 1 ]] && echo execute || echo dry-run)"
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- "${worktree}" <<'REMOTE'
set -u
worktree="$1"
for unit in far-p5-ablations.service far-ollama-p5.service far-boundary.service far-family-dev.service far-ramdocs-round2.service; do
  printf '%s=' "${unit}"; systemctl --user is-active "${unit}" 2>/dev/null || true
done
printf 'head='; git -C "${worktree}" rev-parse HEAD 2>/dev/null || true
printf 'origin_main='; git -C "${worktree}" rev-parse origin/main 2>/dev/null || true
printf 'dirty='; [[ -n "$(git -C "${worktree}" status --porcelain 2>/dev/null)" ]] && echo yes || echo no
REMOTE
echo "planned: fetch origin/main, fast-forward ${worktree}/main to ${expected_commit}, install P5 units"
if [[ "${execute}" != "1" ]]; then
  echo "dry-run complete; no remote files changed"
  exit 0
fi

ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- \
  "${worktree}" "${expected_commit}" <<'REMOTE'
set -euo pipefail
worktree="$1"
expected_commit="$2"
for unit in far-p5-ablations.service far-ollama-p5.service far-boundary.service far-family-dev.service far-ramdocs-round2.service far-ollama-boundary.service far-ollama-family-dev.service far-ollama-2plus4.service; do
  [[ "$(systemctl --user is-active "${unit}" 2>/dev/null || true)" != "active" ]] \
    || { echo "${unit} is active" >&2; exit 75; }
done
[[ -z "$(git -C "${worktree}" status --porcelain --untracked-files=all)" ]] \
  || { echo "remote worktree is dirty" >&2; exit 1; }
git -C "${worktree}" fetch origin main
[[ "$(git -C "${worktree}" rev-parse origin/main)" == "${expected_commit}" ]] \
  || { echo "origin/main is not the exact expected commit; publish or select it first" >&2; exit 1; }
git -C "${worktree}" switch main
git -C "${worktree}" merge --ff-only origin/main
[[ "$(git -C "${worktree}" rev-parse HEAD)" == "${expected_commit}" ]] \
  || { echo "remote HEAD does not equal expected commit" >&2; exit 1; }
mkdir -p "${HOME}/.config/systemd/user"
cp "${worktree}/scripts/systemd/far-ollama-p5.service" "${HOME}/.config/systemd/user/"
cp "${worktree}/scripts/systemd/far-p5-ablations.service" "${HOME}/.config/systemd/user/"
systemctl --user daemon-reload
echo "prepared P5 remote at ${expected_commit}"
REMOTE
