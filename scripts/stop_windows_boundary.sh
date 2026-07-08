#!/usr/bin/env bash
# Guarded stopper for WS3 boundary-mapping services on the Windows GPU WSL host.
#
# Default mode is dry-run: it prints current service/process state and the exact
# systemd stop commands that would be issued. It stops services only with
# --execute. The script does not delete checkpoints, write experiment files,
# inspect held-out/test inputs, or kill arbitrary processes.

set -euo pipefail

usage() {
  cat <<'EOF'
usage: scripts/stop_windows_boundary.sh [--execute] [--stop-ollama] [remote]

Default: dry-run only. Prints service/process state and planned stop commands.

With --execute:
  stop the WS3 boundary runner unit:
    far-boundary.service

With --stop-ollama:
  also stop far-ollama-boundary.service.

This script intentionally does not stop WS2 family-dev units. Use
scripts/stop_windows_family_dev.sh if WS2 is in scope.

Examples:
  scripts/stop_windows_boundary.sh
  scripts/stop_windows_boundary.sh --execute
  scripts/stop_windows_boundary.sh --execute --stop-ollama
EOF
}

execute=0
stop_ollama=0
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
    --stop-ollama)
      stop_ollama=1
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

runner_units=(
  far-boundary.service
)

planned_units=("${runner_units[@]}")
if [[ "${stop_ollama}" == "1" ]]; then
  planned_units+=(far-ollama-boundary.service)
fi

echo "== WS3 boundary guarded stopper =="
date '+%Y-%m-%dT%H:%M:%S%z'
echo "remote=${remote}"
echo "mode=$([[ "${execute}" == "1" ]] && echo execute || echo dry-run)"
echo "stop_ollama=$([[ "${stop_ollama}" == "1" ]] && echo yes || echo no)"

echo
echo "== current remote state =="
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' <<'REMOTE'
set -u

for unit in \
  far-boundary.service \
  far-ollama-boundary.service \
  far-family-dev@google.service \
  far-family-dev@meta.service \
  far-family-dev-mistral-resume.service \
  far-family-dev.service \
  far-ollama-family-dev.service; do
  printf "%s: " "${unit}"
  systemctl --user is-active "${unit}" 2>/dev/null || true
done

echo
echo "relevant processes:"
ps -eo pid,etime,pcpu,pmem,cmd \
  | grep -E 'python -m experiments.boundary|falsirag-boundary|ollama serve|llama-server|train.py' \
  | grep -v grep || true
REMOTE

echo
echo "== planned remote actions =="
for unit in "${planned_units[@]}"; do
  echo "systemctl --user stop ${unit}"
done
if [[ "${stop_ollama}" != "1" ]]; then
  echo "(not stopping far-ollama-boundary.service; pass --stop-ollama to include it)"
fi
echo "(not stopping WS2 family-dev units or far-ollama-family-dev.service)"

if [[ "${execute}" != "1" ]]; then
  cat <<'EOF'

Dry-run complete. No remote services were stopped.
To stop WS3 boundary runners, rerun with --execute.
EOF
  exit 0
fi

echo
echo "== stopping selected services =="
for unit in "${planned_units[@]}"; do
  echo "stopping ${unit}"
  ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" \
    "systemctl --user stop '${unit}'"
done

echo
echo "== post-stop state =="
ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote}" 'bash -s' <<'REMOTE'
set -u

for unit in \
  far-boundary.service \
  far-ollama-boundary.service \
  far-family-dev@google.service \
  far-family-dev@meta.service \
  far-family-dev-mistral-resume.service \
  far-family-dev.service \
  far-ollama-family-dev.service; do
  printf "%s: " "${unit}"
  systemctl --user is-active "${unit}" 2>/dev/null || true
done

echo
echo "relevant processes:"
ps -eo pid,etime,pcpu,pmem,cmd \
  | grep -E 'python -m experiments.boundary|falsirag-boundary|ollama serve|llama-server|train.py' \
  | grep -v grep || true
REMOTE
