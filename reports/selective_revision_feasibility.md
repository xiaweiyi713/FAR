# FAR Selective-Revision Feasibility Audit

> Post-hoc, reference-dependent development diagnostic over frozen outputs. No model calls, held-out/test access, human review, semantic judgment, deployable selector, or causal policy-effect claim.

## Main result

All 60 construction rows require a lexical edit, yet preserving the erroneous initial answer obtains mean whole-answer soft F1 `0.9784` and places `60/60` rows above the historical 0.8 threshold. Whole-answer overlap is therefore unsafe as a selective-revision gate.

Typed revision improves mean lexical revision-delta F1 from `0.0723` for generic revision to `0.1454`, but its whole-answer soft F1 is lower (`0.7974` versus `0.8734`). A reference-dependent per-item maximum over preserve/generic/typed reaches only `0.1618` delta F1, or `+0.0164` over always typed.

Filtering typed revisions at recorded primary confidence >=0.90 selects `31/60` rows. Their conditional delta F1 is `0.1386`, target-complete rate is `0.1613`, and collateral-edit rate is `0.8065`. None improves on the unfiltered typed trace. Current confidence is not a demonstrated fidelity selector.

## Fixed-arm metric conflict

| Frozen arm | Mean answer soft F1 | Rows >=0.8 | Mean revision-delta F1 |
|---|---:|---:|---:|
| `preserve` | 0.9784 | 60/60 | 0.0000 |
| `generic` | 0.8734 | 51/60 | 0.0723 |
| `typed` | 0.7974 | 37/60 | 0.1454 |

## Confidence-threshold replay with preserve fallback

| Threshold | Typed coverage | Mean answer soft F1 | Mean delta F1 | Selected delta F1 | Complete target | Collateral |
|---:|---:|---:|---:|---:|---:|---:|
| 0.00 | 60/60 | 0.7974 | 0.1454 | 0.1454 | 0.2500 | 0.7667 |
| 0.60 | 58/60 | 0.8050 | 0.1402 | 0.1450 | 0.2414 | 0.7586 |
| 0.70 | 57/60 | 0.8049 | 0.1307 | 0.1376 | 0.2456 | 0.7544 |
| 0.75 | 56/60 | 0.8125 | 0.1302 | 0.1395 | 0.2500 | 0.7500 |
| 0.80 | 48/60 | 0.8181 | 0.1169 | 0.1461 | 0.2917 | 0.8542 |
| 0.85 | 38/60 | 0.8679 | 0.0752 | 0.1187 | 0.2368 | 0.8421 |
| 0.90 | 31/60 | 0.8981 | 0.0716 | 0.1386 | 0.1613 | 0.8065 |
| 0.95 | 0/60 | 0.9784 | 0.0000 | -- | -- | -- |

## Interpretation boundary

The three outcomes are not causal counterfactuals: typed and generic answers come from independent frozen runs, while preserve is scored without generation. The per-item maximum and every delta-F1 result use the construction reference. The confidence curve was inspected on the same 60 development rows and has no prospective calibration or registered utility. It cannot license a selector, semantic repair claim, or held-out performance estimate.

The observed arm-choice headroom is small relative to the low absolute edit fidelity. A future selector therefore needs a newly preregistered development branch, a reference-free confidence signal calibrated before evaluation, and a utility that jointly handles edit benefit, collateral risk, and abstention. Recompute with `falsirag diag selective-revision-audit verify`.
