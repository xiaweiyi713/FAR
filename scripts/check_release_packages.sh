#!/usr/bin/env bash
# Install the built wheel and sdist independently and validate packaged data/CLIs.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

shopt -s nullglob
wheels=(dist/*.whl)
sdists=(dist/*.tar.gz)
if [[ ${#wheels[@]} -ne 1 || ${#sdists[@]} -ne 1 ]]; then
  echo "expected exactly one wheel and one sdist under dist/" >&2
  exit 2
fi

smoke_root="$(mktemp -d "${TMPDIR:-/tmp}/far-package-smoke.XXXXXX")"
trap 'rm -rf "${smoke_root}"' EXIT

for artifact in "${wheels[0]}" "${sdists[0]}"; do
  artifact="$(cd "$(dirname "${artifact}")" && pwd)/$(basename "${artifact}")"
  (
    cd "${smoke_root}"
    uv run --isolated --with "${artifact}" \
      python -I "${ROOT}/scripts/package_smoke.py"
  )
done

echo "FAR wheel and sdist smoke checks passed."
