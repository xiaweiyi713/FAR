# Proposal Traceability

| Proposal requirement | Evidence | Status |
|---|---|---|
| Claim graph with dependency edges | `far/claims.py`, claim tests | Implemented |
| Positive typed evidence requirements | `far/evidence_types.py` | Implemented |
| Typed support/refutation/boundary queries | `far/counterfactual.py` | Implemented |
| Typed conflict controls and VeraRAG reuse | `far/adapters/conflict.py` | Implemented |
| Typed revision and before/after trace | `far/revision.py` | Implemented |
| Six-provider LLM and retrieval reuse | `far/adapters/` | Implemented; optional Vera install |
| 300--400 benchmark, five categories | 300 rows in `bench/falsirag_bench.jsonl` | Candidate complete |
| In-corpus counter-evidence | `bench/corpus.jsonl`, validator recall 0.93 | Implemented |
| Frozen held-out split/no leakage | `bench/split_manifest.json` | Frozen; external blindness pending |
| Double annotation and IAA | `bench/annotations.py` | Tooling complete; humans pending |
| External FEVER slice | `bench/external/fever_pair_candidates_v1/` | Candidate imported; annotation pending |
| Five baselines | `baselines/` | Implemented; style reproductions labeled |
| Four ablations | `experiments/ablations.py` | Implemented |
| Six metrics, CI, McNemar | `eval/` | Implemented |
| Checkpoint/signature/result validation | `experiments/runner.py`, validation tests | Implemented |
| Two tables and three figures | `experiments/build_artifacts.py` | Implemented; final inputs pending |
| AAAI-27 paper and supplement | `paper/` | Draft complete; empirical cells pending |
| Multi-model main/test results | Configs and runners | Blocked on credentials/compute and test custodian |

“Pending” items are external evidence, not missing code. They must not be marked
complete or replaced with synthetic values.
