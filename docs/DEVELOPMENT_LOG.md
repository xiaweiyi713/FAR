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
`far-auto-label`, writing to `/mnt/d/FAR-outputs/qwen35_preannotations`.
Preannotation JSONL is now flushed incrementally so the long run exposes
line-count progress and preserves completed rows if the remote host is
interrupted. These outputs remain non-gold reviewer aids: they cannot close the
independent human annotation or Cohen's kappa gates.

The full Qwen3.5 run completed 300/300 rows but produced 219 schema fallbacks,
so it was retained only as a rough review bundle. A non-thinking Qwen2.5
annotation-helper config (`experiments/configs/qwen25_autolabel.yaml`) was then
added and run on the same D:-backed Windows GPU host. The Qwen2.5 pilot passed
10/10 after normalising common no-action aliases, and the full run completed:

- output: `/mnt/d/FAR-outputs/qwen25_preannotations`;
- model: `qwen2.5:7b`;
- preannotator: `qwen25_7b_ollama_machine_weak`;
- rows: 300/300, 300 unique samples, no duplicate or extra sample IDs;
- fallbacks after one targeted `--resume --retry-fallbacks` pass: 1 (`F0138`);
- preannotation SHA-256:
  `6796d46aa84e7c0a0ff32083e9257aa5fc6c7e5c3a9236735f4dfc659aa34caa`; and
- Label Studio review bundle:
  `/mnt/d/FAR-outputs/label_studio_qwen25`, 300 tasks with 300 predictions.

The Qwen2.5 bundle is the preferred no-human machine draft. It remains
`publication_gold: false` and cannot be reported as independent human
annotation or Cohen's kappa evidence.

## 2026-06-30: Qwen formal-run thinking leak rejected and corrected

The first unbounded Qwen3.5 dev attempt was stopped at 6/60 after output QA
showed that five answers contained `Thinking Process` text; one answer was
9,034 characters. That attempt is invalid for scoring and was preserved at
`/mnt/d/FAR-outputs/qwen_open_dev_invalid_thinking_20260630-111454` rather than
silently overwritten. Its waiting suite was cancelled as well.

The earlier annotation-only thinking fallback is now superseded for experiment
runs. `qwen_open.yaml` explicitly sets `think: false`, the setting is bound into
the run signature, and the Ollama adapter fails closed instead of returning the
`thinking` field when the final `response` is empty. Result-bundle validation
also rejects answers containing known leaked-reasoning markers.

A real D:-backed Windows pilot then passed:

- output: `/mnt/d/FAR-outputs/qwen_open_thinkoff_pilot1`;
- run signature:
  `d12456ebe9b49c0b2fd2356e4c064fcdde909e19bb1281e87425ca39c11ed53a`;
- model digest:
  `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`;
- manifest: complete 1/1, zero errors, diagnostic/partial;
- output: four claims, twelve retrieval traces, four revision traces, a
  130-character final answer, and no thinking marker; and
- prediction SHA-256:
  `eb9312e7e71e89ef5926cf01a1f044452e6d14c3bcd9c4fc45a32a8ece5170f7`.

The first thinking-disabled 60-sample restart, signature
`ea5ef918caf8f4b358e5f64fdfa5d587d61a62d6ad362add3c0f9e62cc72deb2`,
then exposed a separate host-memory failure before its first checkpoint.
Ollama 0.30.11 accumulated about 6.85 GiB of prompt checkpoints while the WSL
VM had only 7.6 GiB RAM; the kernel killed `llama-server` when FAR's CPU
retrieval/NLI models were resident. The failed attempt is preserved under the
`qwen_open_dev_oom_20260630-112331` prefix.

The formal config now uses `unload_after_sample: true`: all LLM calls for one
sample share a loaded model, and the runner then sends Ollama an explicit
`keep_alive=0` unload request. This clears the cross-request cache once per
sample instead of paying the roughly 50-second D:-drive reload before every
claim/query/revision call. The memory-safe pilot passed with:

- output: `/mnt/d/FAR-outputs/qwen_open_sample_unload_pilot1`;
- run signature:
  `eb92f0c55866db13824b7f52dd2cdd20036cb2d93288a6433525edf6c5e18fc1`;
- manifest: complete 1/1, zero errors, diagnostic/partial;
- elapsed time: 94.4 seconds;
- prediction SHA-256:
  `caff3a4bc540088e253eb17a437c4cf66670b861dedf2203b0f061653f728a44`;
- no thinking marker; and
- Ollama `/api/ps` empty after the sample, with host available memory restored
  from at least 4.2 GiB during inference to 6.7 GiB after unload.

The clean 60-sample dev run was restarted in `far-qwen-dev` with signature
`d87dfa21ff6f1cdd52de181747611ebce5d5915501ca5ec0f5f4ae327939658d`.
`far-qwen-suite` waits behind it and will verify the complete upstream manifest
before running all four ablations, all five baselines, evaluation, validation,
and artifact construction under `/mnt/d/FAR-outputs/qwen_open_dev_suite`.

## 2026-06-30: Submission artifact gates made executable

The proposal's final SBOM/fingerprint/check requirement is now backed by
repository commands adapted from VeraRAG's MIT-licensed release tooling:

- `falsirag-generate-sbom` generated and validated a CycloneDX 1.5 SBOM with
  14 deduplicated required/optional dependency components;
- `falsirag-release-checksums` bound the wheel, source distribution, and SBOM
  paths, byte sizes, and SHA-256 hashes in a three-artifact manifest;
- `falsirag-scan-secrets` scanned tracked and unignored text with redacted
  high-confidence rules and returned zero findings; and
- `scripts/release_check.sh` combined those gates with benchmark validation,
  ruff, mypy, 76 tests, package builds, and all three LaTeX compilations.

The complete release check passed locally. It produced a 3-page paper, 1-page
supplement, and 2-page checklist. This closes repository-controlled release
mechanics, not the human annotation, cloud-model, external blind-test, author,
or policy-review gates.
