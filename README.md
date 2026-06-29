# FAR: Falsification-Augmented Retrieval

FAR asks a retrieval-augmented agent a deliberately uncomfortable question:
**what evidence would make its current answer wrong?** It decomposes an initial
answer into a claim graph, assigns typed evidence needs, issues support,
refutation, and boundary queries, detects typed conflicts, and applies a
type-specific revision with a claim-level audit trace.

The repository is a complete research scaffold for the AAAI-27 project in
[`PROJECT_PROPOSAL.md`](PROJECT_PROPOSAL.md). It includes the method, a
300-candidate FalsiRAG-Bench build, annotation/adjudication tools, five baselines,
four ablations, statistical inference, checkpointed runners, paper sources, and
artifact validation. It does **not** claim completed human annotation or final
multi-model results; those require independent annotators and model credentials.

## Quickstart

```bash
uv sync --extra dev --extra eval
uv pip install --no-deps -e /Users/xuwenyao/VeraRAG  # optional adapters
uv run python examples/offline_demo.py
uv run falsirag-validate-bench
uv run python -m pytest
```

For the formal hybrid+dense+reranker configurations, install VeraRAG's dense
extra instead: `uv pip install -e '/Users/xuwenyao/VeraRAG[dense]'`. The formal
configs fail closed if dense retrieval is unavailable, so a BM25 fallback can
never be mislabeled as a hybrid result.

Run a balanced, dependency-free diagnostic slice:

```bash
uv run falsirag-suite \
  --config experiments/configs/offline_smoke.yaml \
  --output-dir outputs/smoke_suite \
  --limit 10 \
  --baseline vanilla_rag \
  --ablation minus_typed_conflict \
  --resamples 200
```

The `test` split is rejected unless `--allow-test` is supplied. Limited runs are
marked `partial`, and any tables/figures built from them are marked
`diagnostic_only`.

## Method outputs

`FARPipeline.run(question, initial_answer)` returns:

- a validated acyclic claim graph;
- positive typed evidence requirements for every claim;
- support/refutation/boundary query and retrieval traces;
- a claim-to-evidence map and typed conflicts;
- the revised answer and explicit before/after revision trace.

The core runs offline with deterministic rules. Configured LLMs participate in
claim decomposition, typed query generation, and revision realization. Invalid
structured model outputs fall back to the deterministic protocol; provider
failures remain visible.

The VeraRAG adapter exposes its six providers (OpenAI, Anthropic, Ollama,
DashScope, ZhipuAI, and DeepSeek) plus BM25, dense, FAISS, hybrid RRF, and an
optional CrossEncoder reranker. The checked-in API configs use the same strict
multilingual BGE hybrid+rereanking stack for paired model comparisons.

## Benchmark status

FalsiRAG-Bench v0.1.0-candidate contains five balanced categories (60 each),
175 corpus documents, frozen source-document-group splits, and in-corpus
counter-evidence. The validator currently reports zero cross-split dependency
leakage and 0.93 lexical counter-evidence recall@10 across the three query
families. This is a construction check, not a model result.

All 300 labels are `machine_seeded`. `bench/manifest.json` therefore sets
`publication_ready: false`. Promotion requires two independent annotations,
adjudication, reported Cohen's kappa, and an externally held blind test. See
[`bench/CARD.md`](bench/CARD.md).

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): components and VeraRAG boundary
- [`docs/REPRODUCING.md`](docs/REPRODUCING.md): benchmark, runs, resume, and paper
- [`docs/EVALUATION.md`](docs/EVALUATION.md): metric and inference definitions
- [`docs/AUTO_ANNOTATION.md`](docs/AUTO_ANNOTATION.md): DeepSeek/LLM preannotation workflow
- [`docs/EXPERIMENT_PLAN.md`](docs/EXPERIMENT_PLAN.md): model/baseline/ablation matrix
- [`docs/PROPOSAL_TRACEABILITY.md`](docs/PROPOSAL_TRACEABILITY.md): proposal-to-evidence audit
- [`paper/main.tex`](paper/main.tex): anonymous AAAI-27 draft using the official kit

## License

FAR code and controlled synthetic summaries are MIT licensed. VeraRAG is reused
through optional adapters under its MIT license. Upstream datasets and source
materials retain their own terms; the separately imported FEVER candidate slice
records CC-BY-SA-3.0 and GPL-3.0 provenance.
