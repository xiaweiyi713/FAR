# Stage-wise trace map (observational)

> This is a zero-model, capability-aware trace attribution over frozen RAMDocs dev
> artifacts. It is not a causal oracle ladder and does not use human gold.

## Decision summary

- Samples: `350`; methods: `8`; cells: `2800`.
- T1 methods passing: `8/8`; supported: `true`.
- T2 changed-wrong minus retrieval-miss: `+0.3914` (95% CI `[+0.3554, +0.4275]`).
- Causal attribution: `false`; publication gold: `false`; test accessed: `false`.

## 8-method failure map

| Method | Correct | Retrieval unscorable | Retrieval miss | Retrieved + unchanged wrong | Retrieved + changed wrong | T1 |
|---|---:|---:|---:|---:|---:|:---:|
| `vanilla_rag` | 101 | 2 | 6 | 89 | 152 | yes |
| `multi_query_rag` | 109 | 2 | 2 | 101 | 136 | yes |
| `crag_style_reproduction` | 104 | 2 | 5 | 99 | 140 | yes |
| `self_rag_style_reproduction` | 103 | 2 | 2 | 118 | 125 | yes |
| `reflective_rag` | 106 | 2 | 4 | 75 | 163 | yes |
| `counterrefine_style_reproduction` | 102 | 2 | 2 | 47 | 197 | yes |
| `far` | 109 | 2 | 3 | 134 | 102 | yes |
| `far_minus_typed_conflict` | 106 | 2 | 2 | 133 | 107 | yes |

`changed` means citation-stripped normalized text changed relative to the shared initial answer. It does not mean the factual revision was correct.

## Capability matrix

| Method | Retrieval IDs | Initial/final answer | Typed conflict | Revision action | Claim revision trace |
|---|:---:|:---:|:---:|:---:|:---:|
| `vanilla_rag` | yes | yes | no | no | no |
| `multi_query_rag` | yes | yes | no | no | no |
| `crag_style_reproduction` | yes | yes | no | no | no |
| `self_rag_style_reproduction` | yes | yes | no | no | no |
| `reflective_rag` | yes | yes | no | no | no |
| `counterrefine_style_reproduction` | yes | yes | no | no | no |
| `far` | yes | yes | yes | yes | yes |
| `far_minus_typed_conflict` | yes | yes | yes | yes | yes |

## FAR-only trace detail

### `far`

Revision actions: `clarify_definition=2`, `correct_temporal=33`, `keep=191`, `qualify_uncertainty=1`, `replace_numerical=94`, `requalify_entity=8`, `retract=21`

Weak-label misinformation/post-retrieval/wrong 2x2: `conflict_signal__trace_changed=62`, `no_conflict_signal__trace_unchanged=76`

### `far_minus_typed_conflict`

Revision actions: `keep=191`, `qualify_uncertainty=64`, `retract=95`

Weak-label misinformation/post-retrieval/wrong 2x2: `conflict_signal__trace_changed=61`, `no_conflict_signal__trace_unchanged=78`

## Claim boundary

- The cross-method result concerns post-retrieval answer transformation, not detection.
- Detection/action traces are absent for six baselines and are not imputed as failures.
- Two samples lack upstream correct-document labels and are retrieval-unscorable.
- RAMDocs labels are upstream labels, not human IAA or publication-grade gold.
- No model was called and no held-out test was accessed.
