# Machine-only annotation fallback

Date checked: 2026-07-02

This document records the fallback plan when no independent human annotators are
available. The fallback is useful for continuing FAR development and for
reporting a clearly labeled machine-seeded study, but it is not equivalent to
the original double-human annotation protocol.

## Recommendation

Use FAR's built-in LLM preannotator with the local open-weight Qwen/Ollama
runtime as the primary automatic labeler, then add FAR's deterministic
rule-based weak-supervision labeler as a second non-gold machine signal.

Why this is the best fit:

- FAR already exports blind packets and schema-valid machine preannotations.
- The local Qwen/Ollama path avoids cloud keys and keeps artifacts on the
  Windows GPU host's D: drive.
- Label Studio can display FAR's predictions as preannotations if a reviewer
  later becomes available.
- The built-in weak labeler provides an independent deterministic signal for
  date, number, entity, source-reliability, causal-language, and
  definition/scope cases without introducing another service.

What it cannot do:

- It cannot satisfy the `required_annotators: 2` publication gate.
- It cannot support claims of independent human annotation or human Cohen's
  kappa.
- It should not be used to rewrite `machine_seed_is_gold` to `true`.

If the paper proceeds without humans, describe the labels as
`machine-seeded`, `weakly supervised`, or `pseudo-gold`, and keep the original
human-annotation gate listed as a limitation.

## Open-source tools checked

The fallback research focused on open-source systems that can either import
machine predictions for review or generate weak/pseudo labels from rules and
LLM judges. The practical decision is to keep FAR's own JSONL schema as the
source of truth, use Label Studio only as a review UI, and add a deterministic
weak-label layer rather than introducing another labeling service before the
300-sample benchmark is adjudicated.

| Tool | Status | FAR fit | Decision |
|---|---|---|---|
| FAR built-in preannotator + Qwen/Ollama | Project-local, open-weight model runtime | Directly emits FAR JSONL and Label Studio predictions | Use first |
| Label Studio | Open-source annotation UI with prediction imports and an ML backend that can wrap custom models as a service | FAR already exports `label_config.xml` and `tasks.json`; predictions import is enough for static prelabels, while the ML backend is useful only if reviewers need live suggestions | Use as review UI, not autonomous gold |
| doccano auto-labeling | Open-source text annotation tool with Web-API auto-labeling and a maintained `auto-labeling-pipeline` package | Good if the project moves to doccano, but FAR already has Label Studio export/import and richer revision fields | Optional alternative UI; do not migrate now |
| Refuel Autolabel | Open-source LLM batch labeling library | Similar to FAR's preannotator but adds an external config/runtime layer | Optional, not needed immediately |
| Distilabel | Open-source LLM synthetic-data and AI-feedback pipelines | Good for large judge/label pipelines | Optional if scaling beyond current 300 samples |
| Snorkel | Open-source weak supervision | Strong fit for programmatic labeling functions and label-model aggregation | Good second signal if FAR's rule layer grows beyond simple abstain/priority review |
| skweak | Open-source weak supervision for NLP | Useful idea, but mostly spaCy/span/classification-oriented | Do not prioritize |
| Argilla | Open-source dataset/feedback platform with programmatic-labeling/weak-supervision workflows for text classification | Good collaborative UI and suggestions; FAR would need a schema bridge for conflict type + revision action | Optional alternative to Label Studio |

Short version: the open-source tooling exists, but none of it removes FAR's
publication need for independent human review. The recommended path is
therefore to keep FAR's own schema-valid preannotator, use Label Studio
prediction imports for review if humans become available, and keep rule/weak
labels as a triage signal.

## D-drive local Qwen workflow

On the Mac, sync the repository to the Windows GPU host using the documented
D-drive command from `docs/REPRODUCING.md`. On the Windows GPU host:

```bash
ssh windows-gpu
source ~/miniconda3/etc/profile.d/conda.sh
conda activate train
source /mnt/d/FAR-workspace/FAR/scripts/windows_gpu_env.sh
cd /mnt/d/FAR-workspace/FAR
```

Build a blind packet if one is not already present:

```bash
uv run python -m bench.build.annotate_packet build \
  --data-dir bench \
  --output-dir /mnt/d/FAR-outputs/falsirag_annotation_packet \
  --annotator machine_qwen \
  --annotator machine_rules \
  --overwrite
```

Start the local Qwen/Ollama preannotation run in `tmux` with the preferred
non-thinking Qwen2.5 annotation-helper config:

```bash
tmux new -s far-auto-label
falsirag-auto-annotate generate \
  --packet-dir /mnt/d/FAR-outputs/falsirag_annotation_packet \
  --output-dir /mnt/d/FAR-outputs/qwen25_preannotations \
  --config experiments/configs/qwen25_autolabel.yaml \
  --preannotator-id qwen25_7b_ollama_machine_weak \
  --overwrite
```

The completed Qwen2.5 run produced 300/300 rows with one conservative fallback
after retry. Its preannotation SHA-256 is
`6796d46aa84e7c0a0ff32083e9257aa5fc6c7e5c3a9236735f4dfc659aa34caa`, and the
Label Studio review bundle is `/mnt/d/FAR-outputs/label_studio_qwen25`.

For interrupted long runs, reuse the same command with `--resume` instead of
`--overwrite`; FAR skips already written sample IDs and appends the remaining
machine preannotations.
If fallback rows remain after a run, add `--retry-fallbacks` to remove those
fallback rows and regenerate only the failed/missing sample IDs.

The first full Qwen3.5 run completed all 300 rows but had a high fallback rate,
so it should be treated as a rough review bundle. It used the earlier
thinking-field compatibility path. That path is no longer accepted for formal
experiments: current FAR either disables thinking explicitly or fails closed
when no final `response` is returned.

Detach with `Ctrl+B`, then `D`. Reattach with:

```bash
tmux attach -t far-auto-label
```

To export the predictions for a future reviewer:

```bash
falsirag-auto-annotate label-studio \
  --packet-dir /mnt/d/FAR-outputs/falsirag_annotation_packet \
  --preannotation-dir /mnt/d/FAR-outputs/qwen25_preannotations \
  --output-dir /mnt/d/FAR-outputs/label_studio_qwen25 \
  --overwrite
```

The resulting files are explicitly non-gold:

- `preannotation_manifest.json` contains `publication_gold: false`.
- `preannotation_manifest.json` contains
  `can_satisfy_human_annotation_gate: false`.
- `compile_annotations` rejects unreviewed machine drafts.

## Weak-supervision layer

Generate a second automatic signal without another LLM:

```bash
uv run falsirag-weak-label \
  --packet-dir /mnt/d/FAR-outputs/falsirag_annotation_packet \
  --output-dir /mnt/d/FAR-outputs/rules_weak_labels \
  --overwrite
```

The command writes:

- `weak_annotations.jsonl`
- `weak_annotation_manifest.json`

Both files explicitly set `publication_gold: false` and
`can_satisfy_human_annotation_gate: false`. The labeler uses lightweight
labeling functions:

- temporal mismatch: years/dates in answer vs evidence disagree;
- numerical mismatch: normalized numbers, percentages, or ranges disagree;
- entity mismatch: named entities in answer are contradicted by evidence;
- source reliability: answer includes unverified/secondary-source phrasing while
  evidence is from the authoritative source;
- causal overclaim: answer uses causal language while evidence only supports
  correlation;
- definition/scope mismatch: answer uses a broader/narrower definition than the
  evidence.

Rows where no function fires are marked `abstained: true`. Treat this as "no
machine signal", not as a negative label. If the rule set grows beyond this
simple majority/abstain design, Snorkel's label model remains the most
appropriate open-source aggregator.

Report these outputs as machine agreement, not as human IAA.

To audit LLM-vs-rule agreement:

```bash
uv run falsirag-machine-label-audit \
  --preannotation-dir /mnt/d/FAR-outputs/qwen25_preannotations \
  --weak-label-dir /mnt/d/FAR-outputs/rules_weak_labels \
  --packet-dir /mnt/d/FAR-outputs/falsirag_annotation_packet \
  --output-dir /mnt/d/FAR-outputs/machine_label_audit \
  --overwrite
```

Prioritize rows where the audit reports conflict-type or revision-action
disagreement. This is a triage device, not an agreement statistic for the
paper.

The full-packet audit has now been run from the completed Qwen2.5 bundle:

- packet: 300 samples, copied from `/mnt/d/FAR-outputs/falsirag_annotation_packet`;
- Qwen2.5 preannotations: 300 samples, SHA-256
  `6796d46aa84e7c0a0ff32083e9257aa5fc6c7e5c3a9236735f4dfc659aa34caa`;
- deterministic weak labels: 300 samples, 211 non-abstained, 89 abstained,
  SHA-256
  `f31f2422d5c3471002675db57b2b5104ee1ee71bb14b170477c95aa02296f8a1`;
- weak-label conflict counts: temporal 118, numerical 30,
  source-reliability 29, entity 20, causal 10, definition 4;
- audit shared samples: 300/300, missing packet samples: 0;
- agreement across all shared rows: conflict-present 0.687, conflict-type
  0.363, revision-action 0.370;
- agreement on weak-non-abstained rows: conflict-present 0.863,
  conflict-type 0.403, revision-action 0.398; and
- priority human-review list: 127 samples.

The relatively low conflict-type/action agreement is expected: the rule layer is
intentionally high-bias and sparse, while the LLM preannotator attempts the full
schema. The disagreements are therefore useful as a review queue, not as a
negative result or a replacement for two human annotators.

## References

- Label Studio prediction imports:
  <https://labelstud.io/guide/predictions.html>
- Label Studio ML backend:
  <https://labelstud.io/guide/ml>
- doccano auto-labeling configuration:
  <https://doccano.github.io/doccano/advanced/auto_labelling_config/>
- doccano auto-labeling pipeline:
  <https://github.com/doccano/auto-labeling-pipeline>
- Argilla programmatic labeling:
  <https://docs.v1.argilla.io/en/v1.3.0/guides/programmatic_labeling_with_rules.html>
- Refuel Autolabel:
  <https://github.com/refuel-ai/autolabel>
- Distilabel:
  <https://distilabel.argilla.io/latest/>
- Snorkel:
  <https://github.com/snorkel-team/snorkel>
- skweak:
  <https://github.com/NorskRegnesentral/skweak>
- Argilla:
  <https://docs.argilla.io/latest/>
