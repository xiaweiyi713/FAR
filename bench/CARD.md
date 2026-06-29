# FalsiRAG-Bench Dataset Card

## Summary

FalsiRAG-Bench isolates a retrieval-augmented agent's ability to seek evidence
that can falsify its initial answer and to revise under a typed conflict. The
tracked v0.2.0 artifact contains 300 machine-seeded candidates: 60 each for
temporal shift, numerical conflict, entity confusion, causal overclaim, and
multi-source conflict. Every candidate contains a falsifiable initial claim,
claim-level evidence, in-corpus counter-evidence, a typed conflict seed, and an
expected revision seed.

This release is a **candidate set, not publication gold**. The machine-generated
labels must be replaced or confirmed by two independent annotators and an
adjudicator. `manifest.json` deliberately sets `publication_ready` to false.

## Construction and provenance

The builder selects evidence-backed VeraBench v1.1.2 examples with deterministic
SHA-256 ranking (seed 1729). Temporal, numerical, and entity candidates are
created by controlled perturbation of an evidence-supported answer. Causal
examples add an explicit causal overclaim plus a synthetic source-entailment
boundary note. Multi-source examples add a synthetic low-reliability distractor
while preserving the original evidence-backed answer as counter-evidence.

VeraBench passages are controlled summaries released under the VeraRAG MIT
license. Upstream names and URLs are provenance metadata; upstream material
retains its own terms. Synthetic boundary and distractor documents are released
under the FAR MIT license and are marked `synthetic: true`.

The optional FEVER external slice is imported from VeraRAG's fingerprinted
candidate set. Its declared upstream licenses are CC-BY-SA-3.0 and GPL-3.0. It
remains separate from the main benchmark and cannot be reported as gold before
independent annotation and adjudication.

## Splits and leakage control

The 60/20/20 target is assigned over source-document dependency groups, not
individual questions. The current deterministic realization is 182 train, 60
dev, and 58 test candidates. No source-document dependency group crosses a
split. `splits/test_inputs.jsonl` omits claims, counter-evidence roles, conflict
labels, expected revisions, and source-generation metadata.

The test gold remains in the full local research archive. The
`falsirag-build-blind-bundle` command creates a separate handoff containing a
sanitized corpus and operational inputs only; test runners can execute entirely
from that directory and emit unscored predictions. This technical separation
does not itself create organizational blindness: publication claims still
require an external custodian/independent evaluator and a documented one-shot
handoff.

## Annotation

Run:

```bash
falsirag-validate-bench
python -m bench.build.annotate_packet build \
  --data-dir bench --output-dir outputs/falsirag_annotation \
  --annotator annotator_a --annotator annotator_b
```

Annotators label conflict presence, conflict type, revision action, and revised
answer acceptability independently. An adjudicator then resolves every item.
The compiler reports pairwise and mean Cohen's kappa for conflict presence,
conflict type, and revision action. The promotion target is at least 0.60 on all
three mean kappas; the values must be reported even when the gate fails.

Machine preannotations can be generated with `falsirag-auto-annotate` to speed
triage, but they remain `publication_gold: false` and cannot replace independent
human annotation. Reviewer draft files produced from preannotations are rejected
by the compiler until a human explicitly marks them reviewed.

## Validation and retrieval viability

The validator checks schema constraints, unique IDs, continuous or segmented
evidence traceability, category balance, fingerprints, masked test inputs, and
zero cross-split dependency leakage. It also runs FAR's deterministic lexical
retriever over all three typed query families and requires counter-evidence
recall@10 of at least 0.80. The current candidate build achieves 0.91; this is a
construction check, not a model result.

Candidate v0.2 also forbids identical `(question, initial_answer)` inputs with
different revision labels. Multi-source rows explicitly attribute their initial
answer to an unverified secondary summary, making source reliability observable
without exposing the hidden category. This repairs 29 ambiguous input pairs in
the previous candidate build.

Contamination claims are scoped to explicitly supplied references:

```bash
python -m bench.build.audit_contamination \
  --benchmark bench/falsirag_bench.jsonl \
  --reference /path/to/training_or_prompt_corpus.jsonl \
  --output outputs/contamination.json
```

## Intended use and limitations

Use the benchmark for controlled comparisons of falsifying retrieval, typed
conflict detection, and typed revision. Do not use it as current factual advice,
as broad language-understanding evidence, or as training data for the evaluated
test setting.

Important limitations are the controlled/synthetic construction, reuse of a
small source corpus, correlated variants within source-document groups,
Chinese-heavy main data, currently uncompleted human annotation, and an
operational rather than externally enforced blind test. Confidence intervals
must respect dependency groups. Report external FEVER results separately.
