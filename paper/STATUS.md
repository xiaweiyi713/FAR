# Paper Status

The anonymous AAAI-27 source uses the official 2027 Author Kit and now tracks
three explicitly separate evidence profiles.

## Relaxed single-author machine-audited profile

This profile is complete and checked by `falsirag-solo-paper-readiness`.
The main paper contains the full 60-item Qwen3.5 9B development comparison,
all four component ablations, paired inference for typed versus untyped FAR,
and the frozen FEVER binary transfer result. The paper claim is deliberately
narrow:

> On a construction-derived, machine-audited Qwen development diagnostic,
> typed conflict control improves over a matched untyped ablation.

The gate requires the paper to disclose that removing refutation or boundary
queries does not reduce answer correctness, while removing typed revision
raises answer correctness and eliminates revision behavior. It also requires
the non-human-gold, non-blind, single-model, and FEVER-null-transfer limits.
The tracked status is in `reports/solo_paper_readiness.{md,json}`.

## Preregistered 2+4 single-author evidence profile

This profile replaces the unavailable human-annotation gate only for a separately
named claim tier. It combines RAMDocs external upstream labels with a DeepSeek/GLM/Meta
cross-family LLM jury and author-blind adjudication. It is never described as human
inter-annotator agreement, publication-grade human gold, or an externally held test.

The tooling now enforces G-A, G-K, G-S, family isolation, the 14-day repeat interval,
three-view label sensitivity, the three-system-family matrix, and commit-bound one-shot
test access. Evidence is not complete: RAMDocs Round 1 failed G-A, and the preregistered
dev-only Round 2 FAR iteration is still running. Phase B, jury gold, the model matrix,
and held-out evaluation therefore remain blocked.

The final gate is `falsirag-jury-paper-readiness`; it remains fail-closed until every
required source artifact can be recomputed from the fingerprinted 2+4 evidence release.

## Strict AAAI evidence profile

The strict profile remains incomplete and is not superseded by 2+4. It still requires two independent
human annotations plus adjudication, a frozen three-model matrix, an externally
held one-shot test, trusted scoring, and independent policy review. The relaxed
profile never upgrades machine labels to human IAA, local development results
to a blind test, or one model to multi-model generality.

The public evidence remains fingerprinted under `diagnostics/solo_v1/`.
`falsirag-solo-release verify` rechecks all 69 files, while
`falsirag-submission-readiness` continues to enforce the strict path.
