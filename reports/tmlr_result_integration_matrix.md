# TMLR result-integration matrix for WS4

This report turns the roadmap decision tree into a writing checklist for the
active TMLR mechanism-and-boundary paper. It is not a new empirical result and
does not alter F1--F10, G-F, G-B, G-P, label status, or held-out/test policy.

## Fixed baseline after WS3

- The paper line is mechanism-and-boundary, not end-to-end superiority.
- The completed positive evidence now includes the 60-item Qwen development
  typed-vs-untyped signal and the independently verified WS2 directional
  recurrence across Mistral, Gemma, and Llama under machine-audited labels.
- The completed negative evidence is still two preregistered RAMDocs development
  failures plus WS1 attribution: complete retrieval, partial-credit scoring, and
  a detection-only explanation do not rescue the original broad claim.
- WS2 is directional because G-P estimates low power for the three-family
  reproduction. A nonsignificant G-F cannot be written as evidence of absence.
- WS3 has no global pass/fail. Its verified public-dev boundary matrix is not
  human IAA, publication gold, or external blind validation.
- WS3 is near-null at the dataset level but has one preregistered positive
  external condition (Google CONFLICTS outdated information) and no no-conflict
  safety violation. This selects a weak A-line mechanism-and-boundary story,
  not a global transfer story.

## Outcome-to-paper mapping

| Branch | WS2 outcome | WS3 outcome | Main title claim | Abstract sentence to use | Required caveat |
|---|---|---|---|---|---|
| A-line | G-F passes, or combined typed-minus-untyped is positive with at least 2/3 families positive | At least one external boundary subgroup is directionally positive without a safety violation | Typed conflict control shows a reproducible mechanism signal and identifiable external conditions where it helps | "Across local development diagnostics, typed control is most useful when conflict evidence is retrievable, type-compatible, and safe to revise." | Still machine-audited/public-dev only; no held-out/test, no human gold, no end-to-end superiority |
| B-line | G-F passes or remains directionally positive, but not enough for strong cross-family language | WS3 is all null, underpowered, or mixed without clear matched hypotheses | The mechanism is real on the constructed Qwen diagnostic, but external transfer is tightly bounded | "The evidence supports a local typed-control mechanism while showing that external public-dev transfer is fragile and boundary-dependent." | Do not call null WS3 evidence of absence; emphasize G-P underpowering and RAMDocs upstream bottlenecks |
| C-line | WS2 is directionally inconsistent, nonpositive, or family-specific | Any WS3 result, including positives, is insufficient to generalize the Qwen effect | Typed conflict control is Qwen- and distribution-specific; the contribution is a negative boundary map plus infrastructure | "The positive typed-control signal does not survive the planned generalization checks, turning the contribution into a reproducible account of where the mechanism fails." | No cross-family claim; any WS3 positive is a hypothesis for future work, not rescue evidence |

## Current verified selection state

WS2 passes G-F with a combined typed-minus-untyped answer difference of
`+0.0645`, 3/3 positive family directions, stratified exact McNemar counts of
31 versus 9 (`p=0.000680`), and a family-cluster bootstrap 95% interval of
`[+0.0528,+0.0735]`. The independent release audit is valid. The C-line
family-inconsistency condition is therefore closed. WS3 is also independently
verified: WikiContradict has a typed-minus-untyped boundary-score difference of
`+0.0033` with 95% CI `[-0.0067,+0.0167]`, Google CONFLICTS has `-0.0007` with
95% CI `[-0.0271,+0.0262]`, and both Holm-adjusted McNemar values are `1.0`.
The preregistered Google outdated-information subgroup is positive (`+0.0040`)
and the no-conflict subgroup is safely noninferior (`-0.0042 >= -0.03`), while
the Wiki explicit/implicit hypotheses are contradicted. This selects the A-line
only in a weak, boundary-mapping sense: there is an identifiable public-dev
condition where typed control helps, but the dataset-level external transfer is
near null. The `directional_reproduction` and `directional_boundary_mapping`
ceilings remain binding.

## Section-level editing rules

| Paper section | A-line edit | B-line edit | C-line edit |
|---|---|---|---|
| Abstract | Add one sentence on cross-family directional support and one on the positive boundary subgroup(s) | Keep the current narrow Qwen mechanism sentence; add that WS3 found no robust external transfer under low power | Replace "observed boundary" with "failed generalization boundary" and foreground negative evidence |
| Introduction | Present FAR as a typed-control mechanism with scoped reproducibility | Present FAR as a useful local diagnostic mechanism whose transfer conditions are mostly unmet | Present FAR as a controlled falsification of a plausible typed-control mechanism |
| Experiments | Put WS2 before WS3, because family replication establishes whether the Qwen result generalizes at all | Put WS1/RAMDocs before WS3 to explain why null external results are expected | Put WS2 failure immediately after Qwen dev to prevent overclaiming |
| Discussion | "Use typed control when preconditions hold" | "Typed control is promising but boundary-limited" | "Typed control is not currently deployable as a general RAG improvement" |
| Limitations | Keep machine labels, public dev, low power, and no held-out/test as hard limits | Same, with added emphasis that nulls are underpowered | Same, with added emphasis that positive Qwen evidence is not transportable |

## Evidence insertion checklist

- Insert WS2 only after `diagnostics/family_dev_v1/manifest.json` exists and
  `far.experiments.evidence_family_dev verify` passes.
- The WS2 insertion condition is now satisfied; its release manifest and
  independent audit both pass.
- Insert WS3 only after `diagnostics/boundary_v1/manifest.json` exists,
  `reports/boundary_matrix.md` exists, and `far.experiments.evidence_boundary verify`
  passes.
- The WS3 insertion condition is now satisfied; its release manifest,
  boundary matrix, and independent audit all pass.
- Never convert WS2 or WS3 machine/public-dev evidence into human IAA,
  publication gold, or external blind testing.
- Never use WS3 subgroup positives to reopen RAMDocs G-A or to claim end-to-end
  advantage.
- Keep the AAAI strict profile inactive unless real independent human
  annotation, adjudication, and external custody become available.
