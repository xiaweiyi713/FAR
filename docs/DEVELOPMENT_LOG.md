# Development Decision Log

## 2026-06-29: formal retrieval/conflict stack cutoff

Scope: the 60-item development split only. The held-out test inputs and labels
were not used. Both runs disabled the LLM and are systems diagnostics, not paper
results.

The initial complete run retained five reranked documents per typed query. It
recovered counter-evidence well but exposed many irrelevant documents to every
claim-level conflict check. Inspection also found that the FAR adapter aligned a
VeraRAG graph edge against the whole evidence document instead of the specific
evidence sub-claim named by the edge. This produced cross-slot conflicts such as
comparing different measurements mentioned in one document.

The revised diagnostic:

- retains two reranked documents per support/refutation/boundary query;
- aligns graph conflicts to the edge's evidence sub-claim;
- treats year-only numerical graph edges as temporal only when the paired
  sub-claim supports that interpretation;
- selects the sample-level revision action by trace confidence with a fixed
  semantic tie-break, without benchmark-template prefixes; and
- reports every detected conflict type for Conflict F1 while recording the
  primary type separately for action analysis.

| Development metric | Initial top-5 | Revised top-2 |
|---|---:|---:|
| Counter-evidence recall | 0.950 | 0.950 |
| Evidence precision | 0.056 | 0.169 |
| Evidence recall | 0.958 | 0.958 |
| Typed conflict F1 | 0.328 | 0.361 |
| Typed conflict correct (recall-like) | 0.500 | 0.433 |
| Any conflict detected | 0.967 | 0.883 |
| Revision action correct | 0.283 | 0.350 |
| Revision accuracy | 0.267 | 0.283 |
| Answer correctness | 0.880 | 0.903 |

Decision: retain top-2. It triples evidence precision, improves the multi-label
typed F1 and action selection, and does not reduce counter-evidence/evidence
recall. The reduced any-conflict and typed-correct rates are recorded rather
than hidden. Temporal and entity action selection remain weak and must be tested
with the frozen LLM-backed systems; this diagnostic cannot support a positive
paper claim.

Revised run evidence:

- run status: complete, 60/60;
- run signature: `7b18e1168c22df242dce6f69210613a7df2e4ddbbde7d1f983f2bebb732b9b95`;
- implementation SHA-256: `734d6f73ac06cd038da20db943655ffb68e835daa9d36e0d85e8837b304021e5`;
- benchmark SHA-256: `c5bd988f60646bde33d62f654ddb456d2c2c1279175bee92ef503f362addbd8f`;
- corpus SHA-256: `cca5f62db0fbb51e1bae8111ea85fe169fba7be5a8e63847a9c1c048cdae25cd`;
- predictions SHA-256: `1d81945bd3ecadc98b40e988a69620d92e938e414f652e11362d0cc0eee14fff`;
- evaluation-report SHA-256: `ae477dd8e2ee6ec8e5ad988f456cf7eb13c717c3f220e0a30ac2aa14ee2de981`.

Three intermediate runs were intentionally interrupted after their targeted
failure modes were understood. They are not complete result bundles and are not
used in any table.

After this diagnostic, the runner added Ollama digest capture to the run
signature. That provenance-only change does not alter retrieval, conflict, or
revision behavior; the final repository gates include a fresh smoke run on the
post-change implementation.
