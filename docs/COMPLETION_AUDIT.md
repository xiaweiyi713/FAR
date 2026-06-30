# Project Completion Audit

This file separates implemented research infrastructure from evidence that can
only exist after real annotation and experiments. It is the acceptance checklist
for `PROJECT_PROPOSAL.md`; generated or diagnostic values must not be used to
close an empirical gate.

| Proposal obligation | Current evidence | State | Evidence required to close |
|---|---|---|---|
| Claim graph, dependency, and source-faithfulness validation | `far/claims.py`; typed-attribute/no-rewrite tests | Implemented | Full suite passes; rerun matched dev after the dev-derived correction |
| Typed evidence requirements | `far/evidence_types.py` | Implemented | Assignment tests pass |
| Support/refutation/boundary query protocol | `far/counterfactual.py` | Implemented | Three-family schema and fallback tests pass |
| Typed VeraRAG conflict control | `far/adapters/conflict.py`, pinned NLI config, corpus-entity metadata path, detector provenance | Implemented | Graph/NLI/lexicon integration tests pass; rerun matched dev after the dev-derived correction |
| Typed revision and before/after trace | `far/revision.py` | Implemented | Action/trace tests pass |
| VeraRAG LLM and retrieval reuse | `far/adapters/`, editable local dependency | Implemented | Six-provider and BM25/dense/FAISS/hybrid/rerank adapter tests pass |
| 300--400 candidate benchmark in five classes | 300 rows, 60 per class | Candidate complete | Benchmark validator and fingerprints pass |
| Counter-evidence in the corpus | Frozen corpus; lexical recall@10 = 0.91 | Construction gate passed | Validator report remains bound to frozen corpus |
| No dependency-group split leakage | `bench/split_manifest.json` (182/60/58) | Implemented | Validator reports zero leakage |
| Automatic labeling assistance | Qwen2.5 machine preannotations 300/300 with 1 fallback after retry; Label Studio export 300/300 predictions | Implemented, non-gold | Preannotations remain `publication_gold: false` |
| Independent annotation and IAA | Blind packets, compiler, adjudicator | External work pending | Two independent completed files, adjudication, and reported kappa |
| External FEVER slice | Fingerprinted candidate import | Candidate complete | Human annotation and separate reporting |
| Five transparent baselines | `baselines/` | Implemented | Complete matched prediction bundles |
| Four component ablations | `experiments/ablations.py`; batched-detector parity regression | Implemented | Fresh complete paired bundles, especially corrected typed vs untyped |
| Metrics, confidence intervals, McNemar | `eval/`; reports bind benchmark-manifest readiness and annotation statuses | Implemented | Validated complete reports on frozen, adjudicated predictions |
| Versioned model matrix | DeepSeek V4-Flash, Qwen3.7 Plus 2026-05-26, Qwen3.5 9B; local digest recorded; Qwen FAR dev completed 60/60 with run/prediction hashes and `publication_ready: false`; matched suite running | Qwen diagnostic in progress; clean, memory-bounded runtime verified | Complete matched Qwen suite and corrected-code rerun; cloud credentials/runs; exact provider provenance |
| Windows GPU execution | D:-backed Ollama/HF caches and outputs; CUDA and Qwen end-to-end smokes | Host gate passed | Recheck free space and environment before each formal run |
| Externally blind test | Gold-free bundle and unscored runner | Technical path implemented | Independent custodian and one-shot returned predictions |
| Tables and figures | Artifact builder and diagnostic smoke artifacts | Implemented, final inputs pending | Build only from validated complete reports |
| AAAI-27 paper and supplement | Official template, paper sources, filled checklist | Draft complete | Replace pending cells, add final compute/annotation details, human policy review |
| Reproducible package | Lockfile, wheel/sdist, CycloneDX SBOM, release checksums, redacting secret scanner, `scripts/release_check.sh` | Implemented | Run the single release gate on the submission commit after final evidence is frozen |

## Completion rule

The project is submission-complete only when every row above is either closed by
its named evidence or explicitly removed from the paper's claims. In particular:

1. LLM preannotations may reduce reviewer effort but cannot be reported as two
   independent human annotations or Cohen's kappa.
2. Local access to the test labels is not an externally held blind test.
3. Smoke, partial, train, and development runs cannot populate the main test
   table.
4. The typed-control contribution survives only if the preregistered paired
   typed-versus-untyped comparison supports it; otherwise the paper must report
   the diagnostic or negative result.
5. `paper/aaai27/ReproducibilityChecklist.tex` must be re-audited after final
   runs so every `partial` or `no` answer remains truthful.
