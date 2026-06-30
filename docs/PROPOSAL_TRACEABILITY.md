# Proposal Traceability

| Proposal requirement | Evidence | Status |
|---|---|---|
| Claim graph with dependency edges and source-faithful LLM decomposition | `far/claims.py`, deterministic typed-attribute and no-rewrite regression tests | Implemented; corrected Qwen FAR dev rerun complete, matched comparisons pending |
| Positive typed evidence requirements | `far/evidence_types.py` | Implemented |
| Typed support/refutation/boundary queries | `far/counterfactual.py` | Implemented |
| Typed conflict controls and VeraRAG reuse | enriched graph adapter, strict-NLI formal configs, fingerprinted corpus-entity fallback, real integration tests | Implemented with detector provenance; corrected Qwen FAR dev rerun complete, typed-vs-untyped comparison pending |
| Typed revision and before/after trace | `far/revision.py` | Implemented |
| Six-provider LLM; BM25/dense/FAISS/hybrid/rerank reuse | `far/adapters/`, API configs, adapter tests | Implemented; strict hybrid configs require optional Vera dense install |
| 300--400 benchmark, five categories | 300 rows in `bench/falsirag_bench.jsonl` | Candidate complete |
| In-corpus counter-evidence | `bench/corpus.jsonl`, validator recall 0.91 | Implemented |
| Frozen held-out split/no leakage | `bench/split_manifest.json`, gold-free bundle builder, blind-suite test, `docs/BLIND_TEST_HANDOFF.md` | Technically isolated; external custodian/execution pending |
| Double annotation and IAA | `bench/annotations.py`, `docs/HUMAN_ANNOTATION_PROTOCOL.md` | Tooling and SOP complete; humans pending |
| External FEVER slice | `bench/external/fever_pair_candidates_v1/` | Candidate imported; annotation pending |
| Five baselines | `baselines/` | Implemented; style reproductions labeled |
| Four ablations | `experiments/ablations.py`; untyped wrapper preserves batched graph construction | Implemented; corrected matched bundles pending |
| Six metrics, CI, McNemar | `eval/` | Implemented |
| Checkpoint/signature/result validation | `experiments/runner.py`, validation tests | Implemented |
| Two tables and three figures | `experiments/build_artifacts.py` | Implemented; final inputs pending |
| Reproducible archive, SBOM, fingerprints | build metadata, lockfile, SBOM and release-checksum generators | Implemented; regenerate on submission commit |
| AAAI-27 paper and supplement | `paper/` | Draft complete; empirical cells pending |
| Multi-model main/test results | Versioned DeepSeek V4-Flash, Qwen3.7 Plus (2026-05-26), and local Qwen3.5 9B configs/runners; original Qwen FAR dev completed 60/60 under `d87dfa21...`; invalid old untyped queue preserved at 44/60; corrected FAR rerun completed 60/60 with prediction SHA `992a4cf0...bc96b56`; corrected ablations/baselines continue D:-backed | Original and corrected FAR Qwen diagnostics complete; matched suite completion, cloud credentials/runs, adjudicated labels, and test custodian pending |

“Pending” items are external evidence, not missing code. They must not be marked
complete or replaced with synthetic values.
