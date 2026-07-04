# External Blind Test Handoff

The final test gate must be run by an external custodian from a gold-free
bundle. Local technical isolation is implemented, but it is not a genuine blind
test unless the custodian receives no gold labels and runs the frozen code and
configs once.

## Roles

- **Project owner:** freezes the code commit, configs, adjudicated benchmark,
  and release artifact; builds the gold-free handoff bundle.
- **External custodian:** receives the handoff bundle, environment instructions,
  and frozen config; runs predictions once; returns only unscored prediction
  bundles and manifests.
- **Trusted scorer:** evaluates returned predictions against the frozen
  adjudicated benchmark after the custodian run is complete.

The same person should not serve as both custodian and scorer.

## Prerequisites

Do not hand off test execution until:

1. human annotation and adjudication are complete;
2. `annotation_report.json` passes the kappa gate;
3. dev results and ablation claims are frozen;
4. cloud credentials or local model assets for the test run are ready;
5. the release check passes on the frozen commit.

If any prerequisite is missing, run only dev diagnostics.

## Build the gold-free bundle

From the frozen repository:

```bash
uv run falsirag-build-blind-bundle \
  --data-dir outputs/annotations/falsirag_adjudicated_v1 \
  --output-dir outputs/handoff/falsirag_blind_test_v1
```

The output contains sanitized corpus records, five-field test inputs, and a
manifest. It excludes:

- gold labels;
- expected revisions;
- counter-evidence roles;
- dependency groups;
- construction metadata;
- train/dev scored rows.

The builder refuses to write into a non-empty output directory. Keep that
behavior: stale files in a handoff bundle are a blindness risk.

Before transferring files, audit and package the bundle for the custodian:

```bash
uv run falsirag-build-blind-bundle audit \
  --bundle-dir outputs/handoff/falsirag_blind_test_v1

uv run falsirag-build-blind-bundle package \
  --bundle-dir outputs/handoff/falsirag_blind_test_v1 \
  --output-dir outputs/handoff/custodian_deepseek_handoff \
  --config experiments/configs/deepseek.yaml \
  --frozen-commit "$(git rev-parse HEAD)" \
  --overwrite
```

The package command creates a deterministic ZIP and a
`custodian_handoff_manifest.json`. It includes only:

- `blind_bundle/blind_bundle_manifest.json`;
- `blind_bundle/corpus.jsonl`;
- `blind_bundle/splits/test_inputs.jsonl`;
- the explicitly selected config file(s);
- `CUSTODIAN_RUN_SHEET.md`; and
- the handoff manifest.

It rejects forbidden gold/provenance keys, extra files in the blind bundle,
fingerprint mismatches, and directories whose name contains `technical` unless
`--allow-technical` is explicitly supplied for a non-final dry run.

### Technical dry-run bundle

A full technical dry run was built on 2026-06-30 from the current
machine-seeded benchmark at
`outputs/handoff/falsirag_blind_test_technical_v1/`. It is deliberately ignored
by Git and is **not** the final custodian package: the source benchmark is still
`publication_ready: false`, and no independent human adjudication has occurred.
The dry run proves only that the handoff path can produce and audit a complete
gold-free package before the external gate.

The audited bundle contains exactly 58 unique test inputs and 175 sanitized
corpus documents. Every test row has exactly `id`, `category`, `split`,
`question`, and `initial_answer`; every split value is `test`. Recursive key
inspection found none of the gold, expected-revision, counter-evidence-role,
dependency-group, construction-metadata, conflict-label, or revision-label
fields. Its frozen fingerprints are:

- manifest: `70f6c28c4809d82822fc75596061d07284edf94ef24af6790836571fe24f7c86`;
- sanitized corpus: `97fb3ecff5e76fc521434182204479179b7c02422864850b60867c6d91838e12`;
- test inputs: `1ce8ed27a4db9c1793d9d9342418b82826c5e31d9b5ae754e012fb1f12454016`;
  and
- source corpus: `cca5f62db0fbb51e1bae8111ea85fe169fba7be5a8e63847a9c1c048cdae25cd`.

After adjudication, build a new empty `falsirag_blind_test_v1` directory from
the frozen adjudicated data and repeat the same structural and fingerprint
audit. Do not rename or hand off the technical dry-run directory.

## Handoff package contents

Send the custodian:

1. the `custodian_*_handoff.zip` package and its SHA-256 manifest;
2. the frozen repository commit or release archive;
3. environment instructions from `docs/REPRODUCING.md`;
4. model credentials supplied through environment variables only.

Do not send:

- `bench/falsirag_bench.jsonl`;
- `outputs/annotations/falsirag_adjudicated_v1/falsirag_bench.jsonl`;
- local dev/test evaluation reports;
- prompt-tuning notes derived from test labels.

## Custodian command

For a full FAR test prediction run:

```bash
falsirag-suite \
  --config experiments/configs/deepseek.yaml \
  --data-dir /path/to/falsirag_blind_test_v1 \
  --output-dir /path/to/returned/deepseek_test_far \
  --split test \
  --allow-test \
  --ablation full
```

For baselines or ablations, use the same frozen config and the preregistered
suite options. The custodian should not inspect local gold labels or run
multiple prompt/code variants after seeing outputs.

In blind mode the suite must emit a `far-blind-suite-manifest-v1` manifest with:

- `gold_loaded: false`;
- `unscored: true`;
- input/corpus fingerprints;
- prediction fingerprints.

It must not emit scored reports or paper figures.

## Return package

The custodian returns:

- prediction JSONL files;
- run manifests;
- blind-suite manifest;
- logs needed for reproducibility;
- a note naming the command, model endpoint, date, and whether any restart or
  resume occurred.

The custodian should not return any edited benchmark file.

## Trusted scoring

Only after all return packages and the role-separated one-shot attestation are
frozen, score each complete suite against the adjudicated benchmark. Copy
`submission/blind_test_attestation.template.json` to the ignored real path
`submission/blind_test_attestation.json` before filling it; the scorer rejects
the tracked `.template.json` path.

```bash
uv run falsirag-score-blind-return \
  --model-id deepseek_v4_flash \
  --data-dir outputs/annotations/falsirag_adjudicated_v1 \
  --blind-bundle-dir outputs/handoff/falsirag_blind_test_v1 \
  --return-dir outputs/returned/deepseek_test_suite \
  --attestation submission/blind_test_attestation.json \
  --output-dir outputs/final/deepseek_test_scored
```

The scorer validates and evaluates Vanilla first, compares FAR and the other
baselines against Vanilla, compares each ablation against FAR, and emits the
paired McNemar/bootstrap reports plus tables and figures in one bound bundle.

## Acceptance checks

Before using test numbers in the paper:

- returned manifests match the frozen commit, config, corpus hash, and blind
  input hash;
- every selected method has complete predictions for the test split;
- no returned manifest reports `gold_loaded=true`;
- no run was repeated because of an unfavorable score;
- result validation passes;
- paper tables and figures are regenerated only from validated scored reports.

If any check fails, report the failure and do not use those numbers in a strict
blind-test table. The relaxed machine-audited paper has a separate, explicitly
development-only table governed by `falsirag-solo-paper-readiness`.
