# Automatic preannotation

FAR can now generate machine preannotations for a blind annotation packet. This
is useful when no human annotators are immediately available, but it does not
satisfy the publication annotation gate. The output is deliberately named
`preannotations_*.jsonl` and carries `publication_gold: false`.

## Recommended local open-source workflow

When no human annotators are available, use the local Qwen/Ollama path first.
It requires no cloud key and keeps the generated artifacts on the Windows GPU
host's D: drive:

```bash
ssh windows-gpu
source ~/miniconda3/etc/profile.d/conda.sh
conda activate train
source /mnt/d/FAR-workspace/FAR/scripts/windows_gpu_env.sh
cd /mnt/d/FAR-workspace/FAR
```

Create a blind packet:

```bash
uv run python -m bench.build.annotate_packet build \
  --data-dir bench \
  --output-dir /mnt/d/FAR-outputs/falsirag_annotation_packet \
  --annotator machine_qwen \
  --annotator machine_rules \
  --overwrite
```

Generate schema-valid machine suggestions with the local non-thinking Qwen2.5
annotation-helper config:

```bash
falsirag-auto-annotate generate \
  --packet-dir /mnt/d/FAR-outputs/falsirag_annotation_packet \
  --output-dir /mnt/d/FAR-outputs/qwen25_preannotations \
  --config experiments/configs/qwen25_autolabel.yaml \
  --preannotator-id qwen25_7b_ollama_machine_weak \
  --overwrite
```

`experiments/configs/qwen25_autolabel.yaml` is an annotation-helper config, not
part of the formal model-comparison matrix. The completed Windows GPU run wrote
300/300 rows with one conservative fallback after retry:

- preannotation SHA-256:
  `6796d46aa84e7c0a0ff32083e9257aa5fc6c7e5c3a9236735f4dfc659aa34caa`;
- summary: 300 rows, 300 unique samples, 1 fallback (`F0138`), 0 missing packet
  samples, `publication_gold: false`;
- Label Studio export: `/mnt/d/FAR-outputs/label_studio_qwen25`, 300 tasks with
  300 machine predictions.

FAR's Ollama adapter accepts an explicit `think` option. Formal Qwen3.5 runs set
it to `false` and fail closed when Ollama returns thinking text without a final
response; internal reasoning must never be scored as the answer. The earlier
Qwen3.5 rough annotation bundle was produced with a compatibility fallback and
is retained only as historical, non-gold reviewer assistance.
Generation writes the preannotation JSONL incrementally, so long runs can be
monitored with `wc -l /mnt/d/FAR-outputs/qwen25_preannotations/*.jsonl`.

The first full Qwen3.5 run completed 300/300 rows but produced many schema
fallbacks, so it remains a rough review bundle rather than the preferred
machine draft.
If Windows sleeps, restarts, or the tmux job is killed after some rows have been
written, restart without discarding completed rows:

```bash
falsirag-auto-annotate generate \
  --packet-dir /mnt/d/FAR-outputs/falsirag_annotation_packet \
  --output-dir /mnt/d/FAR-outputs/qwen25_preannotations \
  --config experiments/configs/qwen25_autolabel.yaml \
  --preannotator-id qwen25_7b_ollama_machine_weak \
  --resume
```

If a completed or partial file contains fallback rows, retry only those rows
plus any missing rows:

```bash
falsirag-auto-annotate generate \
  --packet-dir /mnt/d/FAR-outputs/falsirag_annotation_packet \
  --output-dir /mnt/d/FAR-outputs/qwen25_preannotations \
  --config experiments/configs/qwen25_autolabel.yaml \
  --preannotator-id qwen25_7b_ollama_machine_weak \
  --resume \
  --retry-fallbacks
```

At any point, summarize the in-progress or completed output:

```bash
falsirag-auto-annotate summarize \
  --preannotation-dir /mnt/d/FAR-outputs/qwen25_preannotations \
  --packet-dir /mnt/d/FAR-outputs/falsirag_annotation_packet
```

The summary reports rows, duplicate IDs, fallback failures, non-gold guards, and
whether the output fully matches the packet.

This is the recommended no-human fallback for development. It is still not
publication gold. See `docs/MACHINE_ANNOTATION_FALLBACK.md` for the researched
open-source alternatives and the paper wording constraints.

## Rule-based weak labels

For a second machine-only signal that does not call an LLM or cloud API, run the
deterministic weak-supervision labeler on the same blind packet:

```bash
uv run falsirag-weak-label \
  --packet-dir outputs/falsirag_annotation_packet \
  --output-dir outputs/rules_weak_labels \
  --overwrite
```

It writes `weak_annotations.jsonl` and `weak_annotation_manifest.json` with
`publication_gold: false`. The labeler uses conservative date/number/entity,
source-reliability, causal-language, and definition/scope rules. Rows where no
rule fires are marked `abstained: true`; this means "no weak signal", not "no
conflict".

Use these weak labels to compare against LLM preannotations or to prioritize
human review. Do not report them as independent human labels or Cohen's kappa.

To compare the LLM suggestions and rule weak labels, run:

```bash
uv run falsirag-machine-label-audit \
  --preannotation-dir outputs/deepseek_preannotations_pilot \
  --weak-label-dir outputs/rules_weak_labels \
  --packet-dir outputs/falsirag_annotation_packet \
  --output-dir outputs/machine_label_audit \
  --overwrite
```

The audit writes `machine_label_audit.json` and
`machine_label_comparison.jsonl`. Use its priority-review sample list to focus
scarce human review time. Machine-machine agreement is not human IAA.

The current full-packet machine-only audit was generated locally from the
Windows GPU Qwen2.5 preannotation bundle after copying the remote artifacts into
the ignored `outputs/remote_machine_annotation/` directory:

- weak-label rows: 300/300;
- non-abstained weak signals: 211/300; abstentions: 89/300;
- weak-label SHA-256:
  `f31f2422d5c3471002675db57b2b5104ee1ee71bb14b170477c95aa02296f8a1`;
- Qwen2.5 preannotation SHA-256:
  `6796d46aa84e7c0a0ff32083e9257aa5fc6c7e5c3a9236735f4dfc659aa34caa`;
- machine-audit shared samples: 300/300; missing packet samples: 0;
- priority human-review samples from machine disagreement: 127;
- weak-non-abstained agreement: conflict-present 0.863, conflict-type 0.403,
  revision-action 0.398; and
- audit guard: `publication_gold: false`,
  `can_satisfy_human_annotation_gate: false`.

These numbers are useful for reviewer triage and quality-control planning only.
They must not be reported as human inter-annotator agreement.

## Optional DeepSeek workflow

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
  --reviewer-id reviewer_a \
  --preannotation-dir outputs/deepseek_preannotations_pilot \
  --output-dir outputs/label_studio_falsirag \
  --overwrite
```

The export is bound to exactly one declared reviewer and preserves that
reviewer's independently shuffled evidence order. Generate a separate project
for `reviewer_b`; one reviewer's export cannot be relabeled as the other.

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

The importer rejects duplicate tasks, modified question/evidence context,
missing rationales, multiple active completions, cross-reviewer exports, and
packet fingerprint mismatches. Install the validated result atomically without
editing `packet_manifest.json`:

```bash
uv run python -m bench.build.annotate_packet install-review \
  --packet-dir outputs/falsirag_annotation_packet \
  --review-file outputs/label_studio_reviewed_reviewer_a/annotations_reviewer_a.jsonl \
  --reviewer-id reviewer_a
```

Repeat with a separately generated project for `reviewer_b`, then complete
adjudication.

At any point, inspect packet progress and source compatibility:

```bash
uv run python -m bench.build.annotate_packet status \
  --packet-dir outputs/falsirag_annotation_packet \
  --data-dir bench
```

This reports per-reviewer blank/invalid/completed counts, adjudication progress,
packet-vs-benchmark fingerprints, visible-field mismatches, and whether it is
safe to export the adjudication UI or compile the final evidence archive.

After both reviewer files are installed, Label Studio can also be used for the
adjudicator without hand-editing `adjudications.jsonl`:

```bash
uv run falsirag-auto-annotate adjudication-label-studio \
  --packet-dir outputs/falsirag_annotation_packet \
  --output-dir outputs/label_studio_adjudicator \
  --overwrite

uv run falsirag-auto-annotate adjudication-label-studio-import \
  --packet-dir outputs/falsirag_annotation_packet \
  --label-studio-json outputs/label_studio_adjudicator/project-export.json \
  --output-dir outputs/label_studio_adjudicated \
  --adjudicator-id adjudicator_1 \
  --overwrite

uv run python -m bench.build.annotate_packet install-adjudication \
  --packet-dir outputs/falsirag_annotation_packet \
  --adjudication-file outputs/label_studio_adjudicated/adjudications.jsonl \
  --adjudicator-id adjudicator_1
```

The adjudication export is fingerprint-bound to the current packet, the blank
adjudication template, and both frozen reviewer files. The import includes
reviewer labels and evidence-ID maps as context, but the final gold annotation
must be the adjudicator's own completed Label Studio result.

The UI is a review accelerator, not a replacement for the publication gate.
For the preregistered independent-human IAA, omit `--preannotation-dir`; shared
machine predictions can anchor both reviewers and therefore must not be used to
claim strict independent agreement. Prediction-assisted reviews may be retained
as an explicitly labeled secondary workflow.

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

I checked the current open-source ecosystem again on 2026-07-02. The practical options
for FAR are:

| Tool | Best FAR use | Fit |
|---|---|---|
| [Label Studio](https://labelstud.io/guide/predictions.html) | Human review UI for blind packets with imported LLM predictions | Best immediate fit; FAR exports `label_config.xml` and `tasks.json` directly in its documented `predictions` format. Its ML backend can wrap custom models for live auto-labeling, but static prediction import is simpler for this 300-row benchmark. |
| [doccano auto-labeling](https://doccano.github.io/doccano/advanced/auto_labelling_config/) | Open-source text annotation UI with Web-API auto-labeling; [`auto-labeling-pipeline`](https://github.com/doccano/auto-labeling-pipeline) can annotate doccano documents automatically | Viable if the team prefers doccano, but migrating now would add schema conversion work without closing the publication gate. |
| [Argilla](https://docs.v1.argilla.io/en/v1.3.0/guides/programmatic_labeling_with_rules.html) | Collaborative feedback/annotation workflows and weak/programmatic labeling for text classification | Useful for review records and weak supervision, but FAR would need a separate schema bridge for conflict type plus revision action. |
| [Snorkel](https://github.com/snorkel-team/snorkel) | Weak supervision from labeling functions | Useful for deterministic rules such as number/date/entity mismatch; less useful for nuanced revision quality. |
| [Refuel Autolabel](https://github.com/refuel-ai/autolabel) | LLM-based batch labeling from prompts | Similar role to FAR's built-in preannotator; useful if you prefer its prompt/evaluation harness. |
| [Distilabel](https://distilabel.argilla.io/) | LLM synthetic-data and labeling pipelines | Useful for larger LLM labeling pipelines, but more machinery than FAR needs for the current paper artifact. |

FAR's built-in preannotator is intentionally simpler: it preserves the current
JSONL protocol and avoids introducing another service into the reproduction
path.
