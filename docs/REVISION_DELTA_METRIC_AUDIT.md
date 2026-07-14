# Revision-Delta Metric Audit

Status: post-hoc, machine-audited development diagnostic; not preregistered,
human-validated, externally blind, or publication gold.

## Motivation

The original FalsiRAG-Bench `answer_correctness` metric is a whole-answer
lexical soft F1 against the construction-derived revised answer. Most benchmark
rows change only a date, number, entity, causal clause, or source qualifier.
Consequently, leaving the erroneous initial answer untouched can retain nearly
all reference tokens and receive a high whole-answer score. That score remains
useful as a surface-preservation diagnostic, but it cannot by itself establish
that the targeted error was repaired.

This issue was found after the Qwen development results were already visible.
The new metric is therefore explicitly post-hoc and descriptive. It does not
alter any frozen prediction, reference label, preregistered P5/P6-M verdict, or
strict submission gate.

The same frozen evaluator profile is also applied to the already completed WS2
typed/untyped family predictions. This is a post-hoc transport sensitivity, not
the preregistered WS2 primary outcome. Raw typed-minus-untyped delta differences
are positive for Mistral, Gemma, and Llama (`+0.0133`, `+0.0524`, `+0.0536`);
the combined difference is `+0.0398` with family-cluster 95% interval
`[+0.0133,+0.0536]`. Action-conditioned differences are also 3/3 positive,
combined `+0.0816` with interval `[+0.0353,+0.1137]`. These results show only
directional recurrence of construction-dependent lexical edit alignment.

## Frozen definition

Tokenize the initial answer, prediction, and construction-derived revised
answer with the existing mixed Chinese/English `_soft_tokens` tokenizer and
represent each as a token multiset. Define:

- expected removals: `initial - reference`;
- expected additions: `reference - initial`;
- predicted removals: `initial - prediction`;
- predicted additions: `prediction - initial`.

Correct edits are the multiset intersections of expected and predicted
removals plus expected and predicted additions. `revision_delta_precision` is
correct edits divided by all predicted edits; `revision_delta_recall` is
correct edits divided by all expected edits; and `revision_delta_f1` is their
harmonic mean. An unchanged erroneous answer receives zero. An exact reference
revision receives one. Unnecessary rewriting lowers precision even when the
targeted edit is present.

`typed_revision_delta_f1` equals the row's delta F1 only when the method's
declared revision action matches the construction-derived expected action; it
is zero otherwise. This action-conditioned companion prevents incidental token
copying from being presented as typed control. The unconditioned delta F1 must
remain visible beside it so that the action gate cannot hide broad but useful
answer changes made by non-typed baselines.

For a row with no expected edit, leaving the answer unchanged receives one;
an unnecessary edit receives zero precision and zero F1. The current
conflict-focused candidate benchmark has an expected edit on every row, but the
defined edge case makes the metric safe for future no-conflict controls.

## Interpretation boundary

Revision delta is a lexical edit-fidelity diagnostic, not semantic correctness.
It can miss a valid paraphrase, reward a token edit in the wrong position, and
inherits every limitation of the construction-derived reference. Report it
beside whole-answer soft F1, typed-conflict metrics, action accuracy, and the
existing category-specific overclaim checks. The action-conditioned companion
inherits the limitations of the top-level action label. Never use either metric
alone as evidence of human-quality correction, generalization, or publication
readiness.

All P11 recomputation must use recorded prediction JSONL files through the
suite `--reports-only` path or the WS2 `family-dev refresh-evaluations` path.
The recomputation records zero model calls and must not access the frozen test
split. Evaluation reports and generated artifacts bind this contract as
`falsirag-evaluation-metrics-v2-revision-delta`; the public diagnostic verifier
rejects legacy or incomplete metric profiles instead of silently mixing them.
