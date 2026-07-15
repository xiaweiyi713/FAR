# FAR Single-Author Machine-Audited Diagnostic Report

Generated from the frozen diagnostic evidence plus the registered P14 train study; refreshed on 2026-07-15.

## Technical summary

FAR is complete enough to support a single-author, machine-audited synthetic-benchmark diagnostic. The automated readiness gate passes all four diagnostic requirements: the 300-sample candidate benchmark is structurally valid; the machine-consensus audit is complete; the 11-method local Qwen development suite is complete on the 60-sample dev split; and the local 58-sample test bundle is gold-free and structurally audited.

The evidence supports a narrow diagnostic claim: typed conflict control is useful as a development-set mechanism signal. FAR reaches 0.797 whole-answer correctness and 0.983 counter-evidence recall on the local Qwen dev suite, above the six transparent baselines on those two metrics. Against the untyped FAR ablation, FAR improves answer correctness by 7.83 points and revision accuracy by 21.67 points. A post-hoc metric audit adds raw revision-delta F1 0.145 and action-conditioned typed delta F1 0.096. A second frozen trace audit finds mean trace delta F1 0.082: only 15/60 traces completely cover the construction target, 19/60 are off-target, and 12/60 make no lexical target edit. P13 then shows that preserving the erroneous initial answer scores 0.978 whole-answer F1 with zero target edits, a reference-dependent three-arm envelope improves delta F1 over always typed by only 0.016, and confidence at least 0.90 does not select higher-fidelity traces. P14 prospectively tests a reference-free post-generation gate on 120 fresh train rows: calibration selects 15/60, evaluation accepts 18/60, and selected revision-delta F1 is 0.455 versus 0.220 for always typed, an enrichment of +0.235 with 95% interval [+0.103,+0.386]. Typed still does not dominate the broad baseline delta ranking, and P14 acts after generation with construction-derived outcome scoring. The combined revision evidence is therefore mixed and bounded rather than proof that every FAR submodule helps, revision is generally reliable, inference is saved, or semantic/deployment safety has been established.

This report does not complete the strict AAAI submission path. The benchmark remains construction-derived and machine-audited rather than independently human-adjudicated; the local test bundle is not externally held blind evaluation; and the six-way baseline ranking plus P11 delta audit come from the Qwen diagnostic. A separate three-family typed/untyped sensitivity exists, but it is post-hoc for delta and does not constitute a final external multi-model matrix. These boundaries are intentional and enforced by the release verifiers.

## Key findings with visual evidence

### FAR retrieves counter-evidence more reliably than the baselines in the local diagnostic

FAR has the highest counter-evidence recall in the 60-sample Qwen dev suite: 0.983 with a bootstrap interval of [0.950, 1.000]. The closest transparent baseline is the CounterRefine-style reproduction at 0.883. This supports the mechanism-level claim that falsification-guided retrieval is finding the planted counter-evidence in this controlled setting.

![Counter-evidence recall by method](https://raw.githubusercontent.com/xiaweiyi713/FAR/artifacts-v1/diagnostics/solo_v1/experiments/artifacts/counter_evidence_recall.png)

The comparison is diagnostic rather than publication-final: it uses construction-derived labels on the dev split and should be rerun on adjudicated gold before any main-paper table is filled.

| Method | Samples | Answer | Delta F1 | Typed delta | Typed conflict F1 | Revision accuracy | Counter recall | Unsupported |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| FAR | 60 | 0.797 | 0.145 | 0.096 | 0.420 | 0.217 | 0.983 | 0.017 |
| Vanilla RAG | 60 | 0.725 | 0.264 | 0.000 | 0.000 | 0.000 | 0.667 | 0.267 |
| Multi-query RAG | 60 | 0.701 | 0.226 | 0.000 | 0.000 | 0.000 | 0.817 | 0.133 |
| Reflective RAG | 60 | 0.678 | 0.205 | 0.000 | 0.000 | 0.000 | 0.750 | 0.183 |
| CRAG-style reproduction | 60 | 0.772 | 0.307 | 0.000 | 0.000 | 0.000 | 0.667 | 0.267 |
| Self-RAG-style reproduction | 60 | 0.751 | 0.256 | 0.000 | 0.000 | 0.000 | 0.817 | 0.150 |
| CounterRefine-style reproduction | 60 | 0.710 | 0.261 | 0.000 | 0.000 | 0.000 | 0.883 | 0.083 |

Source: `diagnostics/solo_v1/experiments/artifacts/main_results.csv`.

### Typed conflict control is the clearest supported ablation result

The strongest ablation evidence is the paired typed-versus-untyped comparison. FAR keeps counter-evidence recall equal to the untyped ablation but improves answer correctness, typed conflict F1, revision accuracy, and revision-action behavior. This is the main claim that the current dev evidence can support.

| Variant | Samples | Answer | Delta F1 | Typed delta | Typed conflict F1 | Revision accuracy | Counter recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| FAR | 60 | 0.797 | 0.145 | 0.096 | 0.420 | 0.217 | 0.983 |
| Minus typed conflict | 60 | 0.719 | 0.093 | 0.000 | 0.000 | 0.000 | 0.983 |
| Minus refutation query | 60 | 0.826 | 0.194 | 0.124 | 0.429 | 0.267 | 0.967 |
| Minus boundary query | 60 | 0.801 | 0.166 | 0.104 | 0.418 | 0.233 | 0.983 |
| Minus typed revision | 60 | 0.873 | 0.072 | 0.000 | 0.423 | 0.000 | 0.983 |

Source: `diagnostics/solo_v1/experiments/artifacts/ablation_results.csv`.

The mixed ablations matter. Removing refutation or boundary queries does not hurt answer correctness on this dev set. Removing refutation queries raises raw delta F1 from 0.145 to 0.194, with a paired interval that excludes zero. Removing typed revision raises answer correctness while lowering raw delta F1 to 0.072 and zeroing action-conditioned revision metrics. This supports typed control as an inspectable mechanism, but it rules out a monotonic benefit claim for every query or revision component.

### Revision works, but the absolute rate remains a limitation

Only FAR exposes non-zero typed revision accuracy among the seven method-level diagnostic runs, and the category breakdown is uneven. Its raw delta F1 is below all six broad baselines: CRAG-style reaches 0.307 and Vanilla reaches 0.264 versus FAR at 0.145. Those baselines have zero typed delta because they do not expose the expected typed action, but their raw lexical edits must remain visible. The chart is useful mostly because it keeps the limitation visible: FAR is not yet a high-recall automatic correction system.

![Typed conflict revision accuracy by category](https://raw.githubusercontent.com/xiaweiyi713/FAR/artifacts-v1/diagnostics/solo_v1/experiments/artifacts/typed_conflict_breakdown.png)

The current best interpretation is mechanism evidence, not deployment readiness. FAR can expose a typed revision trace and sometimes make the right typed correction, but the next empirical bottleneck is improving revision reliability after conflict detection.

### The trace artifact makes the mechanism inspectable

The diagnostic release includes a concrete before/after trace. This is important because FAR's novelty claim depends on typed control being observable across retrieval and revision, not hidden in an end-to-end answer score.

![Example revision trace](https://raw.githubusercontent.com/xiaweiyi713/FAR/artifacts-v1/diagnostics/solo_v1/experiments/artifacts/revision_trace_case.png)

The example should be used as a qualitative audit case only. It is not a substitute for adjudicated aggregate metrics.

### External FEVER transfer is honest but limited

The external FEVER diagnostic evaluates binary conflict detection on 100 visible SUPPORTS/REFUTES claim-evidence pairs. The binary labels and gold evidence inherit human annotation from FEVER, while FAR's typed sampling buckets remain machine-generated and non-gold. The VeraRAG NLI detector improves recall over the heuristic detector, 0.40 versus 0.30, and improves F1, 0.533 versus 0.462, but both detectors have the same 0.72 accuracy. The paired accuracy difference is 0.000 with a 95% bootstrap interval of [-0.050, 0.050], and exact McNemar p is 1.000.

| Detector | Samples | Accuracy | Precision | Recall | F1 | TP / FP / FN / TN |
|---|---:|---:|---:|---:|---:|---|
| Heuristic | 100 | 0.720 | 1.000 | 0.300 | 0.462 | 12 / 0 / 28 / 60 |
| VeraRAG NLI | 100 | 0.720 | 0.800 | 0.400 | 0.533 | 16 / 4 / 24 / 56 |

Source: `diagnostics/fever_binary_v1/report.json`. FEVER source references: [official FEVER dataset](https://fever.ai/dataset/fever.html) and [copenlu/fever_gold_evidence](https://huggingface.co/datasets/copenlu/fever_gold_evidence).

This result is valuable precisely because it is not overpolished. It shows limited detector transfer and should remain frozen rather than tuned after inspection.

## Scope, data, and metric definitions

This report covers the `single_author_machine_audited_diagnostic` profile, not the strict AAAI profile.

Included evidence:

- 300 construction-derived FalsiRAG-Bench candidate rows across five balanced categories.
- 175 corpus documents.
- 182 train, 60 dev, and 58 local test-input rows with zero dependency-group split leakage.
- 300-row machine-consensus audit with Qwen2.5 machine preannotation and deterministic weak-label signals.
- 11 complete local Qwen dev runs: FAR, six baselines, and four ablations.
- A gold-free local test-bundle technical audit.
- A separate 100-pair FEVER binary transfer diagnostic.
- A preregistered 120-row, dependency-group-disjoint P14 train-only selective-acceptance study.

Excluded evidence:

- Independent human gold labels.
- Human inter-annotator agreement.
- Externally held blind test scores.
- Final multi-model generality.
- Publication-ready AAAI empirical claims.

Metric definitions:

- **Answer correctness**: soft answer-level correctness computed by the project evaluator over the dev split.
- **Revision-delta precision/recall/F1**: post-hoc token-multiset agreement between the edits made from the initial answer and the edits required by the construction reference. Unchanged erroneous answers score zero; extra edits reduce precision. This is lexical edit fidelity, not semantic correctness.
- **Typed revision delta F1**: revision-delta F1 retained only when the declared revision action matches the construction-derived expected action; otherwise zero.
- **Typed conflict F1**: F1 for predicted typed conflict behavior against the construction-derived reference.
- **Revision accuracy**: whether the selected revision behavior matches the expected construction-derived revision action and revised answer conditions.
- **Counter-evidence recall**: whether expected falsifying evidence is retrieved or selected.
- **Unsupported claim rate**: share of evaluated samples where the output retains unsupported claims.
- **Overclaim reduction**: reduction in overclaiming among rows where overclaim behavior is measurable.

All intervals in the diagnostic artifacts are bootstrap intervals from the project evaluator; they are not human-label uncertainty intervals.

## Methodology

### Machine-consensus annotation audit

The machine-consensus audit treats construction labels as the reference to be checked, not as human gold. Two independent machine signals are compared against those references:

- Qwen2.5 LLM preannotation: 299 non-fallback rows out of 300; 0.003 fallback rate; 117 exact joint matches on non-abstained rows.
- Deterministic weak supervision: 211 non-abstained rows out of 300; 121 exact joint matches on non-abstained rows.

The resulting disposition is:

| Disposition | Rows |
|---|---:|
| Machine-confirmed | 178 |
| Machine-disputed | 122 |

The 122 disputed rows remain in the evidence bundle and must be disclosed. They are not silently relabeled, filtered, or upgraded to gold.

For limited future review time, the derived priority table
[`reports/solo_human_review_priority.csv`](solo_human_review_priority.csv)
lists all 122 machine-disputed rows in a deterministic review order. The table
contains sample IDs, categories, reference conflict/action fields, machine
signal fields, and a triage reason; it intentionally omits revised-answer text
and does not claim any human or gold-label status.

### Local development evaluation

The local dev suite evaluates 11 matched runs on 60 dev samples. Every run has tracked predictions, a run identity, a run manifest, scores, and an evaluation report. The suite manifest SHA is:

```text
2b8c1330d53670d50817950444b7ef3f7218956f236d8904831005420cf2b9fe
```

Key prediction fingerprints:

```text
FAR predictions:
992a4cf027db5491feef2a57210d8a9395be61798c0ff84b29760d495bc96b56

Minus typed conflict predictions:
26e6ae372d54a8dea30dd8a892a68a4ba425d91bf341366b21ce309d6d928658

CounterRefine-style predictions:
483f08eca2c34431ac81e87dcac2277433afc5e24e858475742d5c162a6b8c57
```

### External FEVER diagnostic

The FEVER diagnostic is intentionally narrower than FAR. It tests binary conflict detection only:

- Positive class: inherited FEVER `REFUTES` claim-evidence pairs.
- Negative class: inherited FEVER `SUPPORTS` claim-evidence pairs.
- Typed buckets: machine sampling labels used only for descriptive slicing.

No full FAR pipeline, typed revision, or blind-test protocol is evaluated on FEVER in this report.

## Limitations, uncertainty, and robustness checks

What is already guarded by code:

- `falsirag-solo-release verify diagnostics/solo_v1` recomputes the 69-file evidence bundle, run/report/score bindings, and non-publication claims.
- `falsirag-solo-readiness` rejects the solo profile if the benchmark, machine audit, complete local dev suite, or gold-free test-bundle audit is missing.
- `falsirag-eval-fever-binary verify --data-dir bench/external/fever_pair_candidates_v1 diagnostics/fever_binary_v1` recomputes FEVER source fingerprints, detector predictions, and paired statistics.
- `falsirag-submission-readiness` remains a separate fail-closed gate for the strict AAAI path.
- `falsirag diag revision-trace-audit verify` recomputes every Qwen/WS2 trace row, prediction fingerprint, paired interval, and post-hoc boundary without model calls.

What remains uncertain:

- The construction-derived labels may encode design assumptions from the benchmark builder.
- Machine agreement can reveal suspicious rows but cannot replace independent annotation or adjudication.
- The broad-baseline and component ranking is a single-Qwen diagnostic. The separate three-family typed/untyped delta recurrence is post-hoc and construction-dependent, not a final external-provider result.
- Trace alignment is lexical and construction-reference-dependent. It cannot identify a semantic repair, valid paraphrase, or causal action oracle.
- The local test bundle has been sanitized but has not been externally held or one-shot scored by a custodian.
- FEVER transfer is binary and visible; it does not validate typed conflict detection or revision.

## Recommended next steps

1. Use this report as the single-author public deliverable if no annotators are available.
2. Keep [`reports/solo_human_review_priority.csv`](solo_human_review_priority.csv) as an archival triage aid for an optional future strict-human branch; it is not an active dependency or blocker.
3. The relaxed single-author paper may use these complete dev results only with the machine-audited, non-blind, Qwen-suite and directional cross-family qualifiers plus negative ablations enforced by `falsirag-solo-paper-readiness`; the strict AAAI profile remains pending.
4. Treat revision reliability as the next prospective engineering target rather than tuning on the now-visible trace audit. Any new repair policy requires a new preregistered development branch and fresh, separately frozen evidence.
5. Do not tune on the frozen FEVER 100-pair diagnostic. If external development is needed, create a separate development split and reserve a new frozen evaluation slice.
6. Rotate any exposed API keys before cloud experiments. The repository should only use environment variables or local ignored secrets.

## Further questions

- Can a future independently sourced benchmark separate construction-reference artifacts from genuine revision failures without reopening the inactive human branch?
- Can typed revision be improved without sacrificing the answer-correctness gains seen in the `minus_typed_revision` ablation?
- Does the post-hoc revision-delta direction survive on a separately frozen external distribution rather than only the current constructed development set?
- Which external dataset can provide typed conflict labels without post-hoc tuning on the FEVER diagnostic slice?

## Reproducibility commands

Run from the repository root:

```bash
uv run falsirag-solo-release verify diagnostics/solo_v1

uv run falsirag-eval-fever-binary verify \
  --data-dir bench/external/fever_pair_candidates_v1 \
  diagnostics/fever_binary_v1

uv run falsirag diag revision-trace-audit verify
```

To rebuild the solo readiness object, use the original ignored evidence locations documented in `diagnostics/solo_v1/README.md`. The tracked public evidence check is `falsirag-solo-release verify`.
