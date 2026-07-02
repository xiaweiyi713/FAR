# Proposal Traceability

| Proposal requirement | Evidence | Status |
|---|---|---|
| Claim graph with dependency edges and source-faithful LLM decomposition | `far/claims.py`, deterministic typed-attribute and no-rewrite regression tests | Implemented; corrected Qwen FAR dev rerun complete and validated |
| Positive typed evidence requirements | `far/evidence_types.py` | Implemented |
| Typed support/refutation/boundary queries | `far/counterfactual.py` | Implemented |
| Typed conflict controls and VeraRAG reuse | enriched graph adapter, strict-NLI formal configs, fingerprinted corpus-entity fallback, real integration tests; corrected Qwen FAR vs `minus_typed_conflict` paired dev report | Implemented with detector provenance; typed-vs-untyped dev diagnostic favors typed control but remains `publication_ready:false` |
| Typed revision and before/after trace | `far/revision.py` | Implemented |
| Six-provider LLM; BM25/dense/FAISS/hybrid/rerank reuse | `far/adapters/`, API configs, adapter tests | Implemented; strict hybrid configs require optional Vera dense install |
| 300--400 benchmark, five categories | 300 rows in `bench/falsirag_bench.jsonl` | Candidate complete |
| In-corpus counter-evidence | `bench/corpus.jsonl`, validator recall 0.91 | Implemented |
| Frozen held-out split/no leakage | `bench/split_manifest.json`, gold-free bundle builder, blind-suite test, `docs/BLIND_TEST_HANDOFF.md` | Technically isolated; external custodian/execution pending |
| Double annotation and IAA | Reviewer-bound Label Studio exports/imports, atomic installer, raw-evidence freezer/revalidator in `bench/annotations.py`, `docs/HUMAN_ANNOTATION_PROTOCOL.md` | Tamper-evident tooling and SOP complete; humans pending |
| External FEVER slice | `bench/external/fever_pair_candidates_v1/` | Candidate imported; annotation pending |
| Six baselines, including closest-neighbor CounterRefine control | `baselines/`; ignored local pull `outputs/remote_qwen_six_baseline_suite/` | Implemented; CRAG, Self-RAG, and CounterRefine style reproductions explicitly labeled; Qwen dev six-baseline diagnostic complete/validated, still `publication_ready:false` |
| Four ablations | `experiments/ablations.py`; untyped wrapper preserves batched graph construction; complete local Qwen dev ablation reports in `outputs/remote_qwen_ablation_matrix/` | All four corrected Qwen dev ablations complete/validated; typed-vs-untyped supports typed control, other component effects are mixed and must be rechecked on adjudicated gold |
| Six metrics, CI, McNemar | `eval/` | Implemented |
| Checkpoint/signature/result validation | `experiments/runner.py`, validation tests; identities bind clean Git revision and validators recompute signatures | Implemented |
| Two tables and three figures | `experiments/build_artifacts.py` | Implemented; final inputs pending |
| Reproducible archive, SBOM, fingerprints | build metadata, lockfile, SBOM and release-checksum generators | Implemented; regenerate on submission commit |
| AAAI-27 paper and supplement | `paper/` | Draft complete; empirical cells pending |
| Multi-model main/test results | Versioned DeepSeek V4-Flash, Qwen3.7 Plus (2026-05-26), and local Qwen3.5 9B configs/runners; corrected FAR rerun prediction SHA `992a4cf0...bc96b56`; corrected untyped prediction SHA `26e6ae37...28658`; CounterRefine prediction SHA `483f08ec...b8c57`; suite manifest SHA `dccd854c...c4467` | Qwen dev six-baseline + four-ablation diagnostic complete; cloud credentials/runs, adjudicated labels, and test custodian pending |
| Final external acceptance chain | `falsirag-score-blind-return`, `falsirag-submission-readiness`, `submission/*.template.json`, `docs/EXTERNAL_ACTION_PACKET.md` | Implemented and tested end to end with non-publication fixtures; real external evidence pending |

“Pending” items are external evidence, not missing code. They must not be marked
complete or replaced with synthetic values.
