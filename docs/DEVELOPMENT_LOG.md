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

## 2026-06-30: Windows GPU and D-drive execution contract

The configured WSL host has an RTX 4060 Laptop GPU with 8,188 MiB VRAM. Its C:
drive had only 16 GiB free, so no FAR model, runtime, checkout, or generated
experiment output was intentionally placed there. The verified D:-backed
layout is:

- `/mnt/d/FAR-workspace/{FAR,VeraRAG}` for working trees;
- `/mnt/d/FAR-models/{huggingface,ollama}` for pinned model assets;
- `/mnt/d/FAR-runtime/ollama` for the Ollama 0.30.11 runtime;
- `/mnt/d/FAR-runtime/python/site-packages` for missing optional Python wheels;
  and
- `/mnt/d/FAR-outputs` for logs, checkpoints, and result bundles.

`scripts/windows_gpu_env.sh` establishes these paths. Three Hugging Face
snapshots were copied from the existing Mac cache and verified readable at the
revisions in the formal configs. Qwen3.5 was pulled to D: and resolved to:

- tag: `qwen3.5:9b`;
- digest: `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`;
- reported parameters/quantization: 9.7B, Q4_K_M; and
- stored size: 6,594,474,711 bytes.

Because Qwen occupied about 7.2/8.2 GiB in a real generation, the open-model
config keeps dense retrieval, reranking, and NLI in a CPU-only FAR process while
the independently started Ollama server retains 100% GPU placement. Cloud-model
configs can use CUDA for retrieval because no local generator competes for
VRAM. This is an execution placement decision; model identities and retrieval
semantics remain shared.

Two diagnostics closed the host setup gate without creating paper results:

| Diagnostic | Result | Run/prediction identity |
|---|---|---|
| Formal CUDA retrieval/conflict stack, LLM disabled | complete, 5/5, 0 errors | run `f8ab8c37b126b85c46f326f892320a4b9ce68a6eab0a80eda2a7c82b90d0c544`; predictions `c650eb6381803b04c1978990484413862369a7a85dc67998927c39cb14194863` |
| Qwen3.5 end-to-end FAR | complete, 1/1, 0 errors, two revision traces | run `a02fc4573ac583a1ed738f5a7a102395834bea9b10ef4737d5f786f000236548`; predictions `6b6e7b775ec221337c7e3cee425d1b5164653ac392cb868aba82a23c8d520599` |

The first synchronization attempt deliberately surfaced a reproducibility
hazard: an unanchored rsync exclusion named `build` removed `bench/build` on the
remote host. The documented command now anchors repository-root exclusions
(`/build`, `/dist`) and the rerun passed. Neither diagnostic is eligible for a
paper table because both used `--limit` on the development split.

The remote suite check also exposed a missing plotting extra. Matplotlib 3.11.0
and only its missing dependencies were installed into the D:-backed Python
site (72 MiB), after which all nine experiment-runner tests passed. The artifact
builder now selects and fingerprints a cross-platform CJK font; the WSL plotting
test passes with UserWarnings promoted to errors by using the already installed
Windows font rather than placing another font on C:.

## 2026-06-30: Machine-only annotation fallback made executable

The no-human annotation fallback now uses the local Qwen3.5/Ollama runtime
instead of requiring a cloud API key. The first 3-sample pilot reached the
remote GPU but failed validation (`llm_failures: 3/3`) because Qwen3.5 is a
thinking model: Ollama returned the generated JSON in its `thinking` field while
leaving the standard `response` field empty. FAR's Ollama adapter now has a
small thinking-aware compatibility path: it returns `response` when present and
falls back to `thinking` only when `response` is empty.

After the fix, a 3-sample pilot succeeded:

- output: `/mnt/d/FAR-outputs/qwen35_preannotations_pilot3_thinkingfix`;
- model: `qwen3.5:9b`;
- preannotator: `qwen35_9b_ollama_thinkingfix_machine_weak`;
- samples: 3; and
- `llm_failures: 0`.

The full 300-sample machine preannotation run was then launched in tmux session
`far-auto-label`, writing to `/mnt/d/FAR-outputs/qwen35_preannotations`. These
outputs remain non-gold reviewer aids: they cannot close the independent human
annotation or Cohen's kappa gates.
