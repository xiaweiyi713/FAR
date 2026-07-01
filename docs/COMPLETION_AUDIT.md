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
| Automatic labeling assistance | Qwen2.5 machine preannotations 300/300 with 1 fallback after retry; Label Studio export 300/300 predictions; deterministic weak labels generated for 300/300 rows with 211 non-abstained signals; machine-label audit shared 300/300 rows and identified 127 priority-review samples | Implemented, non-gold | Preannotations, weak labels, and machine-machine agreement remain `publication_gold: false` |
| Independent annotation and IAA | Blind packets, compiler, adjudicator, human annotation protocol | External work pending | Two independent completed files, adjudication, and reported kappa |
| External FEVER slice | Fingerprinted candidate import | Candidate complete | Human annotation and separate reporting |
| Six transparent baselines, including CounterRefine-style closest-neighbor control | `baselines/` | Implemented | Complete matched prediction bundles; current remote suite has the original five, so run CounterRefine separately before reports-only merge |
| Four component ablations | `experiments/ablations.py`; batched-detector parity regression; corrected FAR vs `minus_typed_conflict` Qwen dev pair both complete 60/60 with zero errors and validated locally | Core typed-vs-untyped dev diagnostic complete; remaining ablations running | Complete the remaining three ablation bundles and final suite reports |
| Metrics, confidence intervals, McNemar | `eval/`; reports bind benchmark-manifest readiness and annotation statuses | Implemented | Validated complete reports on frozen, adjudicated predictions |
| Versioned model matrix | DeepSeek V4-Flash, Qwen3.7 Plus 2026-05-26, Qwen3.5 9B; local digest recorded; corrected Qwen FAR rerun completed 60/60 with zero errors and prediction SHA `992a4cf027db5491feef2a57210d8a9395be61798c0ff84b29760d495bc96b56`; corrected `minus_typed_conflict` completed 60/60 with prediction SHA `26e6ae372d54a8dea30dd8a892a68a4ba425d91bf341366b21ce309d6d928658`; both passed pre/post evaluation validation. FAR report SHA `3c5b5248544a1b24aa7ff294ed4cd578b7c4ee946e38e8d52f75028e354e2fd5`; untyped paired report SHA `236b9d71bbdfa218e693bdcebd329b0af53bd97d01315e236cf257e7355468bb`; untyped validation SHA `8ae0fa03ff184b8a8e6a838288dcdd976fa155891476297acac93bf1894d39db`. The paired dev diagnostic favors typed control: answer correctness +0.0783, revision accuracy +0.2167, revision action +0.3667, typed conflict F1 +0.4204 for FAR over untyped. Cloud-config preflight checks pinned provider/model names, env-var secrets, dense/NLI requirements, and output-root safety; D:-backed cloud-suite starter avoids visible key logging and refuses GPU-overlapping local Qwen runs by default; remaining ablations/baselines still running | Corrected Qwen core typed-vs-untyped diagnostic validated; cloud run preflight/starter implemented; remaining matched suite in progress | Complete remaining matched Qwen ablations/baselines and reports; rotated cloud credentials/runs; exact provider provenance |
| Windows GPU execution | D:-backed Ollama/HF caches and outputs; CUDA and Qwen end-to-end smokes | Host gate passed | Recheck free space and environment before each formal run |
| Externally blind test | Gold-free bundle, unscored runner, external handoff protocol; 58-input/175-document technical dry run structurally audited with frozen manifest/input/corpus fingerprints | Technical path and full dry run implemented | Rebuild from adjudicated data, then independent custodian and one-shot returned predictions |
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
