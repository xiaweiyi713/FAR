# RAMDocs dev error analysis

This is a deterministic analysis of the frozen 350-row dev evidence. It is not test-set evidence, human annotation, or human IAA.

## Gate result

- G-A passed: `false`
- FAR exact match: `0.311429`
- multi_query_rag exact match: `0.311429`
- paired difference: `0.000000`
- bootstrap 95% CI: `[-0.028643, 0.031429]`
- McNemar p: `1.000000`
- The preregistered stop rule is active; Phase B must not start.

## Paired outcomes

| Outcome | Samples |
|---|---:|
| both_correct | 93 |
| far_only | 16 |
| baseline_only | 16 |
| both_incorrect | 225 |

## Aggregate diagnostics

| Method | Gold coverage | Wrong exclusion | Unsupported sentences |
|---|---:|---:|---:|
| FAR | 0.7510 | 0.5686 | 0.9982 |
| multi_query_rag | 0.7457 | 0.5743 | 0.9933 |

## Category breakdown

| Category | Both correct | FAR only | Baseline only | Both incorrect |
|---|---:|---:|---:|---:|
| ambiguity_misinformation | 15 | 8 | 10 | 133 |
| ambiguity_noise | 78 | 8 | 6 | 92 |

The complete 32-row discordant audit trail is in `discordant_cases.jsonl`.
