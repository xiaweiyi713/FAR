# Automatic preannotation

FAR can now generate machine preannotations for a blind annotation packet. This
is useful when no human annotators are immediately available, but it does not
satisfy the publication annotation gate. The output is deliberately named
`preannotations_*.jsonl` and carries `publication_gold: false`.

## Recommended DeepSeek workflow

Create a blind packet first:

```bash
uv run python -m bench.build.annotate_packet build \
  --data-dir bench \
  --output-dir outputs/falsirag_annotation_packet \
  --annotator reviewer_a \
  --annotator reviewer_b \
  --overwrite
```

Set the API key only in your shell. Do not put it in YAML, Git, notebooks, or
logs:

```bash
export DEEPSEEK_API_KEY="<paste key here>"
```

Generate a small pilot before scaling:

```bash
uv run falsirag-auto-annotate generate \
  --packet-dir outputs/falsirag_annotation_packet \
  --output-dir outputs/deepseek_preannotations_pilot \
  --config experiments/configs/deepseek.yaml \
  --preannotator-id deepseek_chat_v1 \
  --limit 25 \
  --overwrite
```

If the pilot looks sane, remove `--limit` and run the full packet.

For compatibility, `falsirag-auto-annotate --packet-dir ... --output-dir ...`
also runs generate mode, but the explicit subcommand is clearer.

## Creating a human review draft

Convert the preannotations into a reviewer-editable draft:

```bash
uv run falsirag-auto-annotate draft \
  --packet-dir outputs/falsirag_annotation_packet \
  --preannotation-dir outputs/deepseek_preannotations_pilot \
  --output-dir outputs/deepseek_review_draft \
  --reviewer-id reviewer_a \
  --overwrite
```

This creates `draft_annotations_reviewer_a.jsonl`. The rows are filled with LLM
suggestions, but they include:

- `draft_from_machine_preannotation: true`
- `human_reviewed: false`

`compile_annotations` rejects these rows until a human actually reviews the
draft, corrects it as needed, and sets `human_reviewed` to `true`. This guard is
intentional: a machine draft is a starting point, not an independent annotation.

## Reviewing in Label Studio

If you want an open-source UI instead of editing JSONL by hand, export the blind
packet and optional machine predictions to a Label Studio import bundle:

```bash
uv run falsirag-auto-annotate label-studio \
  --packet-dir outputs/falsirag_annotation_packet \
  --preannotation-dir outputs/deepseek_preannotations_pilot \
  --output-dir outputs/label_studio_falsirag \
  --overwrite
```

The export writes:

- `label_config.xml`: a ready-to-import labeling interface;
- `tasks.json`: blind packet tasks, with LLM preannotations attached as
  Label Studio `predictions` when available;
- `label_studio_manifest.json`: packet/preannotation fingerprints and a
  `publication_gold: false` guard.

Create a Label Studio project with `label_config.xml`, import `tasks.json`, and
let reviewers correct the predicted labels. After review, export Label Studio's
JSON task file and convert it back into FAR's reviewer JSONL format:

```bash
uv run falsirag-auto-annotate label-studio-import \
  --packet-dir outputs/falsirag_annotation_packet \
  --label-studio-json outputs/label_studio_falsirag/project-export.json \
  --output-dir outputs/label_studio_reviewed_reviewer_a \
  --reviewer-id reviewer_a \
  --overwrite
```

The importer writes `annotations_reviewer_a.jsonl`. Copy it into the packet
directory or reference it from `packet_manifest.json`, then repeat the process
for a genuinely independent second reviewer and complete adjudication.

The UI is a review accelerator, not a replacement for the publication gate.

## What the file means

Each preannotation contains:

- the blind question, initial answer, claims, and shuffled evidence;
- a suggested conflict presence/type;
- a suggested revision action;
- a suggested revised answer and rationale;
- confidence and `needs_human_review: true`.

These suggestions can speed up later review, but they are not independent human
annotations. Do not copy them into `annotations_*.jsonl` and compile them as
gold unless a human has actually reviewed, corrected, and frozen the file under
the annotation protocol.

## Why this is separate from the gold path

The benchmark paper needs evidence that humans independently judged the conflict
type and revision action. LLM preannotations are useful for triage, error
analysis, and estimating whether the schema is coherent, but they can share the
same model biases as the FAR system being evaluated. Therefore:

- `bench/manifest.json` remains `publication_ready: false`;
- `compile_annotations` still requires completed annotation and adjudication
  files, and rejects unreviewed machine drafts;
- the test split still requires an external blind custodian for final reporting.

## Open-source alternatives

I checked the current open-source ecosystem on 2026-06-29. The practical options
for FAR are:

| Tool | Best FAR use | Fit |
|---|---|---|
| [Label Studio](https://labelstud.io/guide/predictions.html) | Human review UI for blind packets with imported LLM predictions | Best immediate fit; FAR exports `label_config.xml` and `tasks.json` directly in its documented `predictions` format. |
| [Argilla](https://docs.argilla.io/v2.1/how_to_guides/annotate/) | Collaborative feedback/annotation workflows for NLP/LLM datasets | Its Suggestions are editable pre-filled responses; useful for review records, but FAR would need a separate schema bridge. |
| [Snorkel](https://github.com/snorkel-team/snorkel) | Weak supervision from labeling functions | Useful for deterministic rules such as number/date/entity mismatch; less useful for nuanced revision quality. |
| [Refuel Autolabel](https://github.com/refuel-ai/autolabel) | LLM-based batch labeling from prompts | Similar role to FAR's built-in preannotator; useful if you prefer its prompt/evaluation harness. |
| [Distilabel](https://distilabel.argilla.io/) | LLM synthetic-data and labeling pipelines | Useful for larger LLM labeling pipelines, but more machinery than FAR needs for the current paper artifact. |

FAR's built-in preannotator is intentionally simpler: it preserves the current
JSONL protocol and avoids introducing another service into the reproduction
path.
