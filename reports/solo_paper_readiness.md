# Single-Author Machine-Audited Paper Readiness

This report audits the explicitly relaxed paper profile. It does not certify
strict AAAI submission readiness, human gold, external blindness, or
multi-model generality.

| Item | Status |
|---|---|
| Relaxed machine-audited paper profile | `true` |
| Strict AAAI submission | `false` |
| Tracked solo evidence | `true` |
| Paper claim scope matches ablations | `true` |
| FEVER negative transfer disclosed | `true` |

## Narrow supported claim

On a construction-derived, machine-audited 60-item Qwen development diagnostic, typed conflict control improves over its untyped ablation.

- FAR answer correctness: `0.797`
- Typed minus untyped answer correctness: `+0.078`
- Typed minus untyped conflict F1: `+0.420`
- Typed minus untyped revision accuracy: `+0.217`
- Machine-confirmed answer delta (`n=35`): `+0.101`
- Machine-disputed answer delta (`n=25`): `+0.047`

## Required limitations

- labels are not human-validated gold
- evaluation is not externally blind
- one local model does not establish multi-model generality
- refutation and boundary query ablations do not support positive marginal claims
- typed revision trades lower answer correctness for non-zero revision behavior
- FEVER binary transfer shows no paired accuracy gain
- machine-disposition sensitivity is post-hoc and not independent label validation

## Forbidden claims

- human inter-annotator agreement
- human adjudication
- externally held blind test
- publication-grade benchmark gold
- positive marginal contribution from every FAR component
- multi-model or external-domain generality
