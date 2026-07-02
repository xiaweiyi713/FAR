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
command string, removes the tmux-global copy immediately after the new session
inherits it, and refuses to overlap with an active `falsirag-suite` or Ollama
`llama-server` unless `ALLOW_CONCURRENT=1` is explicitly set. It keeps
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

`scripts/sync_qwen_core_comparison.sh` now automates the first admissible
post-run action for the central typed-control diagnostic. It reads the remote
suite marker and refuses to copy anything unless both FAR and
`minus_typed_conflict` have complete 60/60, zero-error, non-partial manifests.
Only then does it rsync the two bundles, validate them, evaluate FAR, evaluate
untyped FAR against fingerprint-bound FAR score rows, and emit paired bootstrap
and McNemar evidence. A live fail-closed test saw the complete FAR manifest and
the still-missing untyped manifest, exited nonzero, and created no local target
directory.

## 2026-06-30: Full gold-free blind-handoff dry run audited

While the corrected untyped Qwen run remained incomplete, the external-test
data path was exercised end to end without scoring or model calls. The builder
created the ignored technical bundle
`outputs/handoff/falsirag_blind_test_technical_v1/` from the current benchmark.
This is explicitly a machine-seeded dry run, not a final custodian package and
not publication evidence.

The package contains exactly three files: its manifest, sanitized corpus, and
test inputs. An independent structural audit confirmed 58 unique test rows,
175 corpus documents, test-only split values, exact five-field test records,
public-only corpus keys, and no recursive keys for gold labels, expected
revisions, counter-evidence roles, dependency groups, construction metadata,
conflict labels, or revision labels. The fingerprints are:

- bundle manifest:
  `70f6c28c4809d82822fc75596061d07284edf94ef24af6790836571fe24f7c86`;
- sanitized corpus:
  `97fb3ecff5e76fc521434182204479179b7c02422864850b60867c6d91838e12`;
- test inputs:
  `1ce8ed27a4db9c1793d9d9342418b82826c5e31d9b5ae754e012fb1f12454016`;
  and
- source corpus:
  `cca5f62db0fbb51e1bae8111ea85fe169fba7be5a8e63847a9c1c048cdae25cd`.

The final gate remains open. After two-person annotation and adjudication, a
new empty bundle must be rebuilt from the frozen adjudicated directory and
given to an independent custodian for one authorized run. The technical dry
run must never be renamed or substituted for that package.

## 2026-06-30: Novelty claim narrowed after direct-neighbor audit

A primary-source literature check identified a direct 2026 neighbor that the
draft had not cited. CounterRefine (arXiv v1 dated 2026-03-17, v3 dated
2026-05-16, accepted at an ACL 2026 workshop) already frames a draft answer as
a hypothesis, performs answer-conditioned counterevidence retrieval, and uses
a validated KEEP/REVISE repair gate. Earlier FLARE and RARR already establish
active retrieval and research-then-revision, while the COLM 2025
RAMDocs/MADAM-RAG work directly evaluates conflicting retrieved evidence.

The proposal and paper were corrected rather than stretching a priority claim.
FAR no longer claims that counterevidence retrieval or answer revision alone is
new. Its defensible empirical hypothesis is narrower: a shared typed-conflict
ontology jointly controls support/refutation/boundary retrieval and
claim-specific revision over a dependency graph, and FalsiRAG-Bench plus the
preregistered typed-versus-untyped ablation tests that mechanism. FLARE, RARR,
CounterRefine, and RAMDocs/MADAM-RAG were added to the paper bibliography and
the closest-neighbor comparison is explicit in Related Work.

The direct-neighbor audit also changed the experimental contract. A sixth,
explicitly labeled `counterrefine_style_reproduction` baseline now implements a
retrieval-grounded draft, answer-conditioned second-pass retrieval, and a
conservative JSON KEEP/REVISE gate. Proposed revisions are rejected unless the
evidence ID exists, the answer shape matches the inferred question type, and
numeric or temporal markers plus lexical content are anchored in that cited
passage. It does not use FAR's typed conflict ontology, typed query tactics, or
typed revision policy. Its metadata states that it is a closed-corpus
adaptation using the supplied initial answer, not the authors' web-retrieval
implementation.

The active corrected Qwen suite imported its baseline list before this sixth
control existed and therefore still contains the original five. It will not be
misreported as a six-baseline run. After that suite finishes, the new baseline
must be run separately on the same 60 dev IDs/config and then incorporated via
the fingerprint-checking reports-only path.

`scripts/queue_qwen_counterrefine.sh` makes that recovery autonomous on the
Windows host. It waits for the already-running suite session, refuses a non-D:
suite root, and requires 60/60 non-partial manifests for FAR, four ablations,
and all original baselines before making a model call. It then runs only the
new control and requires its complete, zero-error manifest before rebuilding
the six-baseline reports and artifacts through `--reports-only`.

## 2026-07-01: Corrected Qwen typed-vs-untyped core pair completed

The Windows GPU host was restarted after the previous user stop. The preserved
suite root was still:

`/mnt/d/FAR-outputs/qwen_open_dev_suite_corrected_96e32b7_restart_20260630_172643`.

Directly resuming the suite from current `main` correctly failed with
`output directory belongs to a different run signature`, because the current
implementation fingerprint had changed after the CounterRefine baseline was
added. The run identities for the existing corrected FAR and
`minus_typed_conflict` checkpoints required implementation SHA-256
`a98aca43b0cb494417df098d92569a6841b5f22146f2f27b7b2008d11d8aba28`. Commit
`96e32b7` was verified locally to reproduce exactly that fingerprint, then
temporarily synchronized to `/mnt/d/FAR-workspace/FAR` so the old checkpoint
could be continued without corrupting run identity.

During the resumed run, an unrelated VeraRAG WS2 repair process repeatedly
restarted on the same host and sent Qwen2.5 requests to the shared Ollama
server. A temporary tmux watchdog,
`far-verarag-stop-watchdog`, was started to kill only the exact VeraRAG
`outputs/remote_results/ws2` baseline command while `far-qwen-suite-v3` exists.
It does not kill Ollama or the FAR suite and exits after the FAR suite session
ends. This preserves the user's request to stop VeraRAG while allowing FAR to
continue using the shared local model server.

The corrected `minus_typed_conflict` run then completed 60/60 with zero errors,
no missing IDs, and `partial:false`:

- run signature:
  `4bdf72392ff78682ebf0e5dd7e6eb73a99c2405b1dce8cae81dd958c588fa04a`;
- prediction SHA-256:
  `26e6ae372d54a8dea30dd8a892a68a4ba425d91bf341366b21ce309d6d928658`; and
- paired local output:
  `outputs/remote_qwen_core_comparison/`.

`scripts/sync_qwen_core_comparison.sh` then copied only the complete FAR and
untyped runs, validated both before scoring, evaluated FAR, evaluated untyped
against FAR score rows, and validated both scored bundles. Important hashes:

- FAR report:
  `3c5b5248544a1b24aa7ff294ed4cd578b7c4ee946e38e8d52f75028e354e2fd5`;
- FAR scores:
  `6ecfa5d4afacd6b5c40688d485328dde1ef76b9566abd9e061f3dc86d6a77e43`;
- untyped paired report:
  `236b9d71bbdfa218e693bdcebd329b0af53bd97d01315e236cf257e7355468bb`;
- untyped scores:
  `42fd95c58be4b45af888737175072bf4f64a4dca157c1c6e0d01b4409bda2021`;
- untyped post-eval validation:
  `8ae0fa03ff184b8a8e6a838288dcdd976fa155891476297acac93bf1894d39db`.

The dev diagnostic supports the preregistered typed-control hypothesis but is
not publication-ready because the benchmark remains machine-seeded and lacks
human adjudication. FAR versus untyped on the same 60 Qwen3.5 dev rows:

- answer correctness: `0.7974` vs `0.7190` (`+0.0783`, 95% paired bootstrap
  CI `[+0.0344, +0.1237]` for FAR over untyped after sign conversion);
- revision accuracy: `0.2167` vs `0.0000` (`+0.2167`, McNemar
  `p=0.000244`);
- revision action correctness: `0.3667` vs `0.0000` (`+0.3667`, McNemar
  `p=4.77e-7`);
- typed conflict F1: `0.4204` vs `0.0000`; and
- counter-evidence recall: both `0.9833`.

At the time of this entry, the remaining three ablations and original five
baselines were still running in the same legacy-fingerprint suite. Later entries
supersede that operational status: the original five baselines completed, while
the separate CounterRefine-style control remains pending after a stop request.
Cloud DeepSeek/Qwen Plus runs, double-human annotation, adjudication, and
external blind custody remain open gates.

## 2026-07-02: Four corrected Qwen ablations collected; diagnosis is mixed

The legacy-fingerprint Qwen suite later completed all four ablations 60/60 with
zero errors and `partial:false`. At the time of this entry, the still-running
part of the suite was the final original Self-RAG-style baseline; a clean
current-main finalizer was queued in tmux session `far-qwen-legacy-finalize` so
that, after the legacy suite exited, it would verify FAR + four ablations + the
original five baselines, restore current `main` from a D:-backed archive, and
run the separate CounterRefine-style control plus reports-only merge. Later
entries supersede this status: the original five baselines completed and
CounterRefine was stopped at 9 checkpointed rows.

The complete ablation prediction hashes are:

- FAR:
  `992a4cf027db5491feef2a57210d8a9395be61798c0ff84b29760d495bc96b56`;
- `minus_typed_conflict`:
  `26e6ae372d54a8dea30dd8a892a68a4ba425d91bf341366b21ce309d6d928658`;
- `minus_refutation_query`:
  `a789a4b6a816c47b0266d765ce7570df54dd2269b399861390bb652c68efeb3e`;
- `minus_boundary_query`:
  `0f3f365c23afec84fc28e8848fe908324b4f3807b9d913c9f4fb0fd38702ec72`;
  and
- `minus_typed_revision`:
  `601777f8bedacd60cfe4d7a9599f3a1b92bd6e24d531784ffd6e4ad75ca5bc8c`.

All five local reports and score files in
`outputs/remote_qwen_ablation_matrix/` passed result validation. Report hashes:

- FAR:
  `3c5b5248544a1b24aa7ff294ed4cd578b7c4ee946e38e8d52f75028e354e2fd5`;
- `minus_typed_conflict`:
  `236b9d71bbdfa218e693bdcebd329b0af53bd97d01315e236cf257e7355468bb`;
- `minus_refutation_query`:
  `e0dc1d2417a6d6504e046e5dd81d8bb969cacb0ffb9869e78e2aa7da6b9fe0d2`;
- `minus_boundary_query`:
  `9fce3485347983504ce2bd8d4aa00556f27031e9904b19b695371f9e8ecce935`;
  and
- `minus_typed_revision`:
  `200633e88cb62ad89dd7234d6497262ad3a131dc33d84c70c31bf53120138d23`.

The interpretation must stay conservative because the benchmark is still
machine-seeded and `publication_ready:false`. The corrected dev evidence
strongly supports the typed-conflict control mechanism: relative to FAR,
`minus_typed_conflict` drops answer correctness by `0.0783`, revision accuracy
by `0.2167`, revision-action correctness by `0.3667`, and typed-conflict F1 by
`0.4204`. However, the other component ablations are not monotonic on this
diagnostic set: `minus_refutation_query` and `minus_boundary_query` do not hurt
answer correctness, and `minus_typed_revision` raises answer correctness while
driving revision accuracy/action correctness to zero. This is a useful warning
for the paper: the defensible claim is typed conflict as an auditable control
signal, while marginal claims about every query/revision submodule must be
withheld or rewritten unless adjudicated gold/test evidence supports them.

## 2026-07-02: Remote Qwen suite paused cleanly before local power-off

After the legacy suite exited, the queued finalizer verified FAR, four
ablations, and the original five Qwen baselines as complete 60/60 with zero
errors, restored the current-main archive, and started the separate
CounterRefine-style closest-neighbor control. At the user's request before
local power-off, the remote `far-qwen-legacy-finalize` and `far-ollama` tmux
sessions were killed, and the remaining Ollama/FAR/VeraRAG processes were
confirmed absent on `windows-gpu`.

The CounterRefine control is therefore not complete: its checkpoint file had 9
rows when the stop request was handled. The suite outputs were left in place,
but the six-baseline Qwen reports-only merge must wait until CounterRefine is
resumed or rerun to 60/60. Documentation status now records the original five
baselines as complete and the sixth baseline as pending, rather than
misstating it as still running.

## 2026-07-02: CounterRefine completed and six-baseline Qwen report merged

The Windows GPU host was reachable again, with no residual FAR/VeraRAG/Ollama
processes and D: storage still available. The D:-backed Ollama service was
started in tmux session `far-ollama`, and
`scripts/queue_qwen_counterrefine.sh` was resumed in
`far-qwen-counterrefine` against the existing corrected suite root:

`/mnt/d/FAR-outputs/qwen_open_dev_suite_corrected_96e32b7_restart_20260630_172643`

The CounterRefine-style closest-neighbor baseline resumed from 9 checkpointed
rows and completed 60/60 with zero errors and `partial:false`. The script then
ran `falsirag-suite --reports-only`, producing an 11-method suite manifest with
FAR, four ablations, and all six baselines. After rsync to the ignored local
directory `outputs/remote_qwen_six_baseline_suite/`, all 11 run/evaluation
bundles passed `experiments.validate_results`.

Key fingerprints:

- suite manifest:
  `dccd854c74d3eec109fb879e0c0d1fb838763694adc655b24eb83219807c4467`;
- CounterRefine predictions:
  `483f08eca2c34431ac81e87dcac2277433afc5e24e858475742d5c162a6b8c57`;
- CounterRefine report:
  `e3c25f966e99b126aad8ff0c3e24353bdf287b85b8d42e7b14beeef94a6d4d5e`;
- CounterRefine scores:
  `e4aca75e72afd5878ca727e9e77f1f8b67f353e14f7d9375574f85293128c08d`.

The compact machine-seeded dev metrics are:

| Method | Answer correctness | Revision acc. | Typed conflict | CE recall | Unsupported |
|---|---:|---:|---:|---:|---:|
| FAR | 0.7974 | 0.2167 | 0.5500 | 0.9833 | 0.0167 |
| Vanilla RAG | 0.7246 | 0.0000 | 0.0000 | 0.6667 | 0.2667 |
| Multi-query RAG | 0.7008 | 0.0000 | 0.0000 | 0.8167 | 0.1333 |
| Reflective RAG | 0.6778 | 0.0000 | 0.0000 | 0.7500 | 0.1833 |
| CRAG-style | 0.7722 | 0.0000 | 0.0000 | 0.6667 | 0.2667 |
| Self-RAG-style | 0.7510 | 0.0000 | 0.0000 | 0.8167 | 0.1500 |
| CounterRefine-style | 0.7102 | 0.0000 | 0.0000 | 0.8833 | 0.0833 |

Interpretation remains conservative. This closes the local Qwen dev
six-baseline diagnostic, but it does not close the publication gate because the
benchmark is still machine-seeded. FAR is above all six baselines on answer
correctness in this diagnostic and retains the typed revision/trace advantages,
including over CounterRefine. However, the ablation diagnosis remains mixed:
`minus_typed_revision` has higher answer correctness while zeroing revision
accuracy/action correctness, so the paper must keep the narrower claim that
typed conflict is an auditable control signal rather than claim monotonic gains
from every FAR submodule.

After completion, `far-ollama` was stopped and the remote host was confirmed to
have no FAR/VeraRAG/Ollama tmux sessions or processes.

## 2026-07-02: External evidence chain made fail-closed and executable

The remaining human/cloud/custodian work is now represented by one explicit
acceptance chain rather than prose-only TODOs. Formal run identities include
the exact Git commit and dirty state, and result validation recomputes the v2
identity signature to reject provenance tampering. Evaluation readiness was
split correctly by phase: adjudicated dev/train reports require the human
annotation and kappa gate, while test reports additionally require an external,
one-shot, gold-free blind-test record.

Added `falsirag-score-blind-return` to validate a complete 11-method custodian
return, role-separated attestation, handoff and source fingerprints, and frozen
commit before trusted scoring. It emits comparison-bound test reports and final
artifacts into a fresh directory. Added `falsirag-submission-readiness` and
templates to audit the candidate benchmark, human annotation, all three formal
dev suites, final blind bundle, three returns, attestation, three scored test
suites, release archive, paper placeholders, and human policy review. An
end-to-end test exercises all 11 methods through the blind runner and trusted
scorer. The current real-project status remains fail-closed because independent
human labels, rotated-key cloud runs, and external custody do not yet exist.

## 2026-07-02: Human annotation evidence made reviewer-bound and replayable

The Label Studio bridge previously exported the adjudicator's canonical
evidence order and accepted a reviewer ID only during import. It now requires a
declared reviewer at export, preserves that reviewer's independent shuffle, and
binds every task to the packet, reviewer source file, and exact visible context.
Import rejects reviewer swaps, duplicate tasks, modified context, blank
rationales, and multiple active annotations. A new atomic `install-review`
command replaces only the named blank reviewer template and refuses later
replacement.

The annotation compiler now rejects duplicate sample IDs, packet paths outside
the packet, changed visible fields, missing rationales, and blank/inconsistent
adjudicator IDs. Successful compilation freezes the raw reviewer files,
adjudication, packet manifest, and fingerprints under `annotation_evidence/`.
`validate-evidence`, submission readiness, and the trusted blind scorer all
recompute pairwise kappas and verify every compiled conflict type, revision
action, and supplied revised answer against that archive. This closes a
reproducibility gap in the future human workflow; no real human labels have been
created by this engineering change.

The compiler also stopped carrying an unseen machine-seeded revised answer
through a blank adjudication. A conflict-positive adjudication now requires a
human-authored revised answer; a no-conflict adjudication is represented by the
explicit internal `no_conflict` type and deterministically uses the initial
answer. This was tightened further so a no-conflict adjudication with a
non-empty `revised_answer` is rejected instead of silently altering the
reference answer. Both paths are schema- and regression-tested.

The final human handoff now has a Label Studio adjudication round trip rather
than requiring manual JSON editing. `falsirag-auto-annotate
adjudication-label-studio` exports an adjudicator project after the reviewer
files are frozen, including both reviewer labels and reviewer-to-adjudicator
evidence-ID maps as read-only context. `adjudication-label-studio-import`
converts exactly one active adjudicator completion per task into
`adjudications.jsonl`, and `annotate_packet install-adjudication` atomically
installs that file while refusing replacement, modified visible fields,
missing conflict-positive revised answers, and no-conflict revised answers.

A fresh strict packet was then generated locally at
`outputs/annotations/falsirag_packet_v1/`, together with separate prediction-free
Label Studio bundles for `reviewer_a` and `reviewer_b`. Both contain 300 tasks,
zero predictions, reviewer-bound context hashes, and standalone instructions.
The packet manifest SHA is
`ae12cf5dcdc0a7ac202dbbc5e3c8a47136c37f8fcf8289c5b5847e2b9c923b24`;
reviewer task SHAs are
`3691e27117a722ef8827282235b2609ebd4a8a33a4c878924ba19f327f03c6ab`
and `f627faf8fdf7c9f71af748926654d8578ae4792647b2c072b9af75db18005e19`.
They are blank handoff artifacts, not completed human annotations.
