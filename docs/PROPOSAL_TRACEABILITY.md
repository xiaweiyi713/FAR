# Proposal Traceability

| Proposal requirement | Evidence | Status |
|---|---|---|
| Claim graph with dependency edges | `far/claims.py`, claim tests | Implemented |
| Positive typed evidence requirements | `far/evidence_types.py` | Implemented |
| Typed support/refutation/boundary queries | `far/counterfactual.py` | Implemented |
| Typed conflict controls and VeraRAG reuse | enriched graph adapter, strict-NLI formal configs, real integration tests | Implemented with detector provenance |
| Typed revision and before/after trace | `far/revision.py` | Implemented |
| Six-provider LLM; BM25/dense/FAISS/hybrid/rerank reuse | `far/adapters/`, API configs, adapter tests | Implemented; strict hybrid configs require optional Vera dense install |
| 300--400 benchmark, five categories | 300 rows in `bench/falsirag_bench.jsonl` | Candidate complete |
| In-corpus counter-evidence | `bench/corpus.jsonl`, validator recall 0.91 | Implemented |
| Frozen held-out split/no leakage | `bench/split_manifest.json`, gold-free bundle builder, blind-suite test | Technically isolated; external custodian/execution pending |
| Double annotation and IAA | `bench/annotations.py` | Tooling complete; humans pending |
| External FEVER slice | `bench/external/fever_pair_candidates_v1/` | Candidate imported; annotation pending |
| Five baselines | `baselines/` | Implemented; style reproductions labeled |
| Four ablations | `experiments/ablations.py` | Implemented |
| Six metrics, CI, McNemar | `eval/` | Implemented |
| Checkpoint/signature/result validation | `experiments/runner.py`, validation tests | Implemented |
| Two tables and three figures | `experiments/build_artifacts.py` | Implemented; final inputs pending |
| Reproducible archive and SBOM | build metadata, lockfile, `experiments/generate_sbom.py` | Implemented; regenerate on submission commit |
| AAAI-27 paper and supplement | `paper/` | Draft complete; empirical cells pending |
| Multi-model main/test results | Versioned DeepSeek V4-Flash, Qwen3.7 Plus (2026-05-26), and local Qwen3.5 9B configs and runners; D:-backed, thinking-disabled, per-sample-unload Qwen pilot verified and clean full dev suite queued | Local runtime ready; cloud credentials, completed formal runs, and test custodian pending |

“Pending” items are external evidence, not missing code. They must not be marked
complete or replaced with synthetic values.
