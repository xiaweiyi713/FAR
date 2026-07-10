#!/usr/bin/env bash
# Run every repository-controlled submission/release gate in one fail-closed command.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

git diff --check
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  echo "release checks require a clean Git worktree" >&2
  git status --short >&2
  exit 2
fi

mkdir -p build/release
EVIDENCE_PATH="${FAR_SUBMISSION_EVIDENCE:-submission/evidence.template.json}"

bash -n scripts/*.sh
bash scripts/check_cloud_run_readiness.sh
uv run ruff format --check .
uv run ruff check .
uv run mypy far tests scripts/package_smoke.py
uv run pytest -q
bash scripts/solo_diagnostic_check.sh
uv run falsirag-validate-bench --output build/release/benchmark-validation.json
uv run falsirag-scan-secrets --json > build/release/secret-scan.json
uv run falsirag-generate-sbom \
  --output build/sbom/far-sbom.cdx.json --check --json
uv build
bash scripts/check_release_packages.sh

(
  cd paper
  mkdir -p build/release
  latexmk -pdf -interaction=nonstopmode -halt-on-error \
    -output-directory=build/release main.tex
  latexmk -pdf -interaction=nonstopmode -halt-on-error \
    -output-directory=build/release supplement.tex
  latexmk -pdf -interaction=nonstopmode -halt-on-error \
    -output-directory=build/release aaai27/ReproducibilityChecklist.tex
)

uv run falsirag-release-checksums \
  --sbom build/sbom/far-sbom.cdx.json \
  --artifact benchmark_validation_report=build/release/benchmark-validation.json \
  --artifact secret_scan_report=build/release/secret-scan.json \
  --artifact submission_evidence_snapshot="${EVIDENCE_PATH}" \
  --artifact paper_main_pdf=paper/build/release/main.pdf \
  --artifact paper_supplement_pdf=paper/build/release/supplement.pdf \
  --artifact aaai_reproducibility_checklist_pdf=paper/build/release/ReproducibilityChecklist.pdf \
  --output build/release-checksums.json --check --json

if [[ "${EVIDENCE_PATH}" == *.template.json ]]; then
  uv run falsirag-submission-readiness \
    --evidence "${EVIDENCE_PATH}" \
    --output build/release/submission-readiness-current.json \
    --allow-incomplete > /dev/null
else
  uv run falsirag-submission-readiness \
    --evidence "${EVIDENCE_PATH}" \
    --output build/release/submission-readiness-current.json > /dev/null
fi

echo "FAR release checks passed."
