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

## 2026-06-30: Qwen3.5 dev main run and claim-contract audit

The complete open-model FAR development run finished 60/60 with zero errors:

- output: `/mnt/d/FAR-outputs/qwen_open_dev`;
- run signature:
  `d87dfa21ff6f1cdd52de181747611ebce5d5915501ca5ec0f5f4ae327939658d`;
- implementation SHA-256:
  `f8d227580d468b2382b71fdbf3988444e1a07e11abfd94fcb2f1e0955fa1d4f9`;
- prediction SHA-256:
  `aa0661ee137858e0800555a94795a8a0d3b1369a53dbb4c93b10abe6f9887a74`;
- elapsed time: 2.50 hours; and
- output QA: 60 unique rows, no empty answers, and no reasoning leakage.

The latest evaluator correctly marks the report `publication_ready: false`:
the benchmark is still machine-seeded and all 60 dev rows lack adjudicated
human labels. The diagnostic metrics therefore remain development evidence:
counter-evidence recall 0.983, evidence precision 0.113, typed conflict F1
0.288, revision-action accuracy 0.283, revision accuracy 0.150, and answer
correctness 0.692.

Category analysis found a concrete failure rather than a retrieval bottleneck:
entity-confusion typed accuracy was 0/12 even though the relevant counter
document was usually retrieved. Accepted LLM decompositions created
`ClaimNode`s without deterministic entity/number/time fields, and the source
coverage check permitted claims that added novel vocabulary while retaining
80% of source vocabulary. The local next revision now reparses every accepted
LLM claim for typed attributes and requires exact bidirectional source-token
coverage; otherwise it falls back to the deterministic decomposer. Regression
tests cover both missing typed attributes and the observed alternative-insertion
failure. The full 79-test suite passes. This correction was derived from dev
only; the held-out test bundle remains untouched. A fresh matched dev rerun is
required before attributing any metric change to it.

The original frozen-code suite continues independently on Windows. Its results
remain the valid matched comparison for the completed Qwen main run; the local
correction is intentionally not synchronized into the live process.

## 2026-06-30: Corpus-entity metadata restored to the typed detector

The entity failure audit found a second independent implementation gap. The
benchmark constructor selected entity substitutions from the public `entities`
lists already present in `bench/corpus.jsonl`, but `experiments/runner.py`
dropped those lists while constructing runtime `EvidenceDocument`s. As a
result, the VeraRAG adapter could not use the same non-gold entity information
available to retrieval and benchmark construction.

The corrected runtime now preserves corpus entities and builds a frozen global
entity lexicon for the detector. Formal configs explicitly enable a
high-precision fallback at lexical similarity 0.55. It emits an entity control
only when a corpus-known claim entity is absent from every retrieved passage,
a different public corpus entity anchors a near-duplicate passage to the claim
or question, and the threshold is met. Trace metadata records the detector,
unsupported/anchor/candidate entities, and similarity. The blind bundle now
retains only this public entity list in addition to its existing public corpus
fields; it still excludes labels, expected revisions, counter-evidence links,
dependency groups, and construction metadata.

The threshold audit used only train+dev labels and directly supplied each
sample's annotated counter-document to isolate detector precision from
retrieval. The fallback identified 20/48 entity substitutions and 0/194
non-entity samples. This is a conservative component audit, not an end-to-end
metric or paper result. A real retrieval/NLI replay of dev sample `F0161`
retrieved `D011` and emitted the new `corpus_entity_lexicon` signal for the
`Agent`/former-CTO claim. A balanced five-sample formal-stack smoke completed
5/5 with zero errors and passed result validation:

- output: `outputs/entity_lexicon_pilot` (diagnostic and partial);
- run signature:
  `cd12f7db199682901ecfb980bb8cc6bc146ff11c84bca10e9a428e15aa5e013f`;
- prediction SHA-256:
  `933c473c909198fef7aa7f5e9c828abe4b9cef7cf3afd4f93e260156a24b9a1e`; and
- repository validation: ruff, mypy across 49 sources, and 81 tests pass.

The held-out test labels were not inspected. The correction changes formal run
signatures and therefore requires a fresh matched dev suite after the original
frozen-code comparison finishes.

The same audit also found that `UntypedConflictDetector` exposed only the
single-document `detect` method. `FARPipeline` therefore used VeraRAG's batched
graph for the full method but silently rebuilt one graph per document for
`minus_typed_conflict`. The wrapper now delegates `detect_many` and changes only
the conflict labels/query typing as intended. A regression test fails if the
untyped wrapper falls back to per-document detection. Consequently, the
already-running frozen-code untyped result remains useful for diagnosis but is
not an admissible C2 ablation; the corrected matched suite is mandatory.

The invalid comparison was stopped after 44/60 untyped checkpoints and
preserved without deletion at
`/mnt/d/FAR-outputs/qwen_open_dev_suite_frozen_diagnostic_20260630_96e32b7`.
Commit `96e32b7` was then synchronized to `/mnt/d/FAR-workspace/FAR`; the remote
host passed 81 tests, ruff, and mypy over 49 source files. A fresh full suite was
started in tmux session `far-qwen-suite-v2`, writing only to:

- suite: `/mnt/d/FAR-outputs/qwen_open_dev_suite_corrected_96e32b7`;
- log: `/mnt/d/FAR-outputs/qwen_open_dev_suite_corrected_96e32b7.log`;
- FAR run signature:
  `b4c32c2d4397251a6473125533312f0614f9f726642a252aaaaa494463351780`; and
- implementation SHA-256:
  `a98aca43b0cb494417df098d92569a6841b5f22146f2f27b7b2008d11d8aba28`.

The local and remote implementation fingerprints match. This suite reruns FAR,
all four corrected ablations, and all five baselines before evaluation; it does
not reuse the old FAR prediction symlink.

That first corrected-suite attempt did not produce any checkpoint. The WSL tmux
server and Ollama service were no longer running when it was inspected, and the
suite failed at dev item `F0004` while unloading because the Ollama API was not
reachable. The failed directory was preserved as an incident record rather than
overwritten:

- failed suite root:
  `/mnt/d/FAR-outputs/qwen_open_dev_suite_corrected_96e32b7`;
- only written file:
  `runs/far/run_identity.json`; and
- failure mode: `ConnectionError: Failed to connect to Ollama`.

Ollama was restarted from the D:-backed runtime
`/mnt/d/FAR-runtime/ollama/bin/ollama` in tmux session `far-ollama`, with
models still resolved from `/mnt/d/FAR-models/ollama`. A clean replacement
corrected suite was then launched in tmux session `far-qwen-suite-v3`:

- suite:
  `/mnt/d/FAR-outputs/qwen_open_dev_suite_corrected_96e32b7_restart_20260630_172643`;
- log:
  `/mnt/d/FAR-outputs/qwen_open_dev_suite_corrected_96e32b7_restart_20260630_172643.log`;
- latest-path marker:
  `/mnt/d/FAR-outputs/latest_far_corrected_suite_path.txt`; and
- start state: Ollama and `falsirag-suite` both live, GPU inference active on
  `F0004`.

`scripts/start_windows_qwen_suite.sh` now captures this D:-backed restart
procedure so a later recovery does not depend on shell history. The script
starts Ollama if needed, refuses to collide with an existing suite session, and
records the timestamped suite root under `/mnt/d/FAR-outputs`.

## 2026-06-30: Machine weak-label audit and corrected FAR rerun status

The completed Qwen2.5 machine preannotation bundle and its blind packet were
copied back from the Windows GPU host into the local ignored
`outputs/remote_machine_annotation/` directory. A deterministic rule weak-label
pass and machine-vs-machine audit were generated from those copied artifacts,
without modifying the running remote suite:

- packet samples: 300;
- Qwen2.5 preannotation samples: 300, SHA-256
  `6796d46aa84e7c0a0ff32083e9257aa5fc6c7e5c3a9236735f4dfc659aa34caa`;
- rule weak-label samples: 300;
- weak-label SHA-256:
  `f31f2422d5c3471002675db57b2b5104ee1ee71bb14b170477c95aa02296f8a1`;
- non-abstained weak labels: 211; abstentions: 89;
- weak conflict-type counts: temporal 118, numerical 30,
  source-reliability 29, entity 20, causal 10, definition 4;
- audit shared samples: 300; missing packet samples: 0;
- all-shared agreement: conflict-present 0.687, conflict-type 0.363,
  revision-action 0.370;
- weak-non-abstained agreement: conflict-present 0.863, conflict-type 0.403,
  revision-action 0.398; and
- priority review samples: 127.

These outputs are explicitly non-gold machine aids. They are useful for
ordering scarce review time and catching cases where the LLM and deterministic
rules disagree, but they do not satisfy the two-annotator requirement and cannot
be used as Cohen's kappa evidence.

During the same checkpoint, the D:-backed corrected Qwen suite had completed
the corrected FAR rerun:

- suite:
  `/mnt/d/FAR-outputs/qwen_open_dev_suite_corrected_96e32b7_restart_20260630_172643`;
- method: FAR;
- split: dev;
- status: complete, 60/60, zero errors, `partial: false`;
- prediction SHA-256:
  `992a4cf027db5491feef2a57210d8a9395be61798c0ff84b29760d495bc96b56`; and
- next suite step observed in the log: `far_minus_typed_conflict`.

Only the status helper script was synchronized while the suite was active. It
now selects `python3` or `python` automatically for manifest summaries, so
remote status checks no longer depend on a shell-level `python` alias.

The local release gate was rerun after commit
`3e9cbf475b57722fc19baa27e0610546de471d39` and passed end to end: formatting,
ruff, mypy across 63 source files, 85 tests, benchmark validation, SBOM
validation, package build, release checksums, secret scan, and the paper,
supplement, and reproducibility-checklist LaTeX builds. The regenerated release
checksum manifest was clean (`git_dirty: false`) and recorded:

- source distribution SHA-256:
  `fd3d2824971f9ee0d6d8b38aa68f4a9b0c932b2b48490923c5caddef8b27b684`;
- wheel SHA-256:
  `040b45df2e759449235d789da93c1665381e12efc9928fbb55c82578b3b956a9`; and
- CycloneDX SBOM SHA-256:
  `3c0dc30f7fc0ac0952cfcc96c8912cb921464a7cddf27acb77d83659ba9b4d89`.

As before, this closes repository-controlled release mechanics only. It does
not close the human annotation, cloud-model, externally blind test, author, or
policy-review gates.

## 2026-06-30: Cloud-run preflight added before credentialed experiments

The DeepSeek and Qwen Plus formal configs still require rotated cloud
credentials before any publication-relevant run. To make the next credentialed
step fail closed, `scripts/check_cloud_run_readiness.sh` now verifies the
cloud-backed configuration without printing or persisting secrets:

- `experiments/configs/deepseek.yaml` must use provider `deepseek`, model
  `deepseek-v4-flash`, and environment variable `DEEPSEEK_API_KEY`;
- `experiments/configs/qwen_plus.yaml` must use provider `dashscope`, model
  `qwen3.7-plus-2026-05-26`, and environment variable `DASHSCOPE_API_KEY`;
- both configs must retain `vera_hybrid`, `allow_dense_fallback: false`, local
  dense/reranker snapshots, `require_nli: true`, and local NLI loading;
- default local output roots must stay under ignored `outputs/`, and Windows
  absolute output roots must stay off C:; and
- `--require-keys` upgrades missing environment variables from warnings to
  failures immediately before spending API budget.

The repository release gate now runs shell syntax checks and this no-key
preflight. This closes a configuration-readiness risk only; it does not create
cloud model results and does not make the previously exposed key safe to use.

`scripts/start_windows_cloud_suite.sh` now provides the matching D:-backed tmux
starter for the credentialed DeepSeek and Qwen Plus suites. It runs the same
preflight for the selected config, requires only that config's environment
variable, writes result bundles and latest-path markers under `/mnt/d/FAR-outputs`,
passes the key to tmux's private environment without embedding it in the visible
command string, and refuses to overlap with an active `falsirag-suite` or
Ollama `llama-server` unless `ALLOW_CONCURRENT=1` is explicitly set. It keeps
the clean-worktree preflight by default; `ALLOW_DIRTY=1` exists only for a
recorded rsync copy whose `.git` metadata is stale because `.git` was excluded.
This is startup hygiene only; the cloud result gate remains open until rotated
credentials are supplied and complete validated suites exist.

The two cloud helper scripts were then copied alone to the D:-backed Windows
workspace and checked without a key or model call. Remote shell syntax passed,
the preflight found VeraRAG at `/mnt/d/FAR-workspace/VeraRAG`, accepted
`/mnt/d/FAR-outputs/cloud_suites`, and verified the pinned DeepSeek config. The
rsync workspace intentionally has no `.git` directory; the preflight now treats
missing Git metadata as a hard failure by default rather than incorrectly
calling the tree clean. An explicit `--allow-dirty` permits this known rsync
diagnostic with a warning, while the strict path exits nonzero and requires a
recorded source revision before a formal cloud run.

At that checkpoint, the corrected FAR suite had reached 47/60 on
`minus_typed_conflict`. A separate VeraRAG Qwen2.5 baseline job was also using
the same Ollama/GPU host, and several FAR samples slowed from roughly minutes to
6--20 minutes. Both jobs remained live; no process was stopped or reprioritized.
The cloud starter's default concurrency refusal is therefore retained.

The already-complete corrected FAR run was copied back independently to the
ignored local `outputs/remote_qwen_corrected_suite/` directory while the
remaining suite continued. `experiments.validate_results` passed both before
and after evaluation: the run is complete 60/60 with zero errors, no duplicate
IDs, finite values, matching identity/manifest signatures, a matching
prediction fingerprint, and no leaked reasoning markers. Its frozen identity
is:

- run signature:
  `b4c32c2d4397251a6473125533312f0614f9f726642a252aaaaa494463351780`;
- implementation SHA-256:
  `a98aca43b0cb494417df098d92569a6841b5f22146f2f27b7b2008d11d8aba28`;
- benchmark SHA-256:
  `c5bd988f60646bde33d62f654ddb456d2c2c1279175bee92ef503f362addbd8f`;
- corpus SHA-256:
  `cca5f62db0fbb51e1bae8111ea85fe169fba7be5a8e63847a9c1c048cdae25cd`;
- config SHA-256:
  `a8da92080d9750b7d097b05f8e8ee5ea8f84f2e05432be3e26f13004b3cbb4ea`;
- Qwen3.5 9B Ollama digest:
  `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`;
- prediction SHA-256:
  `992a4cf027db5491feef2a57210d8a9395be61798c0ff84b29760d495bc96b56`;
- evaluation report SHA-256:
  `3c5b5248544a1b24aa7ff294ed4cd578b7c4ee946e38e8d52f75028e354e2fd5`;
- score-row SHA-256:
  `6ecfa5d4afacd6b5c40688d485328dde1ef76b9566abd9e061f3dc86d6a77e43`;
  and
- result-validation SHA-256:
  `69669cfb7629e7eab248a363e56d4f777a998f56686d272c34eb629dbd3cfc28`.

The current evaluator was run against the full benchmark path so its report is
bound to `bench/manifest.json`, while scoring only the 60 returned dev IDs. It
correctly records 60 `machine_seeded` rows and `publication_ready: false`.
Diagnostic aggregate values are: counter-evidence recall 0.983, evidence
precision 0.122, typed conflict F1 0.420, revision-action accuracy 0.367,
revision accuracy 0.217, and answer correctness 0.797. These are directionally
better than the original pre-correction dev run, but the corrections were
derived from dev and the paired untyped run is still incomplete. They therefore
remain debugging evidence, not a paper claim or a substitute for adjudicated
labels.

The remote status helper was extended after the observed contention. It now
reports the newest checkpoint path and age, warns after a configurable
`STALE_SECONDS` interval, and explicitly lists competing generation clients
when they coexist with `falsirag-suite`. A live remote test with
`STALE_SECONDS=300` reported the 47-row untyped checkpoint as 778 seconds old
and identified the concurrent VeraRAG `run_baselines.py` process. The warning is
diagnostic only and never stops or reprioritizes a process.
