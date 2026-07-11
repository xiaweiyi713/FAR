# P6 type-mappability execution and human handoff

P6 is a retrospective mechanism analysis over 217 public development items. It
cannot confirm H4 because the underlying WS3 results predate H4 registration.
The frozen semantics and claim limits remain authoritative in
[`PREREG_TYPE_MAPPABILITY_2026-07-10.md`](PREREG_TYPE_MAPPABILITY_2026-07-10.md).

## Execution placement

Machine prelabels run only on the existing `windows-gpu` host. The developer
Mac must not install or run Ollama for P6. Local commands prepare code, install
returned artifacts, check fingerprints, and support the human workflow without
model calls.

Remote operations are default-deny:

- preparation requires `--execute` plus `FAR_P6_PREP_ALLOWED=1`;
- model start requires `--execute` plus `FAR_P6_PRELABEL_ALLOWED=1`;
- artifact return and tracked-packet installation require `--execute` plus
  `FAR_P6_FETCH_ALLOWED=1`.

The starter never pulls a model. It fails unless remote `qwen3.5:9b` resolves
to digest
`6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`.

## Remote machine prelabels

After the reviewed source commit exists exactly on `origin/main`, inspect and
then prepare the remote worktree, dedicated systemd units, and an external
blank packet:

```bash
scripts/prepare_windows_p6_prelabels.sh
FAR_P6_PREP_ALLOWED=1 scripts/prepare_windows_p6_prelabels.sh --execute
```

Inspect the offline gate, then start only inside an authorized GPU window:

```bash
scripts/start_windows_p6_prelabels.sh
FAR_P6_PRELABEL_ALLOWED=1 scripts/start_windows_p6_prelabels.sh --execute
scripts/check_windows_p6_prelabels.sh
```

Every completed response is appended to an external D:-backed checkpoint. The
final bundle binds the immutable model digest, configuration and prompt-template
fingerprints, per-item prompt hash, raw response hash, and parsed annotation.

Stopping never removes checkpoints:

```bash
scripts/stop_windows_p6_prelabels.sh
scripts/stop_windows_p6_prelabels.sh --execute --stop-ollama
```

## Zero-model return and installation

After all 217 remote rows complete, fetch and install them into the committed
blank packet:

```bash
scripts/fetch_windows_p6_prelabels.sh
FAR_P6_FETCH_ALLOWED=1 scripts/fetch_windows_p6_prelabels.sh --execute
```

The installer independently checks all contexts and annotations. When the
source carries native raw responses, it additionally requires the raw response
to parse to the installed annotation and verifies both response and prompt
fingerprints before preserving them. No local model call occurs.

Installing new diagnostic files changes the diagnostic tree. Before any P10-B
release, rebuild and verify the artifact manifest/archive rather than claiming
the earlier 333-file archive contains P6 prelabels.

## Human-only remainder

Machine prelabels are hidden from reviewers and are not gold. Two distinct
people must independently complete all 217 rows using the reviewer templates;
only after both files are frozen may a third distinct adjudicator see their
labels and the machine prelabels. Use the packet commands printed in
`diagnostics/type_mappability_v1/INSTRUCTIONS.md` to install each completed
file, then run:

```bash
uv run falsirag diag type-mappability status \
  --packet-dir diagnostics/type_mappability_v1
uv run falsirag diag type-mappability analyze \
  --packet-dir diagnostics/type_mappability_v1 \
  --output-dir reports/type_mappability
uv run falsirag diag type-mappability verify \
  --packet-dir diagnostics/type_mappability_v1 \
  --report-dir reports/type_mappability
```

Even after successful adjudication, report the result as retrospective,
`confirmatory_h4:false`, `publication_gold:false`, and
`human_identity_verified:false`.
