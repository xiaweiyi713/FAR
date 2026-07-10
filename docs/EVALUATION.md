# Evaluation Contract

Each prediction contains a sample ID, final answer, retrieved corpus document
IDs, predicted conflict types, revision action, method name, and trace metadata.

- **Answer correctness:** VeraRAG-compatible mixed Chinese/English soft F1.
- **Unsupported claim rate:** fraction of claim rows with no retrieved gold or
  counter-evidence document (evaluated after FAR's atomic decomposition).
- **Evidence precision/recall:** set overlap over corpus document IDs.
- **Counter-evidence recall:** recall restricted to annotated falsifying evidence.
- **Typed conflict F1:** micro F1 over predicted versus gold conflict types.
- **Conflict presence correctness:** whether the system predicts any conflict
  exactly when adjudicated gold does; human `no_conflict` rows count as correct
  only when the predicted conflict set is empty. Typed conflict F1 excludes
  these true negatives from its positive-gold denominator.
- **Revision accuracy:** correct revision action and answer soft F1 at least 0.8.
- **Overclaim reduction:** removal of unsupported causal language or incorrect
  numerical values, reported only where defined.

All primary means receive deterministic percentile bootstrap intervals,
stratified by category (2,000 resamples, seed 1729). Typed conflict F1 is
recomputed inside every resample rather than approximated by mean row accuracy.
System comparisons use paired stratified bootstrap over aligned IDs: baselines
are compared with Vanilla, while every component ablation is compared with full
FAR. Binary answer, conflict, and revision outcomes also use exact two-sided
McNemar tests. Source-document dependency-group sensitivity must accompany the
final paper because 300 candidates are not 300 independent contexts.

Do not compare reports with different benchmark, corpus, configuration, or
implementation hashes. A paired report records both method names and the
baseline score fingerprint, and rejects sample/category/split/dependency-group
mismatches. `far.experiments.validate_results` enforces prediction and evaluation
provenance. Partial/demo reports are never publication evidence.
