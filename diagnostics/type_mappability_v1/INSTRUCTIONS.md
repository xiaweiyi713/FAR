# P6 type-mappability annotation packet

Distribute only `items.jsonl` plus one matching reviewer template to each reviewer. Reviewers work independently without seeing `analysis_index.jsonl`, model prelabels, another reviewer, or FAR scores.

## Types

- `temporal`: time, date, version, or validity-period conflict for the same fact slot
- `entity`: entity identity, reference, namesake, or entity-value substitution
- `numerical`: conflicting comparable measurement, count, ratio, or quantity
- `causal`: causality denied, downgraded to association, or limited by confounding
- `source_reliability`: resolution depends on attributable source authority or reliability
- `definition`: definition, scope, operationalization, or granularity changes meaning
- `counter_evidence`: explicit direct negation or counterexample to the same proposition when no more specific type applies

## Annotation schema

- clean: exactly one mapped type, empty missing_concept.
- partial: one or more mapped types and a non-empty missing_concept.
- unmappable: no mapped types and a non-empty missing_concept.

Every annotation also requires a non-empty rationale. Install completed files with `falsirag diag type-mappability install`; do not edit packet provenance files.

## Workflow

```bash
falsirag diag type-mappability prelabel --packet-dir <packet>
falsirag diag type-mappability install --packet-dir <packet> --role reviewer_a --annotator-id <id-a> --input <completed-a.jsonl>
falsirag diag type-mappability install --packet-dir <packet> --role reviewer_b --annotator-id <id-b> --input <completed-b.jsonl>
falsirag diag type-mappability install --packet-dir <packet> --role adjudicator --annotator-id <id-c> --input <completed-adjudication.jsonl>
falsirag diag type-mappability status --packet-dir <packet>
falsirag diag type-mappability analyze --packet-dir <packet> --output-dir <report-dir>
falsirag diag type-mappability verify --packet-dir <packet> --report-dir <report-dir>
```
