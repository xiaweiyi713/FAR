# Paper Status

The active paper direction is now a TMLR mechanism-and-boundary study. The
existing anonymous AAAI-27 source is retained as a compilable working draft and
future upgrade path, but the strict AAAI profile receives no further investment
under the single-author/no-human-annotator constraint.

## Capability-aware cross-method result

The active paper is now led by the preregistered P2-B stage trace map rather
than a causal ``detection is not the bottleneck'' claim. A schema-only audit
showed that six of eight RAMDocs Round 1 methods lack comparable typed detection,
revision-action, and claim-level revision traces. The frozen analysis therefore
uses only retrieved evidence IDs plus shared initial/final answers across all
eight methods and reserves detection/action detail for the two FAR arms.

The verified 8-method $\times$ 350-item map passes both registered descriptive
criteria. Post-retrieval changed-wrong errors exceed retrieval misses for 8/8
methods. The pooled sample-cluster difference is +0.3914 with 95% bootstrap
interval [+0.3554,+0.4275]. Two items lack upstream correct-document labels and
are retained as retrieval-unscorable. The report and verifier are tracked at
`reports/stage_trace_map.{json,md}` and record zero model calls,
`causal_attribution:false`, `publication_gold:false`, and `test_accessed:false`.

The maximum licensed cross-method claim is that errors concentrate after
retrieval and observable textual answer transformation. It does not establish
that detection is sufficient, identify an action/revision implementation gap,
or estimate a causal oracle ladder. FAR-specific traces remain a narrower case
study of revision-mediated heterogeneous gains and harms.

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

WS2 is now complete and independently verified. Mistral, Gemma, and Llama have
positive typed-minus-untyped answer differences of +0.0528, +0.0673, and
+0.0735. The combined difference is +0.0645 over 180 pairs; stratified exact
McNemar counts are 31 typed-only versus 9 untyped-only successes
(`p=0.000680`), and the family-cluster bootstrap 95% interval is
[+0.0528,+0.0735]. G-F passes with 3/3 positive directions. These are local,
machine-audited development results under the preregistered
`directional_reproduction` claim level, not human gold, blind validation, or a
restored end-to-end superiority claim.

WS3 is now complete and independently verified as
`directional_boundary_mapping`. WikiContradict and Google CONFLICTS are two
public development diagnostics, not held-out/test, human IAA, publication gold,
or external blind testing. The verified release contains 600 formal pipeline
predictions plus 20 calibration predictions, with `gate_b_complete=true`,
`publication_gold=false`, `human_iaa=false`, and `test_accessed=false`.
Overall typed-minus-untyped boundary-score differences are near null:
WikiContradict `+0.0033` with 95% CI `[-0.0067,+0.0167]`, and Google CONFLICTS
`-0.0007` with 95% CI `[-0.0271,+0.0262]`; both Holm-adjusted McNemar values
are `1.0`. The preregistered Google outdated-information subgroup is positive
(`+0.0040`) and the no-conflict subgroup stays within the safety margin
(`-0.0042 >= -0.03`), while the Wiki explicit/implicit predictions are
contradicted. The paper therefore uses WS3 as a weak A-line boundary result:
there are identifiable, narrow public-dev conditions where typed control can
help, but no global external transfer or end-to-end superiority claim.

The active result-integration checklist is
`reports/tmlr_result_integration_matrix.md`. It maps every WS2/WS3 outcome
combination onto the A/B/C paper lines from the roadmap and fixes the section
edits allowed after verified releases exist. WS2 closes the C-line
family-inconsistency branch; WS3 selects only a weak A-line
mechanism-and-boundary interpretation because one preregistered external
condition is directionally positive without a no-conflict safety violation, but
both dataset-level comparisons are near null. The draft may include the
verified WS2 and WS3 releases only with the public-dev, machine-audited,
low-power caveats.

P5 is now complete and integrated as registered negative component evidence.
Across 350 upstream-labelled RAMDocs development items, full FAR obtains 0.3057
exact match, the aggressiveness-matched removal of typed revision obtains
0.3086, and flat claims obtain 0.3057. H3 remains `uncertain` because the 90%
interval `[-0.0229,+0.0171]` crosses the registered equivalence boundary; H5 is
`equivalent` because `[-0.0057,+0.0057]` lies wholly inside it. The paper must
not promote H3 to equivalence or H5 to a general no-effect claim.

P6-M is also complete and integrated as a negative ontology-stability audit.
J1/J2/J3 are dual-view stable on 50/217, 88/217, and 24/217 items. Only 15/217
items reach stable machine consensus and 202 are contested; one frozen stratum
has no consensus, so the registered association is not estimable. This is
machine-panel sensitivity evidence, not population mappability, human IAA,
adjudicated gold, or H4 confirmation. It closes the accepted no-human profile
without filling any human reviewer or adjudicator role.

P11 adds an explicitly post-hoc revision-delta metric audit over the already
frozen 60-item predictions; it makes zero model calls and never accesses the
test split. Whole-answer soft F1 can reward an unchanged erroneous answer when
the construction reference changes only a small token span. The new raw delta
F1 scores only the token additions/removals required by that reference, while
typed delta F1 additionally requires the declared revision action to match.
FAR obtains raw/typed delta F1 `0.145/0.096`; minus typed conflict obtains
`0.093/0`, and minus typed revision obtains `0.072/0`. However CRAG-style and
Vanilla raw delta F1 are higher (`0.307/0.264`), and removing refutation queries
raises raw delta F1 to `0.194`. The paper therefore treats P11 as lexical
edit-fidelity and negative/mixed component evidence, not semantic correctness,
human validation, or a new superiority claim.

The same model-free audit was then applied to the frozen WS2 family predictions.
Mistral, Gemma, and Llama show raw typed-minus-untyped delta differences of
`+0.0133/+0.0524/+0.0536`; the combined difference is `+0.0398` with a
family-cluster 95% interval `[+0.0133,+0.0536]`. Typed delta is also 3/3
positive, combined `+0.0816` `[+0.0353,+0.1137]`. This is explicitly post-hoc
transport sensitivity rather than a preregistered WS2 endpoint, and it does not
erase the Qwen broad-baseline ranking or license semantic/general superiority.

The active text now also has a reproducible TMLR submission build path:
`scripts/build_tmlr_paper.sh` takes the scientific body from `paper/main.tex`,
wraps it in the unmodified official TMLR anonymous-submission style pinned at
upstream commit `7bf90efe3a0debbba703c05c43f3ff7e4d4a2992`, and writes only ignored
artifacts under `paper/build/tmlr/`. The AAAI source remains an inactive upgrade
artifact; it is no longer the only compilable shell for the active paper.
The same builder inserts `paper/appendix.tex` before the references. That active
appendix carries the claim--evidence ledger, registered WS1 details, G-P power
limits, A/B/C outcome rules, reproducibility contract, and label/test boundary.
`paper/supplement.tex` is retained only as the legacy AAAI upgrade-path
supplement and is not the active TMLR evidence appendix.

The active route now also has a separate fail-closed release command,
`scripts/solo_paper_release_check.sh`. On a clean commit it reruns the public
diagnostic and package checks, builds the TMLR artifact, rejects layout overflow
or unresolved references, and fingerprints a nine-artifact `solo-paper`
profile containing the PDF and its source lock. It intentionally consumes no
strict submission evidence and cannot be used to claim human review or AAAI
readiness.

That command now also emits a deterministic portable
`far-solo-paper-release.tar.gz`. It requires a byte-identical second pack and
then runs the paired standard-library-only verifier in Python isolated mode
over its byte-identical embedded copy, the nine-artifact checksums, TMLR source
lock, P5/P6-M boundaries, package fingerprints, and claim flags. The verifier
requires no FAR checkout or installation. The archive is a transferable
machine-audited paper release, not human validation or submission itself.

The main text now contains a dedicated mechanism-interpretation section. It
frames retrieval, type mapping, detection, action selection, and revision as an
opportunity chain rather than a monotone pipeline; explains why the local Qwen
signal and RAMDocs nulls can coexist without claiming that construct alignment
is the proven sole cause; and marks selective revision as an unevaluated future
design hypothesis. The verified WS2 result establishes directional family
recurrence; the verified WS3 result now adds a public-dev boundary matrix with
near-null global transfer and a narrow positive outdated-information condition.

## Relaxed single-author machine-audited profile

This profile is complete and checked by `falsirag-solo-paper-readiness`.
The main paper contains the full 60-item Qwen3.5 9B development comparison,
all four component ablations, paired inference for typed versus untyped FAR,
and the frozen FEVER binary transfer result. The paper claim is deliberately
narrow:

> Across eight RAMDocs development methods, errors concentrate after retrieved
> evidence and answer transformation; FAR shows a narrower machine-audited
> typed-control signal whose transport and ontology stability are explicitly
> bounded.

The gate requires the paper to disclose that removing refutation or boundary
queries does not reduce answer correctness, while removing typed revision
raises answer correctness and eliminates revision behavior. It also requires
the registered P5 verdicts, the P6-M 15/217 negative result, and the
non-human-gold, non-blind, single-model, and FEVER-null-transfer limits.
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
