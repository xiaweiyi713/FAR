# Diagnostic artifact storage

FAR keeps executable code in the `far.*` namespace and treats generated diagnostic runs as a
separate release payload. The frozen inventory is
[`far/data/diagnostics-v1.json`](../far/data/diagnostics-v1.json): 336 files, 43,883,739 bytes,
with a whole-tree SHA-256 of
`8f620af737f3b04f5b3813b06c7183743a3ae14f7c8fd869f43a83b9a821dbff`.

## Current cutover state

- Wheels and source distributions exclude `diagnostics/` and `bench/external/`.
- The published deterministic archive is `far-diagnostics-v1.tar.gz`: 5,639,635 bytes,
  SHA-256 `5e3f28dcd81d2af3170f740611b9f59b8bbe1ee6e869379d5794730db4ecf96e`.
- The archive is published at the immutable
  [`artifacts-v1` release](https://github.com/xiaweiyi713/FAR/releases/tag/artifacts-v1),
  and the manifest records `published: true` plus the exact asset URL.
- The release asset was downloaded independently, installed into an empty directory, and matched
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
  --release-url https://github.com/xiaweiyi713/FAR/releases/download/artifacts-v1/far-diagnostics-v1.tar.gz
```

`install` checks the archive fingerprint, rejects links and unsafe members, verifies every file,
and refuses to overwrite an existing target.

The installer is the release gate: it downloads through the manifest URL, checks the archive
fingerprint, rejects links/unsafe members, recomputes the complete inventory, and only then moves
the verified tree into place. Future accepted P6 human results require a new versioned artifact;
they must not mutate the immutable `artifacts-v1` release.
