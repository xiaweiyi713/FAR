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
   ablations, and the original five baselines have finished 60/60 with zero
   errors. The FAR prediction SHA is
   `992a4cf027db5491feef2a57210d8a9395be61798c0ff84b29760d495bc96b56`.
   The typed-vs-untyped dev diagnostic supports typed conflict control, but the
   other ablation effects are mixed and must not be overstated. The sixth
   CounterRefine-style closest-neighbor control is running separately under the
   same Qwen config before a reports-only merge. Full DeepSeek V4-Flash and
   Qwen3.7 Plus (2026-05-26) runs also remain;
4. final validated six-baseline reports, paired confidence intervals, McNemar
   values, and any typed-ablation claim that survives adjudicated gold/test;
5. named authors, affiliations, and the human-required AAAI policy review.

Do not replace `PENDING-EMPIRICAL-RUN` cells until result bundle validation
passes. Diagnostic smoke figures under `outputs/` are not submission figures.
