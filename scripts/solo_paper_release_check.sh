#!/usr/bin/env bash
# Build and fingerprint the accepted no-human TMLR paper release. This path is
# independent of the inactive strict-human/AAAI submission profile.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

git diff --check
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  echo "solo paper release checks require a clean Git worktree" >&2
  git status --short >&2
  exit 2
fi

release_dir="build/solo-paper-release"
mkdir -p "${release_dir}"

bash -n scripts/*.sh
uv run ruff format --check .
uv run ruff check .
uv run mypy far tests scripts/package_smoke.py
uv run pytest -q
bash scripts/solo_diagnostic_check.sh
uv run falsirag bench validate \
  --output "${release_dir}/benchmark-validation.json"
uv run falsirag release scan-secrets --json > "${release_dir}/secret-scan.json"
uv run falsirag release sbom \
  --output build/sbom/far-sbom.cdx.json --check --json
uv build
bash scripts/check_release_packages.sh
bash scripts/build_tmlr_paper.sh

uv run falsirag release checksums \
  --profile solo-paper \
  --sbom build/sbom/far-sbom.cdx.json \
  --artifact benchmark_validation_report="${release_dir}/benchmark-validation.json" \
  --artifact secret_scan_report="${release_dir}/secret-scan.json" \
  --artifact solo_paper_readiness_json=reports/solo_paper_readiness.json \
  --artifact solo_paper_readiness_markdown=reports/solo_paper_readiness.md \
  --artifact tmlr_paper_pdf=paper/build/tmlr/tmlr.pdf \
  --artifact tmlr_source_lock=paper/build/tmlr/SOURCE.lock \
  --output "${release_dir}/release-checksums.json" --check --json

bundle_archive="${release_dir}/far-solo-paper-release.tar.gz"
repro_archive="${release_dir}/far-solo-paper-release.repro.tar.gz"
uv run falsirag release solo-paper-bundle pack \
  --checksum-manifest "${release_dir}/release-checksums.json" \
  --archive "${bundle_archive}" > "${release_dir}/bundle-build.json"
uv run falsirag release solo-paper-bundle pack \
  --checksum-manifest "${release_dir}/release-checksums.json" \
  --archive "${repro_archive}" > /dev/null
if ! cmp -s "${bundle_archive}" "${repro_archive}"; then
  echo "solo-paper portable archive is not deterministic" >&2
  exit 1
fi
rm -f -- "${repro_archive}"
uv run falsirag release solo-paper-bundle verify \
  --archive "${bundle_archive}" > "${release_dir}/bundle-audit.json"

echo "FAR solo TMLR paper release checks passed."
