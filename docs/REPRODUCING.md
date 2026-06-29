# Reproduction Guide

## Build and validate data

```bash
uv run python -m bench.build.extend_from_verabench \
  --source-dir ../VeraRAG/data/verabench --output-dir bench
uv run falsirag-validate-bench --output outputs/benchmark_validation.json
uv run python -m bench.build.import_fever_slice
```

The build is deterministic. Any data change requires regenerated fingerprints.

## Human annotation

```bash
uv run python -m bench.build.annotate_packet build \
  --data-dir bench --output-dir outputs/annotations \
  --annotator annotator_a --annotator annotator_b
# Freeze both completed files, then complete adjudications.jsonl.
uv run python -m bench.build.annotate_packet compile \
  --data-dir bench --packet-dir outputs/annotations \
  --output-dir outputs/adjudicated_bench
```

The compiler rejects missing labels, mismatched fingerprints, and incomplete
adjudication. It reports three Cohen's kappa values without inventing them.

## Runs and resume

Use `experiments/configs/{deepseek,qwen_plus,qwen_open}.yaml`. API configs name
the required environment variable. Re-run the identical command to resume;
changing code, data, config, split, or limit requires a new output directory.
The held-out test requires `--allow-test`.

```bash
uv run falsirag-run --config experiments/configs/deepseek.yaml \
  --output-dir outputs/runs/deepseek_far
uv run falsirag-baselines --config experiments/configs/deepseek.yaml \
  --output-dir outputs/runs/deepseek_baselines
```

Run every ablation with `--ablation minus_typed_conflict`,
`minus_refutation_query`, `minus_boundary_query`, and `minus_typed_revision`.

## Paper

```bash
cd paper
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

The repository vendors unmodified `aaai2027.sty` and `aaai2027.bst` from the
official Author Kit. Replace pending empirical tables only with validated,
complete reports. The paper draft deliberately contains no fabricated score or
IAA value.
