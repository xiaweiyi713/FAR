# Paper Status

The anonymous AAAI-27 draft uses the official 2027 Author Kit. Method,
benchmark protocol, baselines, ablations, metrics, limitations, and
reproducibility text are complete. The official checklist is filled against the
current evidence; items that depend on final experiments remain `partial` or
`no` and must be revisited before submission.

The following cannot be truthfully completed by code generation:

1. two independent annotations and adjudication for 300 candidate items;
2. an externally held blind test;
3. the remaining matched model matrix. Corrected Qwen3.5 dev FAR, all four
   ablations, and all six baselines have finished 60/60 with zero errors. The
   FAR prediction SHA is
   `992a4cf027db5491feef2a57210d8a9395be61798c0ff84b29760d495bc96b56`.
   The CounterRefine-style closest-neighbor prediction SHA is
   `483f08eca2c34431ac81e87dcac2277433afc5e24e858475742d5c162a6b8c57`, and
   the reports-only suite manifest SHA is
   `dccd854c74d3eec109fb879e0c0d1fb838763694adc655b24eb83219807c4467`.
   The typed-vs-untyped dev diagnostic supports typed conflict control, but the
   other ablation effects are mixed and must not be overstated. These Qwen dev
   results remain machine-seeded diagnostics (`publication_ready:false`). Full
   DeepSeek V4-Flash and Qwen3.7 Plus (2026-05-26) runs also remain;
4. final validated six-baseline reports, paired confidence intervals, McNemar
   values, and any typed-ablation claim that survives adjudicated gold/test;
5. named authors, affiliations, and the human-required AAAI policy review.

For a single-author diagnostic release, the repository now has a separate
automated endpoint. `falsirag-machine-consensus` audits the controlled
construction labels with fingerprint-bound Qwen2.5 and deterministic weak
signals, and `falsirag-solo-readiness` currently passes the benchmark,
machine-audit, complete 11-method Qwen dev suite, and gold-free local test
bundle gates. The complete non-publication evidence is tracked under
`diagnostics/solo_v1/` and independently rechecked by
`falsirag-solo-release verify`. The reader-facing technical synthesis is
tracked at `reports/single_author_diagnostic_report.md`. This supports a
machine-audited synthetic-benchmark report, not the strict human/external
claims required by the current AAAI submission draft.

A separate frozen FEVER binary transfer diagnostic is also public under
`diagnostics/fever_binary_v1/`. The human-annotated upstream FEVER labels yield
0.72 accuracy for both the heuristic and VeraRAG NLI detectors; NLI raises
recall from 0.30 to 0.40 but does not improve paired accuracy (McNemar
`p=1.0`). This negative result exposes limited detector transfer. It does not
evaluate the full FAR pipeline, and the machine-generated typed buckets remain
non-gold, so these values must not populate the AAAI main table.

Do not replace `PENDING-EMPIRICAL-RUN` cells until result bundle validation
passes. Diagnostic smoke figures under `outputs/` are not submission figures.
The final handoff is now machine-auditable through
`falsirag-score-blind-return` and `falsirag-submission-readiness`; the latter
must report `ready:true` after human policy review, not merely pass unit tests.
