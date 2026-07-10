#!/usr/bin/env bash
# Sync and evaluate the completed corrected FAR vs minus-typed Qwen dev pair.
#
# This script is intended to run on the Mac. It is read-only on the remote host
# and refuses to copy or score partial runs.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_HOST="${REMOTE_HOST:-windows-gpu}"
REMOTE_LATEST_PATH_FILE="${REMOTE_LATEST_PATH_FILE:-/mnt/d/FAR-outputs/latest_far_corrected_suite_path.txt}"
LOCAL_ROOT="${LOCAL_ROOT:-${ROOT}/outputs/remote_qwen_core_comparison}"
RESAMPLES="${RESAMPLES:-2000}"
SEED="${SEED:-1729}"

cd "${ROOT}"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "tracked worktree is dirty; commit before evaluating the frozen pair" >&2
  exit 2
fi

REMOTE_ROOT="$(ssh "${REMOTE_HOST}" "cat '${REMOTE_LATEST_PATH_FILE}'")"
if [[ -z "${REMOTE_ROOT}" ]]; then
  echo "remote suite path marker is empty: ${REMOTE_LATEST_PATH_FILE}" >&2
  exit 2
fi

echo "remote suite root: ${REMOTE_ROOT}"

for label in far minus_typed_conflict; do
  manifest="${REMOTE_ROOT}/runs/${label}/run_manifest.json"
  ssh "${REMOTE_HOST}" python3 - "${manifest}" "${label}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
label = sys.argv[2]
if not path.exists():
    raise SystemExit(f"{label}: run manifest is missing: {path}")
data = json.loads(path.read_text(encoding="utf-8"))
errors = []
if data.get("status") != "complete":
    errors.append(f"status={data.get('status')!r}")
if data.get("completed") != 60:
    errors.append(f"completed={data.get('completed')!r}")
if data.get("expected") != 60:
    errors.append(f"expected={data.get('expected')!r}")
if data.get("errors") != 0:
    errors.append(f"errors={data.get('errors')!r}")
if data.get("partial") is not False:
    errors.append(f"partial={data.get('partial')!r}")
if errors:
    raise SystemExit(f"{label}: incomplete remote run: " + ", ".join(errors))
print(
    f"{label}: complete 60/60; predictions_sha256="
    f"{data.get('predictions_sha256')}"
)
PY
done

mkdir -p "${LOCAL_ROOT}/runs" "${LOCAL_ROOT}/evaluations"
for label in far minus_typed_conflict; do
  mkdir -p "${LOCAL_ROOT}/runs/${label}"
  rsync -az \
    "${REMOTE_HOST}:${REMOTE_ROOT}/runs/${label}/" \
    "${LOCAL_ROOT}/runs/${label}/"
  uv run python -m far.experiments.validate_results \
    --run-dir "${LOCAL_ROOT}/runs/${label}" \
    --output "${LOCAL_ROOT}/${label}_validation_pre_eval.json"
done

rm -rf "${LOCAL_ROOT}/evaluations/far" "${LOCAL_ROOT}/evaluations/minus_typed_conflict"
uv run falsirag-eval \
  --benchmark bench/falsirag_bench.jsonl \
  --predictions "${LOCAL_ROOT}/runs/far/predictions.jsonl" \
  --output-dir "${LOCAL_ROOT}/evaluations/far" \
  --resamples "${RESAMPLES}" \
  --seed "${SEED}"

uv run falsirag-eval \
  --benchmark bench/falsirag_bench.jsonl \
  --predictions "${LOCAL_ROOT}/runs/minus_typed_conflict/predictions.jsonl" \
  --output-dir "${LOCAL_ROOT}/evaluations/minus_typed_conflict" \
  --baseline-scores "${LOCAL_ROOT}/evaluations/far/scores.jsonl" \
  --resamples "${RESAMPLES}" \
  --seed "${SEED}"

for label in far minus_typed_conflict; do
  uv run python -m far.experiments.validate_results \
    --run-dir "${LOCAL_ROOT}/runs/${label}" \
    --evaluation-dir "${LOCAL_ROOT}/evaluations/${label}" \
    --output "${LOCAL_ROOT}/${label}_validation.json"
done

echo "paired comparison report: ${LOCAL_ROOT}/evaluations/minus_typed_conflict/report.json"
python3 - "${LOCAL_ROOT}/evaluations/minus_typed_conflict/report.json" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(json.dumps({
    "method": report.get("method"),
    "samples": report.get("samples"),
    "publication_ready": report.get("publication_ready"),
    "aggregate": report.get("aggregate", {}).get("metrics"),
    "comparison": report.get("comparison"),
    "provenance": report.get("provenance"),
}, ensure_ascii=False, indent=2, sort_keys=True))
PY
