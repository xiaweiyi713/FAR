# P6-M execution handoff

P6-M is the machine-only ontology-stability audit registered in
`PREREG_TYPE_MAPPABILITY_MACHINE_2026-07-13.md`. Its verified negative result
closes the accepted no-human redirection profile. It does not complete the
separate frozen strict-human P6 and cannot report human IAA or human gold.

## Local boundary

The Mac may prepare code, inspect status, fetch returned JSONL, analyze, and verify.
It must not install, download, or run any model. The existing Qwen P6 prelabels are
not an input to the P6-M jurors or consensus.

## Remote prerequisites

- The authorized `windows-gpu` worktree is clean and exactly matches `origin/main`.
- The existing P6 packet is present at `/mnt/d/FAR-outputs/type_mappability_v1`.
- `mistral:7b-instruct`, `glm4:9b`, and `llama3.1:8b` are already installed in the D-backed Ollama store.
  The runner refuses missing models; it never pulls them.
- Ollama is reachable on `127.0.0.1:11434` for J1/J2/J3.

## Run the three jurors

Run each role from the remote WSL shell. All three check GPU utilization every 60
seconds and wait while another task is using the GPU. They run sequentially; do not
start multiple roles together.

```bash
cd /mnt/d/FAR-workspace/FAR-longterm
FAR_P6M_ALLOWED=1 scripts/run_windows_p6m_juror.sh J1
FAR_P6M_ALLOWED=1 scripts/run_windows_p6m_juror.sh J2
FAR_P6M_ALLOWED=1 scripts/run_windows_p6m_juror.sh J3
```

Each role writes 217×2 rows under `/mnt/d/FAR-outputs/p6m/J*`. `--resume` is
always used, so an interrupted role continues only when its run identity, commit,
model, prompt, config, and source packet still match.

Every invalid structured response is fsynced to `failed_attempts.jsonl` before a
retry. Fenced or surrounding prose may be removed only to extract the first JSON
object; the extracted object must still pass the exact frozen four-field schema.

## Fetch, analyze, and verify without models

Dry-run first:

```bash
scripts/fetch_windows_p6m.sh --dry-run
```

After all three remote manifests say `complete=true`:

```bash
FAR_P6M_FETCH_ALLOWED=1 scripts/fetch_windows_p6m.sh --execute
```

The fetcher rejects incomplete or human-mislabeled artifacts, copies all raw
attempt provenance into `outputs/p6m_remote/`, builds
`reports/type_mappability_machine/`, copies the three minimal juror inputs into
the tracked `reports/type_mappability_machine/jurors/` evidence tree, and performs
deterministic recomputation from that tracked copy. A fresh clone with the
published diagnostic packet can therefore rerun the verifier without access to
the remote host. The original P6 packet remains `ready_to_analyze=false`; its
human branch is inactive unless real humans become available and strict claims
are reopened. P6-M does not write its reviewer/adjudicator slots.

## Completed formal run (2026-07-13)

The authorized remote run completed all three jurors with 434/434 rows and zero
failed attempts. Transport normalization removed only identical mapped-type
duplicates in 25 J1 responses and 2 J2 responses; J3 required none. The remote
P6-M and Ollama services both stopped after J3.

The returned bundle passed raw-response reparse, model/run identity, prompt,
context, annotation and file-fingerprint checks. Deterministic report verification
returned `valid=true`, `errors=[]`. The result was a negative stability audit:

- J1/J2/J3 dual-view stability: `50/217`, `88/217`, `24/217`;
- dispositions: 1 unanimous, 14 majority, 202 contested;
- machine consensus coverage: `15/217 = 0.0691`;
- view A/B mappability Fleiss kappa: `0.1666` / `-0.0408`;
- one frozen stratum had zero consensus, so the six-point association was not
  estimable.

These values describe model-panel sensitivity, not population mappability. The
15 consensus rows are a selected subset and their mappability/delta summaries
must not be extrapolated to all 217 samples. The original human P6 remains
`ready_to_analyze=false` and inactive. This is the terminal outcome of the
accepted no-human profile; no additional model panel is queued as a substitute.

Reproduce the final check from tracked evidence after installing the diagnostic
packet:

```bash
uv run --locked falsirag diag type-mappability-machine verify \
  --packet-dir diagnostics/type_mappability_v1 \
  --juror-dir reports/type_mappability_machine/jurors/J1 \
  --juror-dir reports/type_mappability_machine/jurors/J2 \
  --juror-dir reports/type_mappability_machine/jurors/J3 \
  --report-dir reports/type_mappability_machine
```
