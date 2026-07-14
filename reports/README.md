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
- [Long-term roadmap status](longterm_roadmap_status.md) and
  [machine-readable JSON](longterm_roadmap_status.json): a generated WS1--WS6
  ledger for the post-stop-rule roadmap. It is a status dashboard, not a new
  empirical gate or submission waiver.
- [TMLR result-integration matrix](tmlr_result_integration_matrix.md): the WS4
  writing checklist that maps verified WS2/WS3 outcome combinations to the
  A/B/C paper lines without changing frozen facts, gates, or evidence status.
- [Registered P5 RAMDocs ablations](p5_ramdocs_ablations.md) and
  [machine-readable JSON](p5_ramdocs_ablations.json): the verified 3×350
  upstream-labelled dev enhancement. H3 remains uncertain and H5 meets the
  registered equivalence rule; neither is human-gold or test evidence.
- [P6-M cross-family machine ontology-stability audit](type_mappability_machine/type_mappability_machine.md)
  and [machine-readable JSON](type_mappability_machine/type_mappability_machine.json):
  all three jurors completed, but only 15/217 samples reached stable machine
  consensus and 202 were contested. This is negative model-panel sensitivity
  evidence and the terminal outcome for the accepted no-human redirection
  profile. It is not human mappability, IAA, gold, or completion of the separate
  strict-human P6. That optional human branch is inactive. The tracked
  [juror inputs](type_mappability_machine/jurors/) preserve the minimal raw
  response and identity evidence required for fresh-clone verification.
- [Single-author machine-audited paper readiness](solo_paper_readiness.md) and
  [machine-readable JSON](solo_paper_readiness.json): the explicitly relaxed
  paper gate. It permits only the narrow typed-control mechanism claim and
  requires disclosure of negative ablations and all non-human/non-blind limits.
  The v5 gate additionally binds the registered P5 verdicts, independently
  recomputes the P6-M negative stability audit, and verifies the P11--P13
  lexical edit, trace-fidelity, and selective-revision feasibility boundaries.
- [P12 frozen revision-trace fidelity audit](revision_trace_fidelity.md) and
  [machine-readable JSON](revision_trace_fidelity.json): row-level lexical
  target alignment over frozen Qwen and WS2 traces. It is post-hoc and not
  semantic correctness.
- [P13 selective-revision feasibility audit](selective_revision_feasibility.md)
  and [machine-readable JSON](selective_revision_feasibility.json): metric
  conflict, a reference-dependent arm-choice envelope, and confidence-threshold
  replay over frozen Qwen outputs. It explicitly does not evaluate a deployable
  selector or causal policy effect.
- P14 has a frozen protocol and result-blind performance amendment but no result
  report. Its incomplete 10-row v1 attempt was paused before content/outcome
  inspection and is permanently ineligible. The 60/60 group-disjoint split,
  label-free packet, policy grid, calibration stop, fresh v2 cache/output, and
  keep-alive lifecycle are defined by the original protocol plus
  `docs/AMENDMENT_SELECTIVE_ACCEPTANCE_PERFORMANCE_2026-07-14.md`. A report may
  be added only after the exact tagged 120-row v2 run and recomputation.
- The project-status snapshot also exposes the preregistered 2+4 profile:
  RAMDocs upstream-label validation, cross-family LLM jury, author-blind
  adjudication, multi-model jury-gold rescoring, and commit-bound one-shot tests.
  It remains fail-closed until every corresponding evidence artifact exists.
