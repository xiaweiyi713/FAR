#!/usr/bin/env bash
# Guarded preparer for the Windows GPU D:-backed FAR long-term worktree.
#
# Default mode is dry-run: it prints current state and planned commands. With
# --execute and FAR_WINDOWS_PREP_ALLOWED=1, it fast-forwards the remote main
# branch to the current local HEAD if the remote worktree is clean and no FAR GPU
# runner service is active. It does not start training, run predictions, inspect
# held-out/test inputs, or delete checkpoints.

set -euo pipefail

usage() {
  cat <<'EOF'
usage: scripts/prepare_windows_longterm_worktree.sh [--execute] [--install-boundary-units] [remote]

Default: dry-run only. Prints remote service/worktree state and planned actions.

With --execute and FAR_WINDOWS_PREP_ALLOWED=1:
  1. refuse if WS2/WS3 FAR services are active;
  2. refuse if the D:-backed worktree is dirty;
  3. git fetch origin main;
  4. git switch main;
  5. git merge --ff-only origin/main;
  6. verify HEAD equals the current local commit.

With --install-boundary-units:
  also copy the tracked WS3 boundary systemd unit files into
  ~/.config/systemd/user and run daemon-reload after the fast-forward.

Examples:
  scripts/prepare_windows_longterm_worktree.sh
  FAR_WINDOWS_PREP_ALLOWED=1 scripts/prepare_windows_longterm_worktree.sh --execute
  FAR_WINDOWS_PREP_ALLOWED=1 scripts/prepare_windows_longterm_worktree.sh --execute --install-boundary-units
EOF
}

execute=0
install_boundary_units=0
remote="${FAR_WINDOWS_REMOTE:-windows-gpu}"
worktree="${FAR_LONGTERM_WORKTREE:-/mnt/d/FAR-workspace/FAR-longterm}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --execute)
      execute=1
      shift
      ;;
    --dry-run)
      execute=0
      shift
      ;;
    --install-boundary-units)
      install_boundary_units=1
      shift
      ;;
    -*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      remote="$1"
      shift
      ;;
  esac
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
local_root="$(cd "${script_dir}/.." && pwd)"
expected_commit="${FAR_LONGTERM_EXPECTED_COMMIT:-$(git -C "${local_root}" rev-parse HEAD)}"

echo "== FAR Windows long-term worktree preparer =="
date '+%Y-%m-%dT%H:%M:%S%z'
echo "remote=${remote}"
echo "worktree=${worktree}"
echo "expected_commit=${expected_commit}"
echo "mode=$([[ "${execute}" == "1" ]] && echo execute || echo dry-run)"
echo "install_boundary_units=$([[ "${install_boundary_units}" == "1" ]] && echo yes || echo no)"
echo "prep_allowed=$([[ "${FAR_WINDOWS_PREP_ALLOWED:-0}" == "1" ]] && echo yes || echo no)"

if [[ "${execute}" == "1" && "${FAR_WINDOWS_PREP_ALLOWED:-0}" != "1" ]]; then
  cat <<'EOF'

Refusing to modify the Windows GPU worktree because preparation is not
explicitly authorized. Re-run with:
  FAR_WINDOWS_PREP_ALLOWED=1 scripts/prepare_windows_longterm_worktree.sh --execute

No remote files were changed.
EOF
  exit 3
fi

echo
echo "== current remote state =="
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- "${worktree}" <<'REMOTE'
set -u
worktree="$1"

for unit in \
  far-family-dev@google.service \
  far-family-dev@meta.service \
  far-family-dev-mistral-resume.service \
  far-family-dev.service \
  far-ollama-family-dev.service \
  far-boundary.service \
  far-ollama-boundary.service; do
  printf "%s: " "${unit}"
  systemctl --user is-active "${unit}" 2>/dev/null || true
done

if [ -d "${worktree}/.git" ]; then
  echo
  echo "worktree_head=$(git -C "${worktree}" rev-parse --short HEAD 2>/dev/null || true)"
  echo "worktree_origin_main=$(git -C "${worktree}" rev-parse --short origin/main 2>/dev/null || true)"
  dirty="$(git -C "${worktree}" status --porcelain 2>/dev/null || true)"
  if [ -n "${dirty}" ]; then
    echo "worktree_dirty=yes"
    printf "%s\n" "${dirty}" | sed -n '1,20p'
  else
    echo "worktree_dirty=no"
  fi
else
  echo
  echo "missing_worktree=${worktree}"
fi
REMOTE

cat <<EOF

== planned remote actions ==
cd ${worktree}
git fetch origin main
git switch main
git merge --ff-only origin/main
verify HEAD == ${expected_commit}
EOF

if [[ "${install_boundary_units}" == "1" ]]; then
  cat <<'EOF'
mkdir -p ~/.config/systemd/user
cp scripts/systemd/far-ollama-boundary.service ~/.config/systemd/user/
cp scripts/systemd/far-boundary.service ~/.config/systemd/user/
systemctl --user daemon-reload
EOF
fi

if [[ "${execute}" != "1" ]]; then
  cat <<'EOF'

Dry-run complete. No remote files were changed.
To prepare the D:-backed worktree when training/prep is allowed, rerun with
FAR_WINDOWS_PREP_ALLOWED=1 and --execute.
EOF
  exit 0
fi

echo
echo "== preparing remote worktree =="
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- \
  "${worktree}" "${expected_commit}" "${install_boundary_units}" <<'REMOTE'
set -euo pipefail

worktree="$1"
expected_commit="$2"
install_boundary_units="$3"

for unit in \
  far-family-dev@google.service \
  far-family-dev@meta.service \
  far-family-dev-mistral-resume.service \
  far-family-dev.service \
  far-boundary.service; do
  state="$(systemctl --user is-active "${unit}" 2>/dev/null || true)"
  if [ "${state}" = "active" ]; then
    echo "${unit} is active; refusing to prepare worktree" >&2
    exit 75
  fi
done

if [ ! -d "${worktree}/.git" ]; then
  echo "missing worktree: ${worktree}" >&2
  exit 1
fi

dirty="$(git -C "${worktree}" status --porcelain)"
if [ -n "${dirty}" ]; then
  echo "remote worktree is dirty; refusing fast-forward" >&2
  printf "%s\n" "${dirty}" >&2
  exit 1
fi

git -C "${worktree}" fetch origin main
git -C "${worktree}" switch main
git -C "${worktree}" merge --ff-only origin/main

head="$(git -C "${worktree}" rev-parse HEAD)"
if [ "${head}" != "${expected_commit}" ]; then
  echo "remote HEAD ${head} != expected ${expected_commit}" >&2
  exit 1
fi

if [ "${install_boundary_units}" = "1" ]; then
  mkdir -p "${HOME}/.config/systemd/user"
  cp "${worktree}/scripts/systemd/far-ollama-boundary.service" "${HOME}/.config/systemd/user/"
  cp "${worktree}/scripts/systemd/far-boundary.service" "${HOME}/.config/systemd/user/"
  systemctl --user daemon-reload
fi

echo "prepared_head=$(git -C "${worktree}" rev-parse --short HEAD)"
REMOTE

cat <<EOF

Remote worktree prepared. Before starting any run, use the relevant guarded
starter dry-run:
  scripts/start_windows_family_dev_next.sh google
  scripts/start_windows_boundary.sh
EOF
