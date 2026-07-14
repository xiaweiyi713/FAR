# P14 Preregistration: Reference-Free Revision Acceptance

Status: frozen before any P14 model output is generated or inspected.

This protocol follows the negative P13 result. P13 showed that whole-answer
overlap and recorded primary confidence do not identify faithful revisions on
the already-consumed 60-item development split. P14 therefore does not tune
another confidence threshold on those rows. It evaluates a distinct,
post-generation accept/reject controller on previously unused train rows.

## Research question and claim level

Can a deterministic controller that observes only the generated FAR trace and
the initial/final texts identify a subset of typed revisions with higher
construction-derived lexical edit fidelity, while falling back to the recorded
initial answer on rejected rows?

The maximum claim is a preregistered, reference-free acceptance-policy result on
machine-seeded, group-disjoint development evidence. It is not semantic
correctness, human validation, external blindness, deployment safety, a
pre-execution selector, or a causal estimate of another model run.

## Frozen evidence and split

- Source rows: `bench/splits/train.jsonl`, SHA-256
  `7796d44fd7673c7c4a6b22cce6829f9463d72635b08d6394887945ce8e561df4`.
- Corpus: `bench/corpus.jsonl`, SHA-256
  `cca5f62db0fbb51e1bae8111ea85fe169fba7be5a8e63847a9c1c048cdae25cd`.
- No development or test row is eligible.
- The builder assigns complete `source_metadata.dependency_group` values to
  calibration or evaluation using the first nonnegative nonce whose SHA-256
  partition gives both sides at least 12 rows in every one of the five frozen
  categories. Within each side/category, the 12 lowest seeded sample hashes are
  selected. The result is exactly 60 calibration and 60 evaluation rows, 12 per
  category, with no dependency group shared across sides.
- Operational model input exposes exactly `id`, `category`, `split`, `question`,
  and `initial_answer`. Construction references, expected actions, evidence
  labels, and source metadata are absent from the remote input packet.

The split seed is `far-p14-selective-acceptance-v1`. The split algorithm, nonce,
selected IDs, group memberships, source hashes, and operational-input hash are
recorded by the protocol manifest and recomputed by the verifier.

## Frozen inference arm

P14 runs one FAR arm over all 120 operational rows with:

- `far/experiments/configs/qwen_open.yaml`, SHA-256
  `a8da92080d9750b7d097b05f8e8ee5ea8f84f2e05432be3e26f13004b3cbb4ea`;
- Ollama `qwen3.5:9b`, digest
  `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`;
- temperature 0, thinking disabled, frozen retrieval/NLI assets, and resumable
  per-sample checkpoints;
- split `train`, `allow_test=false`, no row limit, and the exact preregistration
  commit.

The comparison output for a rejected row is deterministic preservation of its
recorded initial answer; it is not a second generated counterfactual arm. The
study records 120 pipeline-sample executions and does not equate that count
with exact internal LLM HTTP calls.

## Reference-free acceptance features

For each completed FAR output, the controller may use only:

1. whether the primary trace declares a changed, non-`keep` action;
2. primary trace confidence;
3. edit fraction: token-multiset removals plus additions from initial to final,
   divided by the initial token count;
4. trace consistency margin: soft F1(final, primary `after`) minus
   soft F1(final, primary `before`).

No construction reference, expected action, gold conflict, category, dependency
group, score, or calibration/evaluation identity may enter these features.

The fixed candidate grid is the Cartesian product:

- confidence minimum: `0.00, 0.75, 0.80, 0.85, 0.90`;
- maximum edit fraction: `0.20, 0.35, 0.50, 1.00, 2.00`;
- minimum trace consistency margin: `-1.00, 0.00, 0.10, 0.25`.

Every candidate also requires a changed, non-`keep` primary action. Policy IDs
are the canonical JSON encoding of these three thresholds.

## Calibration, stop rule, and evaluation

Calibration considers only policies with coverage in `[0.25, 0.75]`. It ranks
them lexicographically by:

1. higher selected-row mean revision-delta F1;
2. lower selected-row collateral-edit rate;
3. higher selected-row target-complete rate;
4. higher coverage;
5. lexicographically smaller policy ID.

The calibration gate passes only when the selected policy has all of:

- coverage in `[0.25, 0.75]`;
- selected-row mean revision-delta F1 at least `0.03` above always typed;
- selected-row collateral-edit rate no higher than always typed;
- selected-row target-complete rate no lower than always typed.

If no candidate is eligible or the best candidate fails this gate, evaluation
labels remain unscored and the registered outcome is `stopped_at_calibration`.
The same run may not change the grid, thresholds, split, utility, or gate and
retry.

If calibration passes, the exact chosen policy is applied once to the frozen
evaluation rows. The primary evaluation success rule requires:

- coverage in `[0.25, 0.75]`;
- selected-row revision-delta enrichment of at least `0.03` over always typed;
- the 95% category-stratified bootstrap lower bound for that enrichment above
  zero;
- collateral-edit rate no higher than always typed; and
- target-complete rate no lower than always typed.

Whole-answer soft F1 and global policy revision-delta F1 are reported as
trade-off diagnostics, not substituted success criteria. All failures and nulls
remain reportable.

## Boundaries and stopping rules

- This is machine-seeded development evidence with construction-derived lexical
  outcomes, not human gold or semantic repair.
- The controller acts after typed generation. It may save answer quality by
  rejecting an output, but it does not save generation cost and is not the
  pre-execution selector proposed as future work in the paper.
- Calibration and evaluation share the corpus and construction process despite
  dependency-group separation; no external-domain or deployment claim follows.
- The locked benchmark test split remains untouched. P14 cannot authorize a
  held-out/test run.
- All model execution must occur on `windows-gpu` only after an idle-state
  preflight. No model may be downloaded or run on the local Mac.
- A runtime/config/model/source mismatch, duplicate or missing prediction, trace
  schema failure, checkpoint drift, or source fingerprint mismatch is a hard
  failure. Repair requires an explicit amendment, not silent replacement.

## Registered artifacts

- protocol/packet builder and verifier:
  `far/experiments/selective_acceptance.py`;
- remote execution service and guarded preparer under `scripts/`;
- raw remote run identity, append-only checkpoint, finalized predictions, and
  run manifest;
- deterministic JSON/Markdown result and independent recomputation audit.

The preregistration tag is `prereg-selective-acceptance-v1`. It must point to the
clean source commit used by the formal run.
