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
`bundle-build.json`, and `bundle-audit.json`. The build record provides both
SHA-256 values that a recipient can check before running the semantic verifier.
Publishing is an external action; generating this bundle does not itself submit
the paper or upgrade its evidence tier.
