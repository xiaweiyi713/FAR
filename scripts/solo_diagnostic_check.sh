#!/usr/bin/env bash
# Verify the public single-author diagnostic path without requiring human labels,
# cloud credentials, ignored outputs, or external custody.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

uv run falsirag-solo-release verify diagnostics/solo_v1
uv run falsirag-eval-fever-binary verify \
  --data-dir bench/external/fever_pair_candidates_v1 \
  diagnostics/fever_binary_v1
uv run falsirag-project-status --verify
uv run falsirag-solo-paper-readiness > /dev/null

uv run pytest -q \
  tests/test_diagnostic_release.py \
  tests/test_fever_binary_evaluation.py \
  tests/test_diagnostic_report.py \
  tests/test_project_status.py \
  tests/test_solo_paper_readiness.py \
  tests/test_release_checksums.py::test_source_archive_includes_reader_facing_reports

echo "FAR single-author diagnostic checks passed."
