# P5 registered RAMDocs ablations

> Registered enhancement on 350 RAMDocs development items; upstream-labelled, not
> publication-grade human gold, human IAA, held-out, or test evidence.

| Hypothesis | Contrast | Full EM | Ablation EM | Difference | 90% CI | Verdict |
|---|---|---:|---:|---:|---:|---|
| H3 | `full - minus_typed_revision_aggressive` | 0.3057 | 0.3086 | -0.0029 | [-0.0229, +0.0171] | `uncertain` |
| H5 | `full - flat_claims` | 0.3057 | 0.3057 | +0.0000 | [-0.0057, +0.0057] | `equivalent` |

Equivalence requires the complete 90% sample-cluster bootstrap interval to lie
inside `[-0.02, +0.02]`. Crossing either bound is `uncertain`; an interval wholly
outside the bounds is `not_equivalent`. Finalization made zero model calls.

Source commit: `772fc97aea617cc49dd7778f8ad3fc9349e6c8b9`. Model digest: `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`.
