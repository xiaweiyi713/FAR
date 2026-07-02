# Human Annotation and Adjudication Protocol

This protocol is the publication gate for FalsiRAG-Bench. Machine
preannotations can speed up review, but they cannot replace two independent
human annotators, adjudication, or the Cohen's kappa report.

## Scope

Annotators judge the candidate benchmark rows in a blind packet generated from
`bench/falsirag_bench.jsonl` and `bench/corpus.jsonl`. The packet hides split,
category, construction metadata, gold labels, evidence roles, expected
revisions, and machine-seeded labels.

The required output is:

1. one completed `annotations_<annotator>.jsonl` file per independent reviewer;
2. one completed `adjudications.jsonl` after both reviewer files are frozen;
3. a compiled adjudicated benchmark directory with `annotation_report.json`;
4. all mean kappas at least `0.60` for the publication gate.

## Build the blind packet

Use stable, non-identifying reviewer IDs:

```bash
uv run python -m bench.build.annotate_packet build \
  --data-dir bench \
  --output-dir outputs/annotations/falsirag_packet_v1 \
  --annotator reviewer_a \
  --annotator reviewer_b
```

The packet contains:

- `annotations_reviewer_a.jsonl`
- `annotations_reviewer_b.jsonl`
- `adjudications.jsonl`
- `packet_manifest.json`
- `README.md`

Each reviewer receives only their own `annotations_*.jsonl`, the packet
`README.md`, and these instructions. Do not send `falsirag_bench.jsonl`,
`bench/splits/`, machine preannotations, or another reviewer's file.

## Review fields

For every row, reviewers fill `annotation`:

| Field | Required value |
|---|---|
| `conflict_present` | `true` when the visible evidence contradicts, limits, or materially weakens at least one claim in the initial answer; otherwise `false`. |
| `conflict_type` | One of `temporal`, `entity`, `numerical`, `causal`, `source_reliability`, `definition`, `counter_evidence` when `conflict_present=true`; leave blank only when `conflict_present=false`. |
| `revision_action` | One of the valid actions in `bench/schema.py`; choose the smallest action that fixes the answer. |
| `revised_answer_acceptable` | `true` when the answer should be revised according to the selected action; `false` when the evidence does not justify the proposed revision. |
| `rationale` | A short human explanation citing the visible evidence ID(s), e.g. `EVIDENCE_A says 2023, not 2024`. |

Reviewers should judge only the visible packet. They should not search the web,
inspect source benchmark files, consult machine suggestions, or coordinate with
each other.

## Conflict type guidance

- `temporal`: date, year, version, deadline, or ordering is wrong.
- `entity`: the answer names the wrong person, organization, product, place, or
  conflates related entities.
- `numerical`: value, percentage, unit, range, count, or arithmetic is wrong.
- `causal`: the answer asserts causation but the evidence supports only
  correlation, association, possibility, or a narrower mechanism.
- `source_reliability`: an unreliable, secondary, stale, or lower-authority
  statement conflicts with a more authoritative visible source.
- `definition`: the answer and evidence use materially different definitions,
  scopes, denominators, or inclusion criteria.
- `counter_evidence`: visible evidence supplies a direct exception or refuting
  case that should retract or qualify the answer.

When multiple types apply, choose the type that most directly determines the
needed revision. Use the rationale to mention secondary issues.

## Revision action guidance

Use the action names defined in `bench/schema.py`. The common mapping is:

- temporal mismatch -> `correct_temporal`
- entity mismatch -> `requalify_entity`
- numerical mismatch -> `replace_numerical`
- causal overclaim -> `downgrade_causal_to_correlation`
- source conflict -> `prefer_reliable_source`
- definition/scope conflict -> `clarify_definition`
- direct refutation -> `retract`
- weak or incomplete conflict -> `qualify_uncertainty`

If the visible evidence does not warrant changing the answer, use
`qualify_uncertainty` and set `conflict_present=false` only when there is no
material conflict at all.

## Freeze reviewer files

Before adjudication, verify both reviewer files are complete by running a dry
compile. It should fail only because adjudication is still blank; if it reports
missing reviewer labels, return the file to that reviewer.

Do not edit reviewer files after adjudication begins. If a clerical correction
is required, record the correction in a separate note and keep the original file
under a dated backup path.

## Adjudication

The adjudicator reviews only after both independent files are frozen. For every
row, fill `gold_annotation` in `adjudications.jsonl`:

| Field | Required value |
|---|---|
| `conflict_present` | Final adjudicated boolean. |
| `conflict_type` | Final conflict type, or blank only if no conflict. |
| `revision_action` | Final revision action. |
| `revised_answer_acceptable` | Final acceptability boolean. |
| `revised_answer` | Optional corrected reference answer; leave blank if the seeded answer remains adequate after the action. |
| `rationale` | One or two sentences explaining the adjudication. |

The adjudicator may consult both reviewer files and the visible packet, but not
the original machine-seeded hidden labels as authority.

## Compile and gate

After reviewer and adjudication files are complete:

```bash
uv run python -m bench.build.annotate_packet compile \
  --data-dir bench \
  --packet-dir outputs/annotations/falsirag_packet_v1 \
  --output-dir outputs/annotations/falsirag_adjudicated_v1
```

The compiler:

- checks benchmark/corpus fingerprints;
- rejects incomplete or invalid reviewer/adjudication fields;
- rejects unreviewed machine drafts with `human_reviewed=false`;
- writes an adjudicated benchmark copy;
- writes `annotation_report.json` with pairwise and mean Cohen's kappa values;
- keeps `publication_ready=false` until the external blind-test gate is also
  closed.

The annotation gate is considered passed only when
`annotation_report.json` has:

```json
{
  "adjudicated": true,
  "agreement_gate_passed": true
}
```

and every mean kappa is at least `0.60`.

Record the compiled directory in a working copy of
`submission/evidence.template.json`. The final readiness command independently
rechecks reviewer count, adjudication status, kappas, row statuses, and dataset
fingerprints; editing only the manifest cannot close the gate.

## What not to do

- Do not copy machine preannotations into reviewer files without real human
  review.
- Do not set `human_reviewed=true` unless a human has checked that row.
- Do not use local test labels to tune prompts, code, or adjudication policy.
- Do not report kappa from machine-vs-machine or machine-vs-human suggestions
  as independent human IAA.
- Do not change `bench/manifest.json` manually; use the compiler output.
