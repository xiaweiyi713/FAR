# Diagnostic artifact storage

FAR keeps executable code in the `far.*` namespace and treats generated diagnostic runs as a
separate release payload. The frozen inventory is
[`far/data/diagnostics-v1.json`](../far/data/diagnostics-v1.json): 336 files, 43,883,739 bytes,
with a whole-tree SHA-256 of
`8f620af737f3b04f5b3813b06c7183743a3ae14f7c8fd869f43a83b9a821dbff`.

## Current cutover state

- Wheels and source distributions exclude `diagnostics/` and `bench/external/`.
- The deterministic upload candidate is `artifact-dist/far-diagnostics-v1.tar.gz`: 5,639,635 bytes,
  SHA-256 `5e3f28dcd81d2af3170f740611b9f59b8bbe1ee6e869379d5794730db4ecf96e`.
- The archive has **not** been published. Its manifest therefore has `published: false` and no
  release URL.
- Until a release upload succeeds and is downloaded back through the verifier, `diagnostics/`
  remains tracked. This avoids deleting the only available copy or advertising a broken URL.

This is a two-phase migration. Phase A (implemented here) separates installable code from large
research payloads and freezes a reproducible release. Phase B requires an authorized external
upload; only then may a follow-up commit remove `diagnostics/` from the main tree. Existing blobs
remain in old Git history unless maintainers separately approve a history rewrite or LFS migration.

## Commands

Rebuild the deterministic archive and manifest:

```bash
uv run falsirag ops diagnostic-data pack
```

Verify the checked-out payload:

```bash
uv run falsirag ops diagnostic-data verify
```

After uploading the exact archive, rebuild the manifest with the immutable release URL and verify
installation into an empty directory:

```bash
gh release create artifacts-v1 artifact-dist/far-diagnostics-v1.tar.gz \
  --repo xiaweiyi713/FAR \
  --title "FAR diagnostic artifacts v1" \
  --notes "Frozen P0-P6 diagnostic payload; verify against far/data/diagnostics-v1.json."
uv run falsirag ops diagnostic-data pack \
  --release-url https://github.com/xiaweiyi713/FAR/releases/download/artifacts-v1/far-diagnostics-v1.tar.gz
uv run falsirag ops diagnostic-data install --target /tmp/far-diagnostics-v1
```

`install` checks the archive fingerprint, rejects links and unsafe members, verifies every file,
and refuses to overwrite an existing target.

The upload is an external repository mutation and is not performed by the normal build or test
suite. A maintainer must authorize it explicitly. After the commands above succeed, compare
`/tmp/far-diagnostics-v1` with the checked-out `diagnostics/`, commit the manifest containing the
immutable URL, then remove `diagnostics/` in the same reviewed cutover. Do not delete local data
merely because `gh release create` returned success; the independent download/install verifier is
the release gate.
