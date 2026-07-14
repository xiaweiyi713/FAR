# Portable No-Human TMLR Release

This is the public delivery path for the accepted
`single_author_machine_audited_paper` profile. It is separate from the inactive
strict-human/AAAI submission path and does not consume `submission/evidence.json`,
reviewer identities, adjudication, IAA, blind custody, or publication gold.

## Build on a clean commit

```bash
bash scripts/solo_paper_release_check.sh
```

The command runs the complete model-free paper gate, rebuilds and checks the
anonymous TMLR PDF, builds wheel/sdist and the SBOM, fingerprints the nine
required artifacts, then packs the portable archive twice and requires the two
archives to be byte-identical.

The publishable outputs are ignored local artifacts:

- `build/solo-paper-release/far-solo-paper-release.tar.gz`: portable release;
- `build/solo-paper-release/verify_solo_paper_release.py`: paired,
  standard-library-only verifier whose exact bytes are also inside the archive;
- `build/solo-paper-release/bundle-build.json`: archive SHA-256, size, source
  revision, verifier SHA-256, artifact count, and frozen claim-boundary flags;
- `build/solo-paper-release/bundle-audit.json`: isolated standalone audit;
- `build/solo-paper-release/release-checksums.json`: original-path checksum
  profile used to build the archive.

## Verify after transfer

```bash
python3 -I verify_solo_paper_release.py verify \
  --archive far-solo-paper-release.tar.gz
```

Verification imports only the Python standard library and reads only the paired
verifier source plus the archive. `-I` ignores `PYTHONPATH`, the user site, and
the current checkout; no FAR installation, dependency download, network, or
model runtime is required. A Python 3.10+ interpreter is the only prerequisite.
The verifier rejects:

- a non-isolated invocation or an embedded verifier that is not byte-identical
  to the executing sidecar, including coordinated manifest rehashing;
- missing, extra, duplicate, linked, oversized, or unsafe archive members;
- byte-size or SHA-256 changes relative to both the embedded bundle manifest and
  original release-checksum manifest;
- a dirty or malformed source revision;
- a changed TMLR style commit or a source-lock/readiness hash mismatch;
- non-empty secret-scan findings or an invalid candidate benchmark/SBOM/package;
- changed P5 verdicts, changed P6-M negative-stability counts, or any upgrade to
  strict readiness, human review/adjudication/IAA, external blindness, or
  publication gold.

The archive contains exactly the nine `solo-paper` roles plus an embedded
checksum manifest, interpretation-boundary README, byte-identical standalone
verifier, and bundle manifest. It does not contain ignored model outputs, raw
credentials, strict submission evidence, or a human-review substitute.

## Publishing

Publish the `.tar.gz` together with `verify_solo_paper_release.py`,
`release-checksums.json`, and the TMLR PDF. Keep `bundle-build.json` and
`bundle-audit.json` as local build/readback records. Publishing is an external
action; generating this bundle does not itself submit the paper or upgrade its
evidence tier.

## Public release v2

The current immutable public cut is
[`paper-v2`](https://github.com/xiaweiyi713/FAR/releases/tag/paper-v2), bound to
clean Git commit `30dc37f62deeaec79d44e23876e1787bd9876174`:

- archive: 2,363,474 bytes, SHA-256
  `000499205716a93306080ac2bd7a181b5c45df454eb72b65faf70e36e5398217`;
- standalone verifier: 56,517 bytes, SHA-256
  `af26d64f233c6c70bc80bafc4e011ee9aa872b407499c63061ba41623c1d3c24`;
- release checksum manifest: 2,255 bytes, SHA-256
  `4d4c736ec4bd3bbd67fa7904f4948f419ea4b01c562a3898295f9083dbc2d593`;
- 15-page TMLR PDF: 294,328 bytes, SHA-256
  `5a77a5eb0cd8b1d2368b0ccc4ea162c7bf923922045f3f4a22a70c4fc83b4733`.

All four assets were downloaded from GitHub into an empty temporary directory.
Their sizes and hashes matched the clean local candidate, and the downloaded
sidecar passed system `python3 -I` verification with `valid=true`, no errors,
the same source revision, and all human/gold/blindness/strict-readiness flags
false. This release adds the P13 post-hoc selective-revision feasibility audit;
it does not evaluate a deployable selector or prospective policy.

## Public release v1

The first immutable public cut, retained as the P12 historical snapshot, is
[`paper-v1`](https://github.com/xiaweiyi713/FAR/releases/tag/paper-v1), bound to
clean Git commit `434414f6eec712abd13070619248f577cb4d3e0a`:

- archive: 2,328,609 bytes, SHA-256
  `7e94e1e7ed63f0d4945d90164db418eb87e816fd284bb972373ca46cb1d852e8`;
- standalone verifier: 51,501 bytes, SHA-256
  `77fa692e1279e64050a7107c57f545a40bf8faac9ea2617ff0e036b65cc115da`;
- build record SHA-256
  `adba3ad599f67424a466bddb3f08b56a0acac29793e24776452c57437b212b69`;
- isolated audit SHA-256
  `982c7a43bd7ccd461c9745b6d6e936d539333b2aba89c23cc6026b1cf2bd20b5`.

After publication, all four assets were downloaded from GitHub into an empty
temporary directory. Their sizes and hashes matched the local candidate, and
the downloaded sidecar passed `python3 -I` verification with `valid=true`, no
errors, and the same source revision and non-human boundary flags.
