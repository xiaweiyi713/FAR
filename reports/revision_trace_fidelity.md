# FAR Frozen Revision-Trace Fidelity Audit

> Post-hoc, machine-audited development diagnostic over frozen predictions. No model calls, held-out/test access, human review, semantic judgment, or publication-gold claim.

## Main result

Qwen FAR records a mean trace delta F1 of `0.0823`. Only `15/60` rows completely cover the construction-reference edit target; `19/60` propose only off-target lexical edits and `12/60` propose no lexical target edit.

Typed minus untyped trace delta F1 is `+0.0481` with a paired 95% interval of `[+0.0084, +0.0998]`. The same post-hoc direction is positive in `3/3` WS2 families, combined `+0.0232` with a family-cluster interval of `[+0.0064, +0.0355]`.

The directional recurrence is narrower than revision reliability: typed control improves lexical target alignment on average, but the low absolute trace score and frequent off-target/collateral edits do not establish semantically correct repair.

## Qwen frozen methods

| Method | Action acc. | Trace delta F1 | Final delta F1 | Target hit | Target complete | Off-target | No edit |
|---|---:|---:|---:|---:|---:|---:|---:|
| `far` | 0.367 | 0.082 | 0.145 | 0.483 | 0.250 | 19 | 12 |
| `minus_typed_conflict` | 0.000 | 0.034 | 0.093 | 0.517 | 0.167 | 17 | 12 |
| `minus_typed_revision` | 0.000 | 0.000 | 0.072 | 0.000 | 0.000 | 52 | 8 |
| `minus_refutation_query` | 0.367 | 0.128 | 0.194 | 0.500 | 0.250 | 17 | 13 |
| `minus_boundary_query` | 0.367 | 0.097 | 0.166 | 0.467 | 0.233 | 20 | 12 |

## WS2 typed-minus-untyped trace sensitivity

| Family | Trace delta F1 difference |
|---|---:|
| `mistral` | +0.0064 |
| `google` | +0.0355 |
| `meta` | +0.0277 |

## Interpretation boundary

The audit compares token-multiset edits in recorded claim traces with the construction-derived whole-answer edit target. It can penalize valid paraphrases, reward incidental token overlap, and cannot decide whether evidence or a revision is semantically correct. It is post-hoc and must remain subordinate to the preregistered answer-result and stop-rule evidence.

Every source prediction is fingerprinted in the JSON report. Recompute with `falsirag diag revision-trace-audit verify`; the verifier performs zero model calls and rejects source, report, boundary, or Markdown drift.
