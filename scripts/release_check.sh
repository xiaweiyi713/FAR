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

bash -n scripts/*.sh
bash scripts/check_cloud_run_readiness.sh
uv run ruff format --check .
uv run ruff check .
uv run mypy far bench baselines eval experiments tests
uv run pytest -q
uv run falsirag-validate-bench --output build/release/benchmark-validation.json
uv run falsirag-scan-secrets --json > build/release/secret-scan.json
uv run falsirag-generate-sbom \
  --output build/sbom/far-sbom.cdx.json --check --json
uv build
uv run falsirag-release-checksums \
  --sbom build/sbom/far-sbom.cdx.json \
  --output build/release-checksums.json --check --json
uv run falsirag-submission-readiness \
  --evidence submission/evidence.template.json \
  --output build/release/submission-readiness-current.json \
  --allow-incomplete > /dev/null

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

echo "FAR release checks passed."
