# External Action Packet

This is the shortest truthful path from the current machine-seeded diagnostic
state to a submission-ready FAR result. The commands fail closed: machine
preannotations, partial runs, dirty source trees, unbound returns, and local
test dry runs cannot satisfy the final gate.

## 1. Human annotation owner

Give two independent reviewers only their respective blind packet, README, and
`docs/HUMAN_ANNOTATION_PROTOCOL.md`. The safest file-based handoff is generated
per reviewer:

```bash
uv run falsirag-annotate-packet reviewer-handoff \
  --packet-dir outputs/annotations/falsirag_packet_v1 \
  --output-dir outputs/annotations/reviewer_a_handoff \
  --reviewer-id reviewer_a \
  --overwrite
```

Repeat with `reviewer_b`. The handoff builder refuses filled templates and
excludes the other reviewer, packet manifest, source benchmark, and machine
predictions.

After both files are frozen, an adjudicator fills `adjudications.jsonl` and
compiles. Check packet progress at every handoff:

```bash
uv run python -m bench.build.annotate_packet status \
  --packet-dir outputs/annotations/falsirag_packet_v1 \
  --data-dir bench
```

Do not generate the adjudicator project until `reviewers_complete:true` and
`ready_to_export_adjudication_label_studio:true`. If using Label Studio, then
import and install the resulting adjudication:

```bash
uv run falsirag-auto-annotate adjudication-label-studio \
  --packet-dir outputs/annotations/falsirag_packet_v1 \
  --output-dir outputs/annotations/label_studio_adjudicator

uv run falsirag-auto-annotate adjudication-label-studio-import \
  --packet-dir outputs/annotations/falsirag_packet_v1 \
  --label-studio-json outputs/annotations/label_studio_adjudicator/project-export.json \
  --output-dir outputs/annotations/label_studio_adjudicated \
  --adjudicator-id adjudicator_1

uv run python -m bench.build.annotate_packet install-adjudication \
  --packet-dir outputs/annotations/falsirag_packet_v1 \
  --adjudication-file outputs/annotations/label_studio_adjudicated/adjudications.jsonl \
  --adjudicator-id adjudicator_1
```

Then compile:

```bash
uv run python -m bench.build.annotate_packet compile \
  --data-dir bench \
  --packet-dir outputs/annotations/falsirag_packet_v1 \
  --output-dir outputs/annotations/falsirag_adjudicated_v1
```

Do not continue unless `annotation_report.json` records two distinct reviewers,
`adjudicated:true`, `agreement_gate_passed:true`, and every mean Cohen's kappa
is at least `0.60`. The compiler also freezes the raw reviewer and adjudication
files under `annotation_evidence/`; both readiness and trusted scoring recompute
IAA and compiled labels from this archive rather than trusting report numbers.
The status command should report `ready_to_compile:true` immediately before
compilation; otherwise resolve the listed blanks, invalid rows, fingerprint
mismatches, or visible-field mismatches first.

## 2. Experiment owner

Rotate the previously exposed DeepSeek key; never reuse or record it. Export the
rotated DeepSeek and DashScope keys only in the remote shell. Run the complete
11-method dev matrix for DeepSeek V4-Flash, Qwen3.7 Plus 2026-05-26, and local
Qwen3.5 9B against the adjudicated directory. Large caches, outputs, and models
remain under `/mnt/d` on `windows-gpu`.

Formal run identities now bind the implementation hash and exact Git commit and
record whether the worktree was dirty. Start final runs only from one clean,
frozen commit. A dirty or commit-mismatched run is rejected by the submission
gate.

## 3. Release and handoff owner

On the frozen commit, run `bash scripts/release_check.sh`, then build a new
gold-free bundle from adjudicated data and package it for the custodian:

```bash
uv run falsirag-build-blind-bundle \
  --data-dir outputs/annotations/falsirag_adjudicated_v1 \
  --output-dir outputs/handoff/falsirag_blind_test_v1

uv run falsirag-build-blind-bundle audit \
  --bundle-dir outputs/handoff/falsirag_blind_test_v1

uv run falsirag-build-blind-bundle package \
  --bundle-dir outputs/handoff/falsirag_blind_test_v1 \
  --output-dir outputs/handoff/custodian_deepseek_handoff \
  --config experiments/configs/deepseek.yaml \
  --frozen-commit "$(git rev-parse HEAD)" \
  --overwrite
```

Never hand off `falsirag_blind_test_technical_v1`. The package command rejects
technical dry-run bundle names by default, recursively checks for forbidden
gold/provenance keys, and includes only the gold-free bundle, selected config,
run sheet, and manifest. Send the external custodian only this package, the
frozen release/repository, environment instructions, and credentials through
environment variables.

## 4. External custodian

Run each frozen model suite once with `--split test --allow-test`. Return the
three complete unscored suite directories and logs. Do not request gold, retry
because of output quality, or edit benchmark files. Record any operational
restart or failure.

The custodian and trusted scorer then fill
`submission/blind_test_attestation.template.json`. They must be distinct roles;
the attestation binds the frozen commit plus SHA-256 hashes of the final bundle
manifest and all three return manifests.

## 5. Trusted scorer

Score each frozen return against the adjudicated benchmark. For example:

```bash
uv run falsirag-score-blind-return \
  --model-id deepseek_v4_flash \
  --data-dir outputs/annotations/falsirag_adjudicated_v1 \
  --blind-bundle-dir outputs/handoff/falsirag_blind_test_v1 \
  --return-dir outputs/returned/deepseek_test_suite \
  --attestation submission/blind_test_attestation.json \
  --output-dir outputs/final/deepseek_test_scored
```

Repeat with model IDs `qwen_3_7_plus` and `qwen_3_5_9b`. The scorer verifies
gold-free execution, all 11 methods, full test IDs, prediction and identity
fingerprints, clean/frozen commit provenance, role separation, and one-shot
attestation before producing paired reports and final tables/figures. The output
directory must be empty, preventing silent replacement of an earlier score. The
generated `artifact_manifest.json` must report `publication_ready:true`,
`test_only:true`, and strict requirements for both publication-ready and
test-only inputs. It must also carry the same report fingerprints and benchmark
fingerprint as the scored-suite manifest; `falsirag-submission-readiness`
rejects final artifacts that were rebuilt from dev, partial, diagnostic,
mixed-split, or cross-benchmark reports.

## 6. Paper and final gate owner

Copy `submission/evidence.template.json` to an ignored working file, replace
every path and attestation field with the real artifacts, fill the final paper
cells, and have a human review AAAI policy, authorship, and empirical claims.
After the review, bind it to the exact reviewed paper sources:

```bash
uv run falsirag-submission-readiness --print-paper-fingerprints
```

Copy the printed map into `human_review.paper_source_sha256`. If any paper
source changes after review, rerun the human review and refresh the
fingerprints; stale review hashes fail the final gate. The paper reviewer must
also be independent from the experiment roles already bound by the evidence
file: the final gate rejects a `human_review.reviewer_id` that matches any
annotator, the adjudicator, the blind custodian, or the trusted scorer.
Then run:

```bash
uv run falsirag-submission-readiness \
  --evidence submission/evidence.json \
  --output build/submission-readiness.json
```

Exit code zero and `ready:true` are required. The gate independently checks the
candidate benchmark, human annotation/IAA, three adjudicated dev suites, final
blind bundle, three externally returned suites, bound role attestation, three
trusted-scored test suites, release archive, and human paper review. A status
snapshot may be generated before completion with `--allow-incomplete`; it is
not a waiver of any failed gate.
