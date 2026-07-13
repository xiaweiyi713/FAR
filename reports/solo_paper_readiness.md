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
| Tracked stage trace map | `true` |
| Tracked registered P5 report | `true` |
| Verified P6-M negative stability audit | `true` |

## Narrow supported claim

Across eight RAMDocs development methods, errors concentrate after retrieved evidence and answer transformation; FAR shows a narrower machine-audited typed-control signal whose transport and ontology stability are explicitly bounded.

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
- cross-method trace attribution does not identify detection or action causal gaps
- P5 uses upstream-labelled development evidence and H3 remains uncertain
- P6-M is machine-panel sensitivity, not population type mappability
- the strict human P6 analysis was not completed

## Forbidden claims

- human inter-annotator agreement
- human adjudication
- externally held blind test
- publication-grade benchmark gold
- positive marginal contribution from every FAR component
- multi-model or external-domain generality
- H3 equivalence or H4 confirmation
- P6-M as human review, human adjudication, or human IAA
- population mappability estimated from the 15 machine-consensus rows
