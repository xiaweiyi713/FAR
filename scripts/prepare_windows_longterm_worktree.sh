#!/usr/bin/env bash
# Guarded preparer for the Windows GPU D:-backed FAR long-term worktree.
#
# Default operation is dry-run, but the caller must explicitly select the
# registered WS2 family-dev commit or latest main for WS3. With --execute and
# FAR_WINDOWS_PREP_ALLOWED=1, it prepares only that target if the worktree is
# clean and no FAR GPU runner is active. It does not start training, run
# predictions, inspect held-out/test inputs, or delete checkpoints.

set -euo pipefail

usage() {
  cat <<'EOF'
usage: scripts/prepare_windows_longterm_worktree.sh {--family-dev|--latest} [--execute] [--install-boundary-units] [remote]

Dry-run only unless --execute is supplied. A target mode is mandatory:

  --family-dev  prepare the detached, preregistered WS2 source commit
                bd57585716b4c046db97311209a0d9f7ec340e6d
  --latest      fast-forward remote main to the current local HEAD for WS3 or
                non-WS2 maintenance

With --execute and FAR_WINDOWS_PREP_ALLOWED=1:
  1. refuse if WS2/WS3 FAR services are active;
  2. refuse if the D:-backed worktree is dirty;
  3. git fetch origin main;
  4. either detach at the frozen WS2 commit or fast-forward main;
  5. verify HEAD equals the selected target.

With --latest --install-boundary-units:
  also copy the tracked WS3 boundary systemd unit files into
  ~/.config/systemd/user and run daemon-reload after the fast-forward.

Examples:
  scripts/prepare_windows_longterm_worktree.sh --family-dev
  FAR_WINDOWS_PREP_ALLOWED=1 scripts/prepare_windows_longterm_worktree.sh --family-dev --execute
  scripts/prepare_windows_longterm_worktree.sh --latest
  FAR_WINDOWS_PREP_ALLOWED=1 scripts/prepare_windows_longterm_worktree.sh --latest --execute --install-boundary-units
EOF
}

execute=0
install_boundary_units=0
target_mode=""
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
    --family-dev)
      if [[ -n "${target_mode}" && "${target_mode}" != "family-dev" ]]; then
        echo "target modes are mutually exclusive" >&2
        exit 2
      fi
      target_mode="family-dev"
      shift
      ;;
    --latest)
      if [[ -n "${target_mode}" && "${target_mode}" != "latest" ]]; then
        echo "target modes are mutually exclusive" >&2
        exit 2
      fi
      target_mode="latest"
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

if [[ -z "${target_mode}" ]]; then
  echo "one target mode is required: --family-dev or --latest" >&2
  usage >&2
  exit 2
fi

if [[ "${target_mode}" == "family-dev" && "${install_boundary_units}" == "1" ]]; then
  echo "--install-boundary-units requires --latest" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
local_root="$(cd "${script_dir}/.." && pwd)"
if [[ "${target_mode}" == "family-dev" ]]; then
  expected_commit="bd57585716b4c046db97311209a0d9f7ec340e6d"
else
  expected_commit="${FAR_LONGTERM_EXPECTED_COMMIT:-$(git -C "${local_root}" rev-parse HEAD)}"
fi

echo "== FAR Windows long-term worktree preparer =="
date '+%Y-%m-%dT%H:%M:%S%z'
echo "remote=${remote}"
echo "worktree=${worktree}"
echo "target_mode=${target_mode}"
echo "expected_commit=${expected_commit}"
echo "mode=$([[ "${execute}" == "1" ]] && echo execute || echo dry-run)"
echo "install_boundary_units=$([[ "${install_boundary_units}" == "1" ]] && echo yes || echo no)"
echo "prep_allowed=$([[ "${FAR_WINDOWS_PREP_ALLOWED:-0}" == "1" ]] && echo yes || echo no)"

if [[ "${execute}" == "1" && "${FAR_WINDOWS_PREP_ALLOWED:-0}" != "1" ]]; then
  cat <<'EOF'

Refusing to modify the Windows GPU worktree because preparation is not
explicitly authorized. Re-run with:
  FAR_WINDOWS_PREP_ALLOWED=1 scripts/prepare_windows_longterm_worktree.sh <target-mode> --execute

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
EOF

if [[ "${target_mode}" == "family-dev" ]]; then
  cat <<EOF
verify ${expected_commit} is an ancestor of origin/main
git switch --detach ${expected_commit}
verify HEAD == ${expected_commit}
EOF
else
  cat <<EOF
git switch main
git merge --ff-only origin/main
verify HEAD == ${expected_commit}
EOF
fi

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
the same target mode, FAR_WINDOWS_PREP_ALLOWED=1, and --execute.
EOF
  exit 0
fi

echo
echo "== preparing remote worktree =="
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' -- \
  "${worktree}" "${expected_commit}" "${target_mode}" "${install_boundary_units}" <<'REMOTE'
set -euo pipefail

worktree="$1"
expected_commit="$2"
target_mode="$3"
install_boundary_units="$4"

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
  echo "remote worktree is dirty; refusing preparation" >&2
  printf "%s\n" "${dirty}" >&2
  exit 1
fi

git -C "${worktree}" fetch origin main
if [ "${target_mode}" = "family-dev" ]; then
  if ! git -C "${worktree}" merge-base --is-ancestor "${expected_commit}" origin/main; then
    echo "frozen WS2 commit is not an ancestor of origin/main" >&2
    exit 1
  fi
  git -C "${worktree}" switch --detach "${expected_commit}"
else
  git -C "${worktree}" switch main
  git -C "${worktree}" merge --ff-only origin/main
fi

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
