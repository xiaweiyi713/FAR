# FAR Project Status Snapshot

This snapshot is generated from tracked repository evidence. It is a status
ledger for the project proposal, not a submission waiver.

## Summary

| Track | Status | Meaning |
|---|---|---|
| Single-author machine-audited diagnostic | `true` | public single-author machine-audited diagnostic |
| Single-author machine-audited paper | `true` | Narrow typed-control mechanism claim with mandatory negative ablations |
| Cross-family jury + external validation paper | `false` | Preregistered external upstream-label validation plus cross-family LLM jury |
| Strict AAAI submission | `false` | Requires real external evidence and cannot be satisfied by templates or machine labels |

## Current evidence

| Evidence item | Status |
|---|---|
| Candidate benchmark | valid=`true`, samples=300, counter-evidence recall=0.91 |
| Solo diagnostic release | valid=`true`, files=69, methods=11 |
| FEVER binary transfer diagnostic | valid=`true`, publication_ready_main_result=`false` |
| Review-priority table | valid=`true`, rows=122, dispositions=machine_disputed |
| Reader-facing reports | valid=`true` |

## Strict submission blockers

These blockers come from `submission/evidence.template.json` and are expected
until real external evidence is supplied:

- `human_annotation`
- `adjudicated_dev_matrix`
- `final_blind_bundle`
- `external_blind_returns`
- `blind_test_attestation`
- `trusted_test_scoring`
- `release_archive`
- `human_paper_review`

External-role blockers:

- `adjudicated_dev_matrix`
- `blind_test_attestation`
- `external_blind_returns`
- `final_blind_bundle`
- `human_annotation`
- `human_paper_review`
- `trusted_test_scoring`

## Claim boundary

The completed local track may be described as a public single-author,
machine-audited diagnostic; it must not be described as human gold. The 2+4
track replaces the unavailable human gate only for its explicitly named profile;
it remains LLM jury + author adjudication, not human IAA or externally held
blind-test evidence.
