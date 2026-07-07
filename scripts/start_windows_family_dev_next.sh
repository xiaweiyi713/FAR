#!/usr/bin/env bash
# Guarded starter for the next WS2 family-dev run on the Windows GPU.
#
# Default mode is dry-run: it runs the read-only preflight and prints the exact
# remote actions that would be taken.  It starts services only with --execute
# and FAR_FAMILY_DEV_TRAINING_ALLOWED=1.
# Do not use this script for held-out/test runs.

set -euo pipefail

usage() {
  cat <<'EOF'
usage: scripts/start_windows_family_dev_next.sh {google|meta} [--execute] [remote]

Default: dry-run only.  The script runs the read-only preflight and prints the
remote systemd commands that would be used.

With --execute and FAR_FAMILY_DEV_TRAINING_ALLOWED=1:
  1. run offline preflight;
  2. start far-ollama-family-dev.service on the remote host;
  3. rerun preflight with FAR_FAMILY_DEV_REQUIRE_OLLAMA=1 to verify digest;
  4. start far-family-dev@<family>.service.

Examples:
  scripts/start_windows_family_dev_next.sh google
  FAR_FAMILY_DEV_TRAINING_ALLOWED=1 scripts/start_windows_family_dev_next.sh google --execute
EOF
}

family="${1:-}"
if [[ -z "${family}" || "${family}" == "-h" || "${family}" == "--help" ]]; then
  usage
  exit 0
fi
shift || true

case "${family}" in
  google|meta) ;;
  *)
    echo "family must be google or meta; got ${family}" >&2
    exit 2
    ;;
esac

execute=0
remote="${FAR_WINDOWS_REMOTE:-windows-gpu}"
while [[ $# -gt 0 ]]; do
  case "$1" in
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
preflight="${script_dir}/preflight_windows_family_dev_next.sh"

if [[ ! -x "${preflight}" ]]; then
  echo "missing executable preflight script: ${preflight}" >&2
  exit 1
fi

echo "== WS2 family-dev guarded starter =="
date '+%Y-%m-%dT%H:%M:%S%z'
echo "family=${family}"
echo "remote=${remote}"
echo "mode=$([[ "${execute}" == "1" ]] && echo execute || echo dry-run)"
echo "training_allowed=$([[ "${FAR_FAMILY_DEV_TRAINING_ALLOWED:-0}" == "1" ]] && echo yes || echo no)"

if [[ "${execute}" == "1" && "${FAR_FAMILY_DEV_TRAINING_ALLOWED:-0}" != "1" ]]; then
  cat <<'EOF'

Refusing to start WS2 family-dev services because training is not explicitly
authorized. Re-run only during an allowed training window with:
  FAR_FAMILY_DEV_TRAINING_ALLOWED=1 scripts/start_windows_family_dev_next.sh <family> --execute

No remote services were started.
EOF
  exit 3
fi

echo
echo "== offline preflight =="
"${preflight}" "${family}" "${remote}"

cat <<EOF

== planned remote actions ==
1. systemctl --user start far-ollama-family-dev.service
2. FAR_FAMILY_DEV_REQUIRE_OLLAMA=1 scripts/preflight_windows_family_dev_next.sh ${family} ${remote}
3. systemctl --user start far-family-dev@${family}.service
4. scripts/watch_windows_family_dev.sh ${remote}
EOF

if [[ "${execute}" != "1" ]]; then
  cat <<'EOF'

Dry-run complete. No remote services were started.
To start the run when training is allowed, rerun with
FAR_FAMILY_DEV_TRAINING_ALLOWED=1 and --execute.
EOF
  exit 0
fi

echo
echo "== starting Ollama service =="
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user start far-ollama-family-dev.service"

echo
echo "== digest preflight with Ollama online =="
FAR_FAMILY_DEV_REQUIRE_OLLAMA=1 "${preflight}" "${family}" "${remote}"

echo
echo "== starting family service =="
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user start far-family-dev@${family}.service"

echo
echo "== service status =="
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
  "systemctl --user show far-family-dev@${family}.service far-ollama-family-dev.service -p LoadState -p ActiveState -p SubState -p MainPID -p NRestarts -p Result --no-pager"

cat <<EOF

Started far-family-dev@${family}.service. Monitor with:
  scripts/watch_windows_family_dev.sh ${remote}
EOF
