# Paper Status

The active paper direction is now a TMLR mechanism-and-boundary study. The
existing anonymous AAAI-27 source is retained as a compilable working draft and
future upgrade path, but the strict AAAI profile receives no further investment
under the single-author/no-human-annotator constraint.

## Post-stop-rule mechanism evidence

The registered WS1 analysis was frozen before inspecting the 226 RAMDocs
both-incorrect cases and then independently recomputed. G-R1 passed. The failure
buckets are retrieval miss 4, conflict undetected 72, conflict detected but
revision wrong 103, answer-set incomplete 35, overfull 12, and format mismatch
0. All four preregistered explanations are not supported: complete-retrieval
items do not restore a FAR advantage, partial-credit set F1 does not reveal a
masked gain, the detected-conflict subset remains inconclusive, and Qwen's 34
positive typed-versus-untyped deltas all occur on changed-revision paths rather
than detection-without-change paths.

The paper must therefore not claim that the effect resides in detection rather
than revision. Its defensible mechanism statement is that revision mediates
both local typed-control gains and larger heterogeneous harms. The evidence is
machine-audited development analysis, not human gold or blind external testing.

G-P estimates only 0.414 exact-McNemar power for the registered 3 x 60 family
study at a +0.078 effect. WS2 is consequently a directional reproduction: a
nonsignificant G-F cannot establish absence, while fewer than 2/3 positive
families or a nonpositive combined effect narrows the claim to Qwen-specific.

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

The tooling enforces G-A, G-K, G-S, family isolation, the 14-day repeat interval,
three-view label sensitivity, the three-system-family matrix, and commit-bound one-shot
test access. The empirical branch is now closed: RAMDocs Round 1 failed G-A, and
the preregistered dev-only Round 2 FAR iteration also failed G-A. This second
failed gate triggers the registered stop rule and downgrades 2+4 to a
typed-conflict-control applicability-boundary analysis, not an end-to-end
advantage claim.

Phase B not run: the cross-family jury, author-blind adjudication, G-K/G-S,
jury rescoring, and model matrix were not run. Held-out not run: neither
FalsiRAG-Bench held-out nor RAMDocs held-out was evaluated. RAMDocs provides
external upstream labels; this is not human inter-annotator agreement,
publication-grade human gold, or an externally held test. The verified evidence
is fingerprinted under `diagnostics/ramdocs_v2/`, with
`gate_a_passed:false`, `stop_rule_triggered:true`, and
`paper_downgrade_required:true`.

The success gate `falsirag-jury-paper-readiness` remains fail-closed by design.
The relevant terminal gate for this branch is now
`falsirag-round2-failure-readiness`, which verifies the failed-G-A evidence
release, required disclosures, and local three-model smoke records.

## Strict AAAI evidence profile (retained, inactive)

The strict profile remains incomplete and is not superseded by 2+4. It still requires two independent
human annotations plus adjudication, a frozen three-model matrix, an externally
held one-shot test, trusted scoring, and independent policy review. The relaxed
profile never upgrades machine labels to human IAA, local development results
to a blind test, or one model to multi-model generality.

The public evidence remains fingerprinted under `diagnostics/solo_v1/`.
`falsirag-solo-release verify` rechecks all 69 files, while
`falsirag-submission-readiness` continues to enforce the strict path.

This profile is not on the active project timeline. It can be reactivated only
if two independent human annotators, independent adjudication, and an external
blind custodian become available; none is being simulated with LLM jury labels.
