# Machine-only annotation fallback

Date checked: 2026-06-30

This document records the fallback plan when no independent human annotators are
available. The fallback is useful for continuing FAR development and for
reporting a clearly labeled machine-seeded study, but it is not equivalent to
the original double-human annotation protocol.

## Recommendation

Use FAR's built-in LLM preannotator with the local open-weight Qwen/Ollama
runtime as the primary automatic labeler, then optionally add rule-based weak
supervision with Snorkel-style labeling functions for audit signals.

Why this is the best fit:

- FAR already exports blind packets and schema-valid machine preannotations.
- The local Qwen/Ollama path avoids cloud keys and keeps artifacts on the
  Windows GPU host's D: drive.
- Label Studio can display FAR's predictions as preannotations if a reviewer
  later becomes available.
- Weak-supervision tools can provide an independent deterministic signal for
  date, number, entity, source-reliability, and definition-conflict cases.

What it cannot do:

- It cannot satisfy the `required_annotators: 2` publication gate.
- It cannot support claims of independent human annotation or human Cohen's
  kappa.
- It should not be used to rewrite `machine_seed_is_gold` to `true`.

If the paper proceeds without humans, describe the labels as
`machine-seeded`, `weakly supervised`, or `pseudo-gold`, and keep the original
human-annotation gate listed as a limitation.

## Open-source tools checked

| Tool | Status | FAR fit | Decision |
|---|---|---|---|
| FAR built-in preannotator + Qwen/Ollama | Project-local, open-weight model runtime | Directly emits FAR JSONL and Label Studio predictions | Use first |
| Label Studio | Open-source annotation UI with prediction imports | FAR already exports `label_config.xml` and `tasks.json` | Use as review UI, not autonomous gold |
| Refuel Autolabel | Open-source LLM batch labeling library | Similar to FAR's preannotator but adds an external config/runtime layer | Optional, not needed immediately |
| Distilabel | Open-source LLM synthetic-data and AI-feedback pipelines | Good for large judge/label pipelines | Optional if scaling beyond current 300 samples |
| Snorkel | Open-source weak supervision | Strong fit for programmatic labeling functions and label-model aggregation | Good second signal |
| skweak | Open-source weak supervision for NLP | Useful idea, but mostly spaCy/span/classification-oriented | Do not prioritize |
| Argilla | Open-source dataset/feedback platform | Good collaborative UI and suggestions | Optional alternative to Label Studio |

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

Start the local Qwen/Ollama preannotation run in `tmux`:

```bash
tmux new -s far-auto-label
falsirag-auto-annotate generate \
  --packet-dir /mnt/d/FAR-outputs/falsirag_annotation_packet \
  --output-dir /mnt/d/FAR-outputs/qwen35_preannotations \
  --config experiments/configs/qwen_open.yaml \
  --preannotator-id qwen35_9b_ollama_thinkingfix_machine_weak \
  --overwrite
```

The `thinkingfix` identifier records that FAR's Ollama adapter is using the
Qwen3.5 thinking-aware compatibility path. This is necessary because the current
local Qwen3.5/Ollama response can put JSON in the `thinking` field while leaving
the standard `response` field empty.

Detach with `Ctrl+B`, then `D`. Reattach with:

```bash
tmux attach -t far-auto-label
```

To export the predictions for a future reviewer:

```bash
falsirag-auto-annotate label-studio \
  --packet-dir /mnt/d/FAR-outputs/falsirag_annotation_packet \
  --preannotation-dir /mnt/d/FAR-outputs/qwen35_preannotations \
  --output-dir /mnt/d/FAR-outputs/label_studio_qwen35 \
  --overwrite
```

The resulting files are explicitly non-gold:

- `preannotation_manifest.json` contains `publication_gold: false`.
- `preannotation_manifest.json` contains
  `can_satisfy_human_annotation_gate: false`.
- `compile_annotations` rejects unreviewed machine drafts.

## Weak-supervision layer

If we need a second automatic signal without another LLM, implement lightweight
labeling functions rather than a full service:

- temporal mismatch: years/dates in answer vs evidence disagree;
- numerical mismatch: normalized numbers, percentages, or ranges disagree;
- entity mismatch: named entities in answer are contradicted by evidence;
- source reliability: answer includes unverified/secondary-source phrasing while
  evidence is from the authoritative source;
- causal overclaim: answer uses causal language while evidence only supports
  correlation;
- definition/scope mismatch: answer uses a broader/narrower definition than the
  evidence.

These functions can be aggregated with a simple majority/abstain report first.
If the rule set grows, Snorkel's label model is the most appropriate open-source
aggregator.

Report these outputs as machine agreement, not as human IAA.

## References

- Label Studio prediction imports:
  <https://labelstud.io/guide/predictions.html>
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
