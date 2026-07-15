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
| Verified post-hoc family revision-delta sensitivity | `true` |
| Verified post-hoc revision-trace fidelity audit | `true` |
| Verified post-hoc selective-revision feasibility audit | `true` |
| Verified preregistered selective-acceptance study | `true` |

## Narrow supported claim

Across eight RAMDocs development methods, errors concentrate after retrieved evidence and answer transformation; FAR shows a narrower machine-audited typed-control signal whose transport and ontology stability are explicitly bounded. A preregistered reference-free post-generation policy also enriched typed revision-delta on fresh machine-seeded train evidence under explicit non-semantic and non-deployment boundaries.

- FAR answer correctness: `0.797`
- Typed minus untyped answer correctness: `+0.078`
- Typed minus untyped conflict F1: `+0.420`
- Typed minus untyped revision accuracy: `+0.217`
- FAR post-hoc revision delta F1: `0.145`
- FAR post-hoc typed revision delta F1: `0.096`
- Typed minus untyped revision delta F1: `+0.053`
- Three-family post-hoc raw delta difference: `+0.0398`
- Three-family post-hoc typed delta difference: `+0.0816`
- Qwen FAR post-hoc mean trace delta F1: `0.0823`
- Qwen typed minus untyped trace delta F1: `+0.0481`
- Preserved initial-answer soft F1: `0.9784`
- Reference-dependent delta-F1 arm envelope: `0.1618`
- Envelope gain over always typed: `+0.0164`
- Confidence >=0.90 selected trace-complete rate: `0.1613`
- P14 calibration coverage: `0.2500`
- P14 evaluation coverage: `0.3000`
- P14 evaluation selected delta enrichment: `+0.2351`
- P14 enrichment 95% interval: `[+0.1028, +0.3856]`
- Machine-confirmed answer delta (`n=35`): `+0.101`
- Machine-disputed answer delta (`n=25`): `+0.047`

## Required limitations

- labels are not human-validated gold
- evaluation is not externally blind
- the broad baseline delta ranking is Qwen-only and does not establish multi-model generality
- refutation and boundary query ablations do not support positive marginal claims
- typed revision trades lower answer correctness for non-zero revision behavior
- revision-delta metrics are post-hoc lexical diagnostics, not semantic correctness
- revision traces frequently miss the construction target or add collateral edits
- selective revision feasibility is post-hoc and does not evaluate a deployable selector
- P14 selective acceptance is post-generation, uses construction-derived lexical outcomes, and does not save inference
- P14 calibration and evaluation share one machine-seeded train corpus and are neither external nor test evidence
- raw baseline revision delta exceeds FAR despite zero typed action-conditioned delta
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
- P14 as semantic correctness, deployment safety, inference savings, or causal policy effect
- held-out or test validation from the P14 train-only split
