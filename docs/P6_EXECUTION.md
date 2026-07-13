# P6 type-mappability execution and human handoff

P6 is a retrospective mechanism analysis over 217 public development items. It
cannot confirm H4 because the underlying WS3 results predate H4 registration.
The frozen semantics and claim limits remain authoritative in
[`PREREG_TYPE_MAPPABILITY_2026-07-10.md`](PREREG_TYPE_MAPPABILITY_2026-07-10.md).

Status decision (2026-07-13): real reviewers and an adjudicator could not be
sourced, so this strict-human branch is inactive and outside the accepted
no-human redirection profile. The instructions below are retained only as a
future protocol. They have no current owner or deadline and reopen only if real
people become available and strict human-mappability claims are explicitly
requested.

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
Schema-invalid responses receive at most three attempts. Each attempt is
fsync'd to a separate fingerprinted audit log before the runner continues, and
Ollama receives the frozen conditional annotation schema through its structured
output field.

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

The authorized run at source commit `949bb1353d12d97d9541bae310c5b3c57b9e5901`
completed on 2026-07-12. It installed 217/217 rows from 221 total attempts; four
schema/JSON failures were corrected within the bounded retry gate. The frozen
machine-prelabel SHA-256 is
`59f930d5ef0311fed8c9e4f65fe72f85dc6e68516975eea89015e6896a340e2f`,
the identity SHA-256 is
`d309b88de917ae892c79c6c1e6b64455998721ac9eeabcbe8d5d934f6695ae24`,
and the remote attempt-log SHA-256 is
`2fd371e1f5f2e57f72e669681498dff0bf791629f9516f52f6e9a377d2da8b38`.
The remote runner exited successfully, Ollama was stopped, and the local
zero-model installer independently accepted all rows and attempt chains.

The returned machine packet is part of the immutable
[`artifacts-v1`](https://github.com/xiaweiyi713/FAR/releases/tag/artifacts-v1)
release: 336 files with tree SHA-256
`8f620af737f3b04f5b3813b06c7183743a3ae14f7c8fd869f43a83b9a821dbff`.
In a fresh checkout, install that packet before coordinating human work:

```bash
uv run --locked falsirag ops diagnostic-data install
uv run --locked falsirag ops diagnostic-data verify
```

`diagnostics/` is now an ignored local install target, not a Git-tracked
directory. The preservation steps below are therefore mandatory for future
human returns.

## Optional future human-only branch (inactive)

This section is not a current work queue. If the branch is explicitly reopened,
machine prelabels remain hidden from reviewers and are not gold. Two distinct
people must independently complete all 217 rows. Because the tracked packet now
contains machine prelabels, never distribute the repository or packet directory
itself. Generate the two role-isolated, deterministic ZIPs instead:

```bash
falsirag diag type-mappability export-reviewer \
  --packet-dir diagnostics/type_mappability_v1 \
  --role reviewer_a --output-dir outputs/p6-reviewer-a
falsirag diag type-mappability export-reviewer \
  --packet-dir diagnostics/type_mappability_v1 \
  --role reviewer_b --output-dir outputs/p6-reviewer-b
```

Each archive has an exact five-file allowlist: `items.jsonl`, one blank role
template, reviewer instructions, a self-contained `REVIEWER_FORM.html`, and a
fingerprint manifest. The form has no external dependencies or network calls;
it embeds only the same visible items and blank role template, validates the
frozen schema, saves a browser-local draft when available, imports/exports
JSONL backups, and keeps the completed export disabled until all 217 rows are
valid. The archive excludes the analysis index, scores, machine labels, the
peer template, completed files, and the source packet manifest. The
deterministic archives generated from
`artifacts-v1` and checked on 2026-07-12 are:

| Role | Local handoff | SHA-256 |
|---|---|---|
| reviewer A | `outputs/p6-reviewer-a.zip` | `90e720a3f55c83e792abc09322051eafcd596f9c1bc61c918b159355d539da94` |
| reviewer B | `outputs/p6-reviewer-b.zip` | `28d940a3e0aa75f464521823b0014f677052be4c1fb2c2ea880aacaf29bbf382` |

Verify each ZIP immediately before sending it. Give each archive to a distinct
person and never send both archives to the same reviewer. Return only the
completed role JSONL files, retain the original returned bytes outside the
repository, and install them with distinct non-empty self-attested IDs:

The reviewer should unzip their one archive and open `REVIEWER_FORM.html` in a
modern browser. They should export draft JSONL backups regularly and return
only the enabled completed JSONL export. Directly editing the included blank
role template remains supported, but the offline form is the lower-error path.

```bash
shasum -a 256 outputs/p6-reviewer-a.zip outputs/p6-reviewer-b.zip
uv run --locked falsirag diag type-mappability install \
  --packet-dir diagnostics/type_mappability_v1 \
  --role reviewer_a --annotator-id <id-a> --input <completed-a.jsonl>
uv run --locked falsirag diag type-mappability install \
  --packet-dir diagnostics/type_mappability_v1 \
  --role reviewer_b --annotator-id <id-b> --input <completed-b.jsonl>
```

Only after both reviewer files are frozen may the third distinct adjudicator
see their labels and the sanitized machine annotations:

```bash
falsirag diag type-mappability export-adjudicator \
  --packet-dir diagnostics/type_mappability_v1 \
  --output-dir outputs/p6-adjudicator
```

The deterministic adjudicator archive is generated only after the two real
reviewer files are frozen. It has an exact five-file allowlist: visible
`items.jsonl`, the frozen dual-review/sanitized-machine worksheet,
`ADJUDICATOR_INSTRUCTIONS.md`, a self-contained
`ADJUDICATOR_FORM.html`, and its fingerprint manifest. The form binds local
drafts and imports to the exact reviewer-file fingerprints, rejects changes to
context/reviewer/machine inputs, labels the machine suggestion as non-gold, and
enables completed export only after all 217 gold annotations are valid.

The adjudicator packet excludes machine raw responses, analysis strata, and
scores. The adjudicator fills `gold_annotation`; the installer normalizes it to
the frozen installed annotation schema. The third person should unzip the
archive, open `ADJUDICATOR_FORM.html`, export draft backups regularly, and
return only the completed `adjudicator.jsonl`. Use the packet commands printed in
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

## Preserve completed human evidence after P10-B

Reviewer and adjudicator installs modify only the ignored local diagnostic
tree. After every accepted return, keep the original returned file in an
external backup and record its SHA-256. After all three roles and the report
verifier pass, build a new candidate archive without overwriting the immutable
v1 manifest:

```bash
uv run --locked falsirag ops diagnostic-data pack \
  --source diagnostics \
  --archive artifact-dist/far-diagnostics-v2.tar.gz \
  --manifest artifact-dist/diagnostics-v2.candidate.json
```

Do not mutate the `artifacts-v1` release or point the repository at this local
candidate. Publishing `artifacts-v2`, independently downloading it into an
empty directory, comparing the complete tree, and switching the packaged
manifest require a separately reviewed and authorized release cutover. Until
that succeeds, preserve the installed diagnostic tree and all three original
human return files.
