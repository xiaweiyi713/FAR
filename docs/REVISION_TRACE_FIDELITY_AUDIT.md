# Frozen Revision-Trace Fidelity Audit

Status: P12 post-hoc, machine-audited development diagnostic over frozen
predictions. It is not preregistered, semantic correctness, human validation,
publication gold, causal attribution, or held-out/test evidence.

## Question

P11 measures the lexical edits visible in each final answer. P12 asks a narrower
mechanism question: before final rendering, do FAR's recorded claim-level
revision traces propose the token removals and additions required by the
construction-derived reference?

For every trace entry, the audit computes token-multiset removals from `before`
and additions in `after`, using the same mixed Chinese/English tokenizer as the
P11 delta metric. It sums those proposed trace edits within an item and compares
them with the edit from `initial_answer` to the construction reference. The row
is assigned exactly one descriptive bucket:

- `no_lexical_edit`: the trace proposes no token edit;
- `off_target`: edits occur, but none overlap the construction target;
- `partial_target` or `partial_with_collateral`: some target edits are covered;
- `complete_with_collateral`: every target edit is covered alongside extra edits;
- `exact_target`: proposed and required token edits match exactly.

Trace delta precision, recall, and F1 use the same correct/proposed/expected
count definitions as P11. Final-answer delta is recomputed independently and
must agree with the existing metric implementation. The audit also checks every
`changed` flag against the recorded before/after text and binds the declared
revision action to the primary trace action.

## Frozen observations

On the 60-item Qwen development suite, FAR's mean trace delta F1 is `0.0823`.
Only `15/60` rows completely cover the construction target (`1` exact and `14`
with collateral edits); `19/60` are off-target and `12/60` make no lexical
target edit. Typed minus untyped trace delta F1 is `+0.0481`, paired 95% interval
`[+0.0084,+0.0998]`. Target-complete rate rises by `+0.0833`, but any-target-hit
rate changes by `-0.0333` with an interval crossing zero. The directional gain
therefore reflects better completeness/precision on some rows, not more frequent
target contact.

The same post-hoc typed-minus-untyped trace-F1 direction is positive for
Mistral, Gemma, and Llama (`+0.0064`, `+0.0355`, `+0.0277`). The combined
difference is `+0.0232`, family-cluster 95% interval
`[+0.0064,+0.0355]`. This recurrence is descriptive and construction-dependent;
it was not a preregistered WS2 outcome.

## Interpretation boundary

Token multisets ignore edit position and meaning. The audit can penalize a valid
paraphrase, reward incidental token overlap, and cannot establish that the
reference is uniquely correct. It diagnoses recorded trace/reference alignment,
not semantic repair quality or a causal action oracle. The low absolute scores
and frequent collateral/off-target edits strengthen the existing conclusion:
typed control exposes a directional mechanism signal, while revision reliability
remains the principal engineering risk.

## Reproduction

After installing the immutable `artifacts-v2` diagnostics:

```bash
uv run falsirag diag revision-trace-audit verify
```

The verifier deterministically recomputes all 11 Qwen/family trace summaries,
paired intervals, prediction fingerprints, Markdown, and boundary flags. It
performs zero model calls and does not read a held-out/test split.
