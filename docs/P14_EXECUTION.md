# P14 Selective-Acceptance Execution

P14 is the registered follow-up to the negative P13 confidence-threshold audit.
It uses new train rows and a reference-free, post-generation accept/reject
controller. The authoritative design is
[PREREG_SELECTIVE_ACCEPTANCE_2026-07-14.md](PREREG_SELECTIVE_ACCEPTANCE_2026-07-14.md).

## Safety contract

- Never run or download a model on the local Mac.
- Run only on `windows-gpu`, only after the read-only preflight proves that no
  other FAR/model service or GPU compute application is active.
- Use the exact clean commit tagged `prereg-selective-acceptance-v1`.
- Do not access the benchmark test split. The remote packet contains exactly
  120 train inputs and omits all references and expected actions.
- If calibration fails its registered gate, evaluation labels remain unscored.

## Local protocol checks

```bash
uv run falsirag diag selective-acceptance verify-protocol
bash -n scripts/{prepare,preflight,start,check}_windows_selective_acceptance.sh
```

## Prepare the remote without starting inference

Dry-run:

```bash
scripts/prepare_windows_selective_acceptance.sh
```

After the preregistration commit and tag are pushed:

```bash
FAR_P14_PREP_ALLOWED=1 \
  scripts/prepare_windows_selective_acceptance.sh --execute
```

The preparer fast-forwards the remote to the exact tag commit, installs two
dedicated user services, builds the label-free packet under
`/mnt/d/FAR-outputs/selective_acceptance_v1/input`, and verifies it byte for
byte. It does not start Ollama or the experiment.

## Start only when the GPU is idle

Dry-run and read-only preflight:

```bash
scripts/start_windows_selective_acceptance.sh
```

Authorized start:

```bash
FAR_P14_RUN_ALLOWED=1 \
  scripts/start_windows_selective_acceptance.sh --execute
```

The starter launches the dedicated Ollama service, verifies the exact
`qwen3.5:9b` digest, and only then starts the resumable 120-row FAR run. The
experiment service stops its dedicated Ollama service after successful exit;
on failure it retains and restarts both services so the checkpointed run can
resume without deleting evidence.

## Monitor and recover

```bash
scripts/check_windows_selective_acceptance.sh
```

The runner skips checkpointed IDs after an identity match. Do not delete or edit
the checkpoint to repair a failure. A config, source, packet, model digest, or
run-signature mismatch requires an explicit protocol amendment.

## Sync and verify the result

Copy the complete remote directory to an ignored local staging directory, then
run:

```bash
uv run falsirag diag selective-acceptance verify-packet \
  --packet-dir outputs/selective_acceptance_v1/input
uv run falsirag diag selective-acceptance finalize \
  --packet-dir outputs/selective_acceptance_v1/input \
  --run-dir outputs/selective_acceptance_v1/runs/far \
  --output-json reports/selective_acceptance.json \
  --output-markdown reports/selective_acceptance.md
uv run falsirag diag selective-acceptance verify \
  --packet-dir outputs/selective_acceptance_v1/input \
  --run-dir outputs/selective_acceptance_v1/runs/far \
  --output-json reports/selective_acceptance.json \
  --output-markdown reports/selective_acceptance.md
```

Only after independent recomputation may the registered outcome be integrated
into the paper. A null or calibration stop is a completed result and must not be
replaced by post-hoc threshold search.
