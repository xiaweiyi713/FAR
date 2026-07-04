# FAR Reports

This directory contains durable, versioned reports derived from tracked project evidence.

- [Single-author machine-audited diagnostic report](single_author_diagnostic_report.md): the complete solo diagnostic deliverable for the no-human-annotator path. It is explicitly not a strict AAAI submission report.
- [Solo human-review priority CSV](solo_human_review_priority.csv): a deterministic
  triage table for the 122 machine-disputed rows. It is generated from the
  tracked machine-consensus audit and is a review-priority aid, not gold labels.
- [Project status snapshot](project_status_snapshot.md) and
  [machine-readable JSON](project_status_snapshot.json): a generated ledger
  separating the complete single-author diagnostic track from the still-blocked
  strict AAAI submission track.
- [Single-author machine-audited paper readiness](solo_paper_readiness.md) and
  [machine-readable JSON](solo_paper_readiness.json): the explicitly relaxed
  paper gate. It permits only the narrow typed-control mechanism claim and
  requires disclosure of negative ablations and all non-human/non-blind limits.
- The project-status snapshot also exposes the preregistered 2+4 profile:
  RAMDocs upstream-label validation, cross-family LLM jury, author-blind
  adjudication, multi-model jury-gold rescoring, and commit-bound one-shot tests.
  It remains fail-closed until every corresponding evidence artifact exists.
