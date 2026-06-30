# Paper Status

The anonymous AAAI-27 draft uses the official 2027 Author Kit. Method,
benchmark protocol, baselines, ablations, metrics, limitations, and
reproducibility text are complete. The official checklist is filled against the
current evidence; items that depend on final experiments remain `partial` or
`no` and must be revisited before submission.

The following cannot be truthfully completed by code generation:

1. two independent annotations and adjudication for 300 candidate items;
2. an externally held blind test;
3. the remaining matched Qwen3.5 baselines/ablations and corrected-code rerun,
   plus full DeepSeek V4-Flash and Qwen3.7 Plus (2026-05-26) runs (the original
   Qwen FAR dev method finished 60/60 but is diagnostic-only);
4. final paired confidence intervals, McNemar values, and typed-ablation claim;
5. named authors, affiliations, and the human-required AAAI policy review.

Do not replace `PENDING-EMPIRICAL-RUN` cells until result bundle validation
passes. Diagnostic smoke figures under `outputs/` are not submission figures.
