# Experiment Matrix and Gates

Run FAR, five baselines, and four ablations on train/dev before touching test.
Target backends are DeepSeek Chat, Qwen Plus, and local Qwen 2.5 7B; record exact
service/model identifiers and immutable local model hashes where possible.

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
