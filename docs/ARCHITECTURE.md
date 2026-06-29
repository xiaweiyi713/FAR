# Architecture

The package owns its research semantics and treats VeraRAG as an optional
implementation provider. This prevents the paper method from depending on the
historical `src.*` layout.

1. `far/claims.py` decomposes the initial answer and validates a dependency DAG.
2. `far/evidence_types.py` assigns temporal, entity, numerical, causal,
   source-reliability, definition, and counter-evidence requirements.
3. `far/counterfactual.py` generates exactly the enabled support, refutation,
   and boundary query families. Typed and untyped modes are separate.
4. `far/adapters/retrieval.py` retrieves evidence; `conflict.py` returns typed
   control signals through offline rules or VeraRAG's conflict graph. The Vera
   adapter deterministically enriches both sides with entities/numbers/times,
   preserves Vera resolver strategies, and labels any high-precision FAR rule
   used when the graph has no edge.
5. `far/revision.py` selects a deterministic action by conflict type, then may
   ask the configured model to realize that action without changing it.
6. `far/pipeline.py` records every intermediate object in `FARResult`.

VeraRAG integration is centralized in `far/adapters/`: the six-provider LLM
client; concrete BM25, dense, FAISS, hybrid RRF, and CrossEncoder-reranked
retrieval builders; and the layered conflict graph. Hybrid runs fail if VeraRAG
silently loses its dense component unless a diagnostic config explicitly sets
`allow_dense_fallback: true`. Formal configs likewise require the declared NLI
model to load; rule-only silent degradation is rejected. Import failures give
installation guidance. No
benchmark gold metadata is read by normal detectors. Train/dev runners use the
research archive, but test runners exclusively parse the five-field operational
`test_inputs.jsonl`; they can run from a gold-free bundle in which construction
metadata and source dependency IDs are also removed. Oracle evidence metadata
exists only behind an explicit test/demo detector flag.

Experiment runners hash configuration, the split-specific operational input,
corpus, and all Python implementation files. Checkpoints are append-only and
fsynced per sample. Resumption is allowed only when the signature matches.
