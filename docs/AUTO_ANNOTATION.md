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

If you later want a UI or weak-supervision layer around FAR's files:

- Label Studio can import preannotations or connect ML backends.
- Argilla is a collaborative annotation and feedback platform for AI datasets.
- Snorkel is useful when you can write labeling functions instead of using an
  LLM directly.
- Refuel Autolabel is a lightweight LLM-based text labeling tool.

FAR's built-in preannotator is intentionally simpler: it preserves the current
JSONL protocol and avoids introducing another service into the reproduction
path.
