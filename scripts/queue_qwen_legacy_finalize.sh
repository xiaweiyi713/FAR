#!/usr/bin/env bash
# Stage current main on the Windows GPU host and queue the post-legacy Qwen
# finalization. This is a local-side helper: run it from the Mac while the
# legacy 96e32b7 suite is still running. It does not overwrite the remote FAR
# workspace until the legacy suite tmux session has exited and all original
# legacy runs are complete.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_HOST="${REMOTE_HOST:-windows-gpu}"
FAR_ROOT="${FAR_ROOT:-/mnt/d/FAR-workspace/FAR}"
STAGE_ROOT="${STAGE_ROOT:-/mnt/d/FAR-workspace/far-main-stage}"
ARCHIVE_ROOT="${ARCHIVE_ROOT:-/mnt/d/FAR-workspace/archives}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/mnt/d/FAR-outputs}"
LATEST_PATH_FILE="${LATEST_PATH_FILE:-${OUTPUT_ROOT}/latest_far_corrected_suite_path.txt}"
WAIT_FOR_SESSION="${WAIT_FOR_SESSION:-far-qwen-suite-v3}"
WATCHDOG_SESSION="${WATCHDOG_SESSION:-far-verarag-stop-watchdog}"
FINALIZE_SESSION="${FINALIZE_SESSION:-far-qwen-legacy-finalize}"
POLL_SECONDS="${POLL_SECONDS:-60}"

cd "${ROOT}"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "tracked worktree is dirty; commit before staging a finalizer archive" >&2
  exit 2
fi

REV="$(git rev-parse --short=12 HEAD)"
ARCHIVE_PATH="${ARCHIVE_ROOT}/far-main-${REV}.tar"
REMOTE_LOG="${OUTPUT_ROOT}/qwen_legacy_finalize_${REV}.log"

echo "staging current FAR revision ${REV} on ${REMOTE_HOST}:${ARCHIVE_PATH}"
ssh "${REMOTE_HOST}" "mkdir -p '${ARCHIVE_ROOT}' '${OUTPUT_ROOT}'"
git archive HEAD | ssh "${REMOTE_HOST}" "cat > '${ARCHIVE_PATH}'"

ssh "${REMOTE_HOST}" bash -s -- \
  "${FINALIZE_SESSION}" \
  "${WAIT_FOR_SESSION}" \
  "${WATCHDOG_SESSION}" \
  "${FAR_ROOT}" \
  "${STAGE_ROOT}" \
  "${ARCHIVE_PATH}" \
  "${LATEST_PATH_FILE}" \
  "${OUTPUT_ROOT}" \
  "${REMOTE_LOG}" \
  "${POLL_SECONDS}" <<'REMOTE'
set -euo pipefail

FINALIZE_SESSION="$1"
WAIT_FOR_SESSION="$2"
WATCHDOG_SESSION="$3"
FAR_ROOT="$4"
STAGE_ROOT="$5"
ARCHIVE_PATH="$6"
LATEST_PATH_FILE="$7"
OUTPUT_ROOT="$8"
REMOTE_LOG="$9"
POLL_SECONDS="${10}"

if tmux has-session -t "${FINALIZE_SESSION}" 2>/dev/null; then
  echo "finalizer tmux session already exists: ${FINALIZE_SESSION}" >&2
  exit 2
fi

tmux new-session -d -s "${FINALIZE_SESSION}" bash -lc "
set -euo pipefail
echo FINALIZER_START \$(date -Is)
echo archive=${ARCHIVE_PATH}
echo waiting_for=${WAIT_FOR_SESSION}
while tmux has-session -t '${WAIT_FOR_SESSION}' 2>/dev/null; do
  sleep '${POLL_SECONDS}'
done
SUITE_ROOT=\$(cat '${LATEST_PATH_FILE}')
echo legacy_suite_done \$(date -Is) suite=\${SUITE_ROOT}

python3 - \"\${SUITE_ROOT}\" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
expected_runs = {
    'far': root / 'runs' / 'far' / 'run_manifest.json',
    'minus_typed_conflict': root / 'runs' / 'minus_typed_conflict' / 'run_manifest.json',
    'minus_refutation_query': root / 'runs' / 'minus_refutation_query' / 'run_manifest.json',
    'minus_boundary_query': root / 'runs' / 'minus_boundary_query' / 'run_manifest.json',
    'minus_typed_revision': root / 'runs' / 'minus_typed_revision' / 'run_manifest.json',
    'vanilla_rag': root / 'runs' / 'baselines' / 'vanilla_rag' / 'run_manifest.json',
    'multi_query_rag': root / 'runs' / 'baselines' / 'multi_query_rag' / 'run_manifest.json',
    'reflective_rag': root / 'runs' / 'baselines' / 'reflective_rag' / 'run_manifest.json',
    'crag_style_reproduction': root / 'runs' / 'baselines' / 'crag_style_reproduction' / 'run_manifest.json',
    'self_rag_style_reproduction': root / 'runs' / 'baselines' / 'self_rag_style_reproduction' / 'run_manifest.json',
}
problems = []
for label, path in expected_runs.items():
    if not path.is_file():
        problems.append(f'{label}: missing {path}')
        continue
    data = json.loads(path.read_text(encoding='utf-8'))
    checks = {
        'status': data.get('status') == 'complete',
        'completed': data.get('completed') == 60,
        'expected': data.get('expected') == 60,
        'errors': data.get('errors') == 0,
        'partial': data.get('partial') is False,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        problems.append(f'{label}: failed {failed} in {path}')
if problems:
    raise SystemExit('legacy suite incomplete:\n' + '\n'.join(problems))
print('legacy suite complete: FAR + four ablations + original five baselines')
PY

if tmux has-session -t '${WATCHDOG_SESSION}' 2>/dev/null; then
  tmux kill-session -t '${WATCHDOG_SESSION}' || true
fi

rm -rf '${STAGE_ROOT}'
mkdir -p '${STAGE_ROOT}' '${FAR_ROOT}'
tar -xf '${ARCHIVE_PATH}' -C '${STAGE_ROOT}'
rsync -az --delete \
  --exclude '/.git' --exclude '/.venv' --exclude '__pycache__' \
  --exclude '/outputs' --exclude '/output' --exclude '/build' --exclude '/dist' \
  '${STAGE_ROOT}/' '${FAR_ROOT}/'

source ~/miniconda3/etc/profile.d/conda.sh
conda activate train
cd '${FAR_ROOT}'
source scripts/windows_gpu_env.sh

if ! tmux has-session -t far-ollama 2>/dev/null; then
  tmux new-session -d -s far-ollama \"bash -lc 'source ~/miniconda3/etc/profile.d/conda.sh; conda activate train; source ${FAR_ROOT}/scripts/windows_gpu_env.sh; exec ollama serve >> ${OUTPUT_ROOT}/far-ollama.log 2>&1'\"
fi
for i in \$(seq 1 30); do
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [[ \"\${i}\" == 30 ]]; then
    echo 'ollama did not become ready' >&2
    exit 3
  fi
done

WAIT_FOR_SESSION='${WAIT_FOR_SESSION}' \
LATEST_PATH_FILE='${LATEST_PATH_FILE}' \
FAR_ROOT='${FAR_ROOT}' \
bash scripts/queue_qwen_counterrefine.sh

echo FINALIZER_DONE \$(date -Is)
" >> "${REMOTE_LOG}" 2>&1

tmux ls
echo "queued finalizer session: ${FINALIZE_SESSION}"
echo "remote log: ${REMOTE_LOG}"
REMOTE
