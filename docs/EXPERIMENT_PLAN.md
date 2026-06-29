# Experiment Matrix and Gates

Run FAR, five baselines, and four ablations on train/dev before touching test.
Target backends are DeepSeek V4-Flash, Qwen3.7 Plus (2026-05-26), and local Qwen 3.5 9B; record exact
service/model identifiers and immutable local model hashes where possible.
Use `falsirag-suite` for the default run path so every prediction bundle is
evaluated, validated, fingerprinted, and converted into tables/figures from the
same recorded reports.

Baselines are Vanilla RAG, Multi-query RAG, Reflective RAG, a closed-corpus
CRAG-style reproduction, and an inference-time Self-RAG-style reproduction.
The latter two are not the official trained systems and must retain those labels
in every table.

Go/no-go gates:

1. Candidate benchmark validation and counter-evidence recall at least 0.80.
2. Double annotation, adjudication, and all reported mean kappas at least 0.60.
3. FAR versus Vanilla/Reflective on paired dev inference.
4. Typed versus untyped paired dev inference. If not supported, rewrite the
   central claim as a diagnostic or negative result; do not shop test prompts.
5. Freeze code/config, transfer test gold to an independent custodian, then run
   test once. Report all failures and intervals.

The suite binds comparison direction explicitly: FAR and other baselines are
measured against Vanilla, and each `minus_*` report is measured against full
FAR on identical sample IDs. Reports retain both method names and the baseline
score fingerprint; comparison fails on benchmark or row-metadata mismatch.
