# Diagnostic artifact storage

FAR keeps executable code in the `far.*` namespace and treats generated diagnostic runs as a
separate release payload. The frozen inventory is
[`far/data/diagnostics-v1.json`](../far/data/diagnostics-v1.json): 333 files, 43,267,220 bytes,
with a whole-tree SHA-256 of
`9cc3b45e6c1696e545495414bb22970954a43e4d6cf31f9576861d12710b9548`.

## Current cutover state

- Wheels and source distributions exclude `diagnostics/` and `bench/external/`.
- The deterministic upload candidate is `artifact-dist/far-diagnostics-v1.tar.gz`: 5,557,784 bytes,
  SHA-256 `ad2b99d59de170d8bfa375e85d8f2a816a63dcafb1bf12c415a19f14af35693d`.
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
uv run falsirag ops diagnostic-data pack \
  --release-url https://github.com/xiaweiyi713/FAR/releases/download/artifacts-v1/far-diagnostics-v1.tar.gz
uv run falsirag ops diagnostic-data install --target /tmp/far-diagnostics-v1
```

`install` checks the archive fingerprint, rejects links and unsafe members, verifies every file,
and refuses to overwrite an existing target.
