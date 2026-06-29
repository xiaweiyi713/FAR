# Evaluation Contract

Each prediction contains a sample ID, final answer, retrieved corpus document
IDs, predicted conflict types, revision action, method name, and trace metadata.

- **Answer correctness:** VeraRAG-compatible mixed Chinese/English soft F1.
- **Unsupported claim rate:** fraction of claim rows with no retrieved gold or
  counter-evidence document (one atomic claim in candidate v0.1).
- **Evidence precision/recall:** set overlap over corpus document IDs.
- **Counter-evidence recall:** recall restricted to annotated falsifying evidence.
- **Typed conflict F1:** micro F1 over predicted versus gold conflict types.
- **Revision accuracy:** correct revision action and answer soft F1 at least 0.8.
- **Overclaim reduction:** removal of unsupported causal language or incorrect
  numerical values, reported only where defined.

All primary means receive deterministic percentile bootstrap intervals,
stratified by category (2,000 resamples, seed 1729). System comparisons use
paired stratified bootstrap over aligned IDs. Binary revision success also uses
the exact two-sided McNemar test. Source-document dependency-group sensitivity
must accompany the final paper because 300 candidates are not 300 independent
contexts.

Do not compare reports with different benchmark, corpus, configuration, or
implementation hashes. `experiments.validate_results` enforces prediction and
evaluation provenance. Partial/demo reports are never publication evidence.
