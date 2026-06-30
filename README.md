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
uv run falsirag-generate-sbom --check
uv run python -m pytest
```

For formal hybrid+dense+reranker+NLI configurations, run
`uv sync --extra experiment` and install the local VeraRAG code with
`uv pip install --no-deps -e /Users/xuwenyao/VeraRAG`. The formal configs fail
closed if dense retrieval or NLI is unavailable, so a degraded run cannot be
mislabeled as the configured method.

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

After installing the `experiment` extra and VeraRAG, validate the exact pinned
formal retrieval/NLI stack without API calls using
`experiments/configs/formal_stack_smoke.yaml` (see the reproduction guide).

The `test` split is rejected unless `--allow-test` is supplied. Limited runs are
marked `partial`, and any tables/figures built from them are marked
`diagnostic_only`. Full runs remain diagnostic while the benchmark manifest is
not publication-ready or scored rows have not been adjudicated.

For final test execution, first use `falsirag-build-blind-bundle`; test runners
then consume only sanitized operational inputs and emit unscored prediction
manifests. They do not load local gold or build result artifacts. The trusted
scoring handoff is documented in `docs/REPRODUCING.md`.

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
optional CrossEncoder reranker. The checked-in API configs use the same pinned
BGE hybrid+rereanking stack and required NLI conflict layer for
paired model comparisons. Dense or NLI degradation aborts formal runs rather
than changing the method silently.

## Benchmark status

FalsiRAG-Bench v0.2.0-candidate contains five balanced categories (60 each),
175 corpus documents, frozen source-document-group splits, and in-corpus
counter-evidence. The validator currently reports zero cross-split dependency
leakage and 0.91 lexical counter-evidence recall@10 across the three query
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
- [`docs/DEVELOPMENT_LOG.md`](docs/DEVELOPMENT_LOG.md): frozen dev-only tuning decisions and hashes
- [`docs/PROPOSAL_TRACEABILITY.md`](docs/PROPOSAL_TRACEABILITY.md): proposal-to-evidence audit
- [`docs/COMPLETION_AUDIT.md`](docs/COMPLETION_AUDIT.md): requirement-by-requirement submission gates
- [`paper/main.tex`](paper/main.tex): anonymous AAAI-27 draft using the official kit
- [`paper/aaai27/ReproducibilityChecklist.tex`](paper/aaai27/ReproducibilityChecklist.tex): evidence-based AAAI checklist

## License

FAR code and controlled synthetic summaries are MIT licensed. VeraRAG is reused
through optional adapters under its MIT license. Upstream datasets and source
materials retain their own terms; the separately imported FEVER candidate slice
records CC-BY-SA-3.0 and GPL-3.0 provenance.
