# P13 Selective-Revision Feasibility Audit

Status: complete post-hoc development diagnostic. This is not a prospective
policy evaluation or a new empirical gate.

## Question

P11 and P12 show a real tension: typed control improves construction-derived
lexical edit alignment, but typed revision lowers whole-answer overlap and most
recorded traces do not completely realize the target. P13 asks whether the
frozen outputs already contain a usable signal for deciding when to apply a
typed revision.

The answer is no. Current whole-answer overlap is unsafe as the policy utility,
recorded confidence does not rank edit fidelity, and even a
reference-dependent per-item arm oracle has little selection headroom over the
always-typed arm. The dominant remaining problem is realization quality, not a
missing confidence threshold.

## Frozen inputs

The deterministic audit reads only:

- the 60-row FalsiRAG-Bench development split;
- the tracked Qwen FAR and `minus_typed_revision` predictions and score rows;
- their frozen solo-suite manifest and prediction hashes;
- the independently verified P12 revision-trace report.

`minus_typed_revision` is a generic `qualify_uncertainty` realization, not a
literal no-change arm. P13 therefore adds a deterministic `preserve` arm by
scoring the recorded erroneous initial answer without generation. Typed and
generic outputs remain independent runs; none is treated as a causal
counterfactual for another.

## Results

| Frozen arm | Mean answer soft F1 | Rows at or above 0.8 | Mean revision-delta F1 |
|---|---:|---:|---:|
| Preserve initial answer | 0.9784 | 60/60 | 0.0000 |
| Generic revision | 0.8734 | 51/60 | 0.0723 |
| Typed revision | 0.7974 | 37/60 | 0.1454 |

All 60 construction rows require a non-empty target edit. The fact that an
unchanged erroneous answer crosses the historical 0.8 threshold on every row
confirms that whole-answer soft F1 cannot serve as a selective-revision safety
gate.

A reference-dependent per-item maximum over preserve, generic, and typed outputs
reaches revision-delta F1 0.1618. That is only +0.0164 over always selecting the
typed output. The winner accounting is 28 typed-only, 7 generic-only, one
generic/typed tie, and 24 all-zero ties. This is an in-sample upper envelope,
not an implementable oracle.

At recorded primary confidence at least 0.90, typed coverage falls to 31/60.
Those selected rows have conditional revision-delta F1 0.1386, below the
unfiltered 0.1454; only 5/31 are trace-target complete and 25/31 contain
collateral lexical edits. Raising the current confidence threshold therefore
does not demonstrate selective fidelity.

## Claim boundary

The report is post-hoc, construction-reference dependent, and evaluated on the
same development rows used to identify the problem. It has no registered policy
utility, prospective confidence calibration, semantic correctness judgment,
held-out/test access, human review, or causal policy-effect estimate. It does
not evaluate a deployable selector.

A future policy experiment must start as a new preregistered development branch.
Before any GPU run, it needs a reference-free confidence signal, a frozen
coverage/risk/abstention utility, a calibration/evaluation split that is not
selected after seeing these curves, and explicit stopping rules. P13 does not
authorize use of the locked test inputs.

## Reproduce

```bash
uv run falsirag diag selective-revision-audit build
uv run falsirag diag selective-revision-audit verify
```

Both commands make zero model calls. The JSON report fingerprints every source
and retains all 60 row-level outcomes; the verifier rejects source, report,
boundary, confidence-curve, or Markdown drift.
