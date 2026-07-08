#!/usr/bin/env bash
# Guarded starter for the WS3 boundary-mapping run on the Windows GPU.
#
# Default mode is dry-run: it runs the read-only preflight and prints the exact
# remote actions that would be taken. It starts services only with --execute
# and FAR_BOUNDARY_TRAINING_ALLOWED=1.
# Do not use this script for held-out/test runs.

set -euo pipefail

usage() {
  cat <<'EOF'
usage: scripts/start_windows_boundary.sh [--execute] [remote]

Default: dry-run only. The script runs the read-only preflight and prints the
remote systemd commands that would be used.

With --execute and FAR_BOUNDARY_TRAINING_ALLOWED=1:
  1. run offline preflight;
  2. start far-ollama-boundary.service on the remote host;
  3. rerun preflight with FAR_BOUNDARY_REQUIRE_OLLAMA=1 to verify Qwen digest;
  4. start far-boundary.service.

Examples:
  scripts/start_windows_boundary.sh
  FAR_BOUNDARY_TRAINING_ALLOWED=1 scripts/start_windows_boundary.sh --execute
EOF
}

execute=0
remote="${FAR_WINDOWS_REMOTE:-windows-gpu}"

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
preflight="${script_dir}/preflight_windows_boundary.sh"

if [[ ! -x "${preflight}" ]]; then
  echo "missing executable preflight script: ${preflight}" >&2
  exit 1
fi

echo "== WS3 boundary guarded starter =="
date '+%Y-%m-%dT%H:%M:%S%z'
echo "remote=${remote}"
echo "mode=$([[ "${execute}" == "1" ]] && echo execute || echo dry-run)"
echo "training_allowed=$([[ "${FAR_BOUNDARY_TRAINING_ALLOWED:-0}" == "1" ]] && echo yes || echo no)"

if [[ "${execute}" == "1" && "${FAR_BOUNDARY_TRAINING_ALLOWED:-0}" != "1" ]]; then
  cat <<'EOF'

Refusing to start WS3 boundary services because training is not explicitly
authorized. Re-run only during an allowed training window with:
  FAR_BOUNDARY_TRAINING_ALLOWED=1 scripts/start_windows_boundary.sh --execute

No remote services were started.
EOF
  exit 3
fi

echo
echo "== offline preflight =="
"${preflight}" "${remote}"

cat <<EOF

== planned remote actions ==
1. systemctl --user start far-ollama-boundary.service
2. FAR_BOUNDARY_REQUIRE_OLLAMA=1 scripts/preflight_windows_boundary.sh ${remote}
3. systemctl --user start far-boundary.service
4. journalctl --user -u far-boundary.service -f
EOF

if [[ "${execute}" != "1" ]]; then
  cat <<'EOF'

Dry-run complete. No remote services were started.
To start WS3 boundary mapping when training is allowed, rerun with
FAR_BOUNDARY_TRAINING_ALLOWED=1 and --execute.
EOF
  exit 0
fi

echo
echo "== starting boundary Ollama service =="
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user start far-ollama-boundary.service"

echo
echo "== digest preflight with Ollama online =="
FAR_BOUNDARY_REQUIRE_OLLAMA=1 "${preflight}" "${remote}"

echo
echo "== starting boundary service =="
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user start far-boundary.service"

echo
echo "== service status =="
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user show far-boundary.service far-ollama-boundary.service -p LoadState -p ActiveState -p SubState -p MainPID -p NRestarts -p Result --no-pager"

cat <<EOF

Started far-boundary.service. Monitor with:
  journalctl --user -u far-boundary.service -f
EOF
