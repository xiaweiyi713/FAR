# Diagnostic artifact storage

FAR keeps executable code in the `far.*` namespace and treats generated diagnostic runs as a
separate release payload. The frozen inventory is
[`far/data/diagnostics-v2.json`](../far/data/diagnostics-v2.json): 336 files, 44,128,752 bytes,
with a whole-tree SHA-256 of
`362761dc85faf14d5a3b9e7f397c40e39383a8475ec0502efcbb904d973e92ae`.

## Current cutover state

- Wheels and source distributions exclude `diagnostics/` and `bench/external/`.
- The current deterministic archive is `far-diagnostics-v2.tar.gz`: 5,636,721 bytes,
  SHA-256 `016988b09b856e94025e2d50312ebb79d13a48e73155c3ca96cd611acb24b383`.
- The archive is published at the immutable
  [`artifacts-v2` release](https://github.com/xiaweiyi713/FAR/releases/tag/artifacts-v2),
  and the packaged v2 manifest records `published: true` plus the exact asset URL.
- The original [`artifacts-v1`](https://github.com/xiaweiyi713/FAR/releases/tag/artifacts-v1)
  asset remains unchanged as the P10-B source snapshot. V2 adds the P11
  revision-delta metric profile and refreshed `solo_v1` reports without rewriting v1.
- The v2 release asset was downloaded independently, installed into an empty directory, and matched
  against all 336 checked-out source files before the tracked tree was removed.
- `diagnostics/` is now an ignored local install target. A fresh checkout retrieves it with
  `falsirag ops diagnostic-data install`; CI performs the same verified installation before tests.

The two-phase migration is complete. Phase A separated installable code from research payloads;
Phase B published, independently read back, and removed the tracked current-tree copy. Existing
blobs remain in old Git history because no history rewrite or LFS migration was authorized.

## Commands

Verify or install the published release:

```bash
uv run falsirag ops diagnostic-data verify
uv run falsirag ops diagnostic-data install
```

Maintainer-only reproduction of the published archive from an already installed tree:

```bash
uv run falsirag ops diagnostic-data pack \
  --release-url https://github.com/xiaweiyi713/FAR/releases/download/artifacts-v2/far-diagnostics-v2.tar.gz
```

`install` checks the archive fingerprint, rejects links and unsafe members, verifies every file,
and refuses to overwrite an existing target.

The installer is the release gate: it downloads through the manifest URL, checks the archive
fingerprint, rejects links/unsafe members, recomputes the complete inventory, and only then moves
the verified tree into place. Future evidence changes require a new versioned artifact; they must
not mutate either immutable `artifacts-v1` or `artifacts-v2` release.
