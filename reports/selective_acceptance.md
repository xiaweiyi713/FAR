# P14 Reference-Free Selective Acceptance

> Preregistered, machine-seeded development study. The controller acts after generation; this is not semantic correctness, human review, external validation, or a pre-execution selector.

## Registered outcome

`evaluation_success`

## Calibration

- Gate passed: `true`
- Candidate policies evaluated: `100`
- Policy: `{"confidence_min":0.0,"max_edit_fraction":0.5,"min_trace_consistency_margin":0.1}`
- Coverage: `0.2500` (15/60)
- Selected revision-delta F1: `0.2761`; enrichment over always typed `+0.1235`
- Collateral rate: `0.8000`; always typed `0.8333`
- Target-complete rate: `0.2667`; always typed `0.1833`

## Evaluation

- Success: `true`
- Coverage: `0.3000` (18/60)
- Selected revision-delta F1: `0.4547`; enrichment `+0.2351`
- Enrichment 95% bootstrap interval: `[+0.1028, +0.3856]`
- Policy global answer soft F1: `0.9439`
- Policy global revision-delta F1: `0.1364`

## Boundary

The policy features contain no construction reference or expected action, but outcome metrics remain construction-derived lexical diagnostics. Calibration and evaluation are dependency-group disjoint yet share one corpus and construction process. The policy accepts or rejects an already-generated typed answer and therefore does not save inference or establish deployment safety, semantic repair, human agreement, causal policy effect, or held-out/test performance.
