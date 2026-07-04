# Paper Status

The anonymous AAAI-27 source uses the official 2027 Author Kit and now supports
two explicitly separate evidence profiles.

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

## Strict AAAI evidence profile

The strict profile remains incomplete. It still requires two independent
human annotations plus adjudication, a frozen three-model matrix, an externally
held one-shot test, trusted scoring, and independent policy review. The relaxed
profile never upgrades machine labels to human IAA, local development results
to a blind test, or one model to multi-model generality.

The public evidence remains fingerprinted under `diagnostics/solo_v1/`.
`falsirag-solo-release verify` rechecks all 69 files, while
`falsirag-submission-readiness` continues to enforce the strict path.
