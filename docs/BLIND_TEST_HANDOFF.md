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

1. `outputs/handoff/falsirag_blind_test_v1/`
2. the frozen repository commit or release archive;
3. the exact config file, e.g. `experiments/configs/deepseek.yaml`;
4. environment instructions from `docs/REPRODUCING.md`;
5. a short run sheet listing model credentials supplied through environment
   variables only.

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

Only after the return package is frozen, score it against the adjudicated
benchmark:

```bash
uv run falsirag-eval \
  --data-dir outputs/annotations/falsirag_adjudicated_v1 \
  --predictions /path/to/returned/deepseek_test_far/runs/far/predictions.jsonl \
  --output-dir outputs/evaluations/deepseek_test_far \
  --split test \
  --allow-test
```

Run the preregistered baseline first and pass its `scores.jsonl` as
`--baseline-scores` for paired McNemar/bootstrap reports.

## Acceptance checks

Before using test numbers in the paper:

- returned manifests match the frozen commit, config, corpus hash, and blind
  input hash;
- every selected method has complete predictions for the test split;
- no returned manifest reports `gold_loaded=true`;
- no run was repeated because of an unfavorable score;
- result validation passes;
- paper tables and figures are regenerated only from validated scored reports.

If any check fails, report the failure and do not replace
`PENDING-EMPIRICAL-RUN` cells with those numbers.
