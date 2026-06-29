# Reproduction Guide

## Environment contract

FAR declares Python 3.10+ support in `pyproject.toml`. The checked-in
`.python-version` pins the local development environment to Python 3.12, but
the static type/lint contract targets Python 3.10 so the artifact does not
silently drift beyond the proposal's compatibility claim. Use:

```bash
uv run ruff check .
uv run mypy far bench baselines eval experiments tests
uv run python -m pytest
```

before publishing or replacing paper numbers.

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

## Automatic preannotation

When humans are not yet available, generate non-gold LLM suggestions from a
blind packet:

```bash
export DEEPSEEK_API_KEY="<paste key here>"
uv run falsirag-auto-annotate generate \
  --packet-dir outputs/annotations \
  --output-dir outputs/deepseek_preannotations \
  --config experiments/configs/deepseek.yaml \
  --preannotator-id deepseek_chat_v1
```

The output is review aid only. It deliberately cannot satisfy the independent
annotation, adjudication, or Cohen's kappa publication gates. See
[`docs/AUTO_ANNOTATION.md`](AUTO_ANNOTATION.md).

To create an editable human review draft from preannotations:

```bash
uv run falsirag-auto-annotate draft \
  --packet-dir outputs/annotations \
  --preannotation-dir outputs/deepseek_preannotations \
  --output-dir outputs/deepseek_review_draft \
  --reviewer-id annotator_a
```

The compiler rejects unreviewed machine drafts until `human_reviewed` is set to
`true` by a human reviewer.

## Runs and resume

Use `experiments/configs/{deepseek,qwen_plus,qwen_open}.yaml`. API configs name
the required environment variable. Re-run the identical command to resume;
changing code, data, config, split, or limit requires a new output directory.
The held-out test requires `--allow-test`.

Recommended: run one complete suite for a config. This executes FAR, selected
baselines, selected ablations, evaluation, result validation, and table/figure
artifact generation:

```bash
uv run falsirag-suite \
  --config experiments/configs/deepseek.yaml \
  --output-dir outputs/suites/deepseek_dev \
  --split dev \
  --baseline vanilla_rag \
  --baseline multi_query_rag \
  --ablation minus_typed_conflict \
  --ablation minus_refutation_query
```

Omit the repeated `--baseline` and `--ablation` flags to run all five baselines
and all four FAR ablations. Use `--limit` only for diagnostic smoke runs; suite
manifests and built artifacts then remain marked `diagnostic_only`.

For targeted debugging, run individual components:

```bash
uv run falsirag-run --config experiments/configs/deepseek.yaml \
  --output-dir outputs/runs/deepseek_far
uv run falsirag-baselines --config experiments/configs/deepseek.yaml \
  --output-dir outputs/runs/deepseek_baselines
```

Run every ablation with `--ablation minus_typed_conflict`,
`minus_refutation_query`, `minus_boundary_query`, and `minus_typed_revision`.

To rebuild only the paper-facing tables and figures from already validated
reports, install the `eval` extra and call the artifact builder directly:

```bash
uv sync --extra eval
uv run falsirag-build-artifacts \
  --report far=outputs/evaluations/far/report.json \
  --report vanilla=outputs/evaluations/vanilla_rag/report.json \
  --report minus_typed_conflict=outputs/evaluations/minus_typed_conflict/report.json \
  --prediction far=outputs/runs/far/predictions.jsonl \
  --output-dir outputs/artifacts
```

## Paper

```bash
cd paper
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

The repository vendors unmodified `aaai2027.sty` and `aaai2027.bst` from the
official Author Kit. Replace pending empirical tables only with validated,
complete reports. The paper draft deliberately contains no fabricated score or
IAA value.
