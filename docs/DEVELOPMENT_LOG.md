# Development Decision Log

## 2026-07-04: RAMDocs document-type leakage caught before scoring

Operational QA found that the first RAMDocs import encoded upstream document
types in the `source` strings (`ramdocs_correct`, `ramdocs_misinfo`, and
`ramdocs_noise`) and retained the type in runtime metadata. Although the
initial-answer prompt did not print either field, FAR's source-reliability layer
could in principle consume the source name. Any G-A result produced under that
representation would therefore be vulnerable to label leakage.

The formal queue was stopped before it left initial-answer generation. Its 14
completed initial answers and the earlier one-row FAR smoke are preserved under
the `invalid_type_leak_20260704` / pilot output names and are excluded from all
reports. The importer now assigns every document the same
`ramdocs_anonymous_document` source, and the operational loader strips
`document_type` while retaining types only in the scorer-side corpus metadata.
Tests enforce both invariants. The anonymized corpus SHA-256 is
`219269fedcdc21c9bd87b045a5afd1e7ce60c22ea21f4c1e8ded9c7658d61496`.

The anonymized rerun then passed both one-row stages from clean commit
`fa3b344767c07d03cc21119adc2509fd7e54aba1`:

- initial answer: signature
  `7fcdc3e1884b9f0dc3559c7135a7e90ed3acacf48ff037d5ad171b1defc4ba8e`,
  prediction SHA-256
  `23705228e2ed73dad802679bebc4194dd4a7dac22af059cc4f0c96b92b636c2e`;
- full FAR: signature
  `f97f621155e143123b45212efabb85a777faee2e1abd41ff6538c7b3184a175e`,
  prediction SHA-256
  `cf0fa9e09046ec6046d4a12c12b5e375f4b9590e4e0b70cc501926e03db5e438`.

The completed FAR row used only item-local document IDs and contained neither
runtime document-type metadata nor type-bearing source names. The formal Phase A
suite was restarted from zero after this validation; no invalidated checkpoint
was reused.

A final pre-run audit then noticed that the runtime loader still exposed the
upstream `disambig_entity` list through document metadata. Because FAR can build
an entity lexicon from that field while baselines cannot, the loader was tightened
again to pass an empty metadata mapping for every RAMDocs runtime document. The
second restart was stopped before its first checkpoint, so it produced no row to
invalidate. Scorer-side corpus metadata remains available only after prediction.

The first no-oracle FAR smoke then failed closed before inference because the
formal conflict config still required `enable_entity_lexicon_conflict` while the
fair runtime lexicon was intentionally empty. RAMDocs has no system-visible,
non-oracle entity lexicon, so its dedicated config now explicitly disables only
that lexicon-assisted signal. NLI, temporal, numerical, source consistency,
scope, and granularity checks remain enabled. This is a pre-evaluation data
adapter decision; no development score existed when it was made.

The fully no-oracle smoke passed from clean commit
`ee27a3061dd1ed5c792f44fa42cb2361ae0c03f6`. Its initial-answer signature is
`8108ce2e39a89f0fedd20935269d6fb3781632ad57defaee72ca2a1451a2cff5`
(prediction SHA-256
`20f513f4fdd5af474319f889fa61d8710b8ef1a0f6e8c575513c176091939d1f`),
and its FAR signature is
`de2c9e9d412a5f9a1371047fff32d95620f0f049ac13e69a091cbdd1fd2767c2`
(prediction SHA-256
`031d1985491a7dcf674e67cb88de91f6e5acd1e53d65db507f8ad3de9e1c988e`).
The row used only item-local IDs, generated nine typed queries, and exposed no
document type, type-bearing source name, or upstream disambiguated entity. The
formal suite was launched again from zero only after these checks passed.

Before any RAMDocs score existed, a statistical audit caught that the first G-A
implementation accepted any exact McNemar `p < 0.05`, even when the candidate
was significantly worse. Because the test is two-sided, the gate now requires a
strictly positive observed FAR-minus-baseline exact-match difference together
with `p < 0.05`; the alternative bootstrap path still requires a lower bound
above zero. A reverse-comparison regression test prevents directionless passage.

The same requirement audit caught a missing A2 auxiliary: conflict reporting on
items that contain upstream `misinfo` documents. The scorer now reports
`misinformation_conflict_detected` only on that weak-truth subset and records its
denominator separately. This uses scorer-side metadata after prediction; the
runtime remains blind to document type. A complete three-item, eight-method
offline suite then exercised initialization, all run directories, partial
scoring, every paired comparison, strongest-baseline selection, and the failed
G-A stop path without accessing test.

The in-flight formal suite was stopped before this scorer change was admitted;
the replacement output directory had zero completed rows. No prior formal or
smoke output is eligible for G-A. The complete 350-item development suite was
restarted from zero from clean commit
`73109746a0780db788fa1d8e72fcea1ce4abc703` in tmux session
`far-ramdocs-phase-a`, with a previously absent
`/mnt/d/FAR-outputs/ramdocs_dev_v1` directory. The first initial-answer
checkpoint was durably written, confirming the D:-backed Qwen/Ollama path is
making progress. This is an execution checkpoint, not a scored result.

## 2026-07-04: RAMDocs closed-corpus GPU smoke and Phase A launch

The pinned 500-row RAMDocs import was rebuilt at Hugging Face revision
`9c041bfd158c603b615883d9a931b00cbc141494`. It contains 2,766 documents and a
frozen 350/150 development/test split. The test input file exposes only
`id/question/split`; no test scoring was run.

On the D:-backed Windows GPU host, a clean-checkout Qwen3.5 9B initialization
pilot completed 3/3 samples with zero errors and no hidden labels loaded. Its run
signature is `de7782c49b7e6028312cf7bf681ec7c7d7a77b7b398058302f694a3f92c4e599`
and prediction SHA-256 is
`3d649c0b242e78d77e8627a1d2f0ae1afed2ccd04b0ad7636e96520f59a58388`.

A separate full-FAR smoke was intentionally interrupted after the first durable
checkpoint. That completed row loaded the pinned NLI model, generated six
LLM-marked typed queries, produced two revision traces, used only `RAM0001-*`
documents, contained no thinking text, and finished in 83.2 seconds. It is a
runtime smoke, not a paper result.

The complete RAMDocs development suite was then launched in tmux session
`far-ramdocs-phase-a`, writing to `/mnt/d/FAR-outputs/ramdocs_dev_v1`. It runs
from clean Git commit `171d943a0bc9e1e595008eaaf37186e70c8e608f` and resumes from
incrementally flushed checkpoints. The G-A stop rule remains authoritative: no
jury annotation, held-out scoring, or upgraded paper packaging begins unless
the completed development comparison passes G-A.

## 2026-07-04: 2+4 protocol preregistered

The zero-budget replacement for the unavailable independent-human annotation
path is preregistered in `docs/PLAN_2PLUS4.md`. The protocol file is committed
without implementation-driven changes and has SHA-256
`2cbb2452d2ea1f167a844e63b52bee4e15e3b8bf2adad7feb5dc86dd1d41c7fe`.

The new evidence path combines (1) external evaluation on a benchmark carrying
upstream answer/document labels and (2) a cross-family LLM jury followed by
author-blind adjudication. It does not relabel either component as independent
human annotation, human IAA, externally held blind testing, or publication-grade
human gold. Any later protocol clarification follows the deviation rules in
section 7 of the preregistration document.

## 2026-07-04: deviation — clarify RAMDocs provenance and exact match

This clarification occurred before any RAMDocs development or held-out scoring.
Source inspection pinned the Hugging Face dataset at revision
`9c041bfd158c603b615883d9a931b00cbc141494` and the upstream code repository at
commit `d44454c9ebb0bf513d8236a03decc9fb58704cad`. RAMDocs contains 500 questions
under MIT. Its valid answers derive from AmbigDocs, while misinformation is
constructed by answer/entity replacement and noise is retrieved. It is therefore
an independently published, upstream-labeled external benchmark, not a clean
substitute for independent human IAA or publication-grade human gold.

The paper specifies strict exact match as containing every gold answer and no
incorrect/misleading answer, but the public repository does not include a
standalone official scorer. Before implementation, the active protocol freezes a
normalised containment implementation of that published criterion and requires
separate gold-coverage and wrong-answer-exclusion diagnostics. The active
protocol SHA-256 after this clarification is
`45b1ca998a09c2349fe805805730117791f4b90663d0241ebbbc513074d51fd7`;
the original preregistered fingerprint remains recorded above.

## 2026-07-04: deviation — make jury label space and support proxy explicit

This clarification occurred before any jury annotation and before any RAMDocs
scoring. The benchmark has five positive conflict types, but blind jurors must be
allowed to conclude that no conflict exists. G-K therefore uses the honest
six-label space (five positive types plus `no_conflict`) rather than forcing a
positive label. The preregistered binary fallback and all thresholds are
unchanged.

RAMDocs does not provide claim-level support annotations for generated answers.
The auxiliary “unsupported claim rate” is consequently renamed and frozen as an
unsupported-sentence lexical proxy: split the answer into non-empty sentences,
compute normalised token F1 against every upstream `correct` document, and mark a
sentence unsupported when its maximum F1 is below 0.50. This diagnostic is not
described as a human factuality judgement.

The active protocol SHA-256 after this clarification is
`a38d048eb280eb7e3f0fdb316f3a57a298c983a22549712bcfa9c6e937c6c9f2`.

## 2026-07-04: deviation — freeze joint consensus and author self-consistency

This clarification occurred before jury aggregation and before author
adjudication. Type-level G-K remains unchanged. Promotion of an unadjudicated
jury row now requires a joint majority over conflict presence, conflict type,
revision action, and revised-answer acceptability, preventing an incoherent gold
row assembled from unrelated field-wise votes. The author G-S score uses exact
agreement over the same four categorical fields; free text is intentionally
excluded. The 20% second-pass sample is fixed as 12 rows from each of the five
construction categories (60 total), selected deterministically without exposing
round-one labels.

The active protocol SHA-256 after this clarification is
`e629d57e0d495380c4090943c7ad694740ad0e6e130d8f1dfd0d57507141d6c1`.

## 2026-07-04: deviation — stratify the 20% repeat within disputed rows

This correction occurred before any jury result or author adjudication existed.
The author only adjudicates the disputed layer, so a fixed 12 rows per original
construction category could exceed the available disputed rows. The repeat is
therefore the deterministic, category-stratified ceiling of 20% of disputed rows
in each category. The 14-day minimum and G-S threshold remain unchanged.

The active protocol SHA-256 after this correction is
`0b4c69868339cb018d8a83ada2663dc3047f251e4ea41d09b2ec92dde0f1769b`.

## 2026-07-04: deviation — resolve current DeepSeek model and fallback accounting

This change occurred before any new jury or model-matrix run. The planned
`DeepSeek V4-Flash` identifier is not an available model identifier in the
project's current DeepSeek adapter. J1 is pinned to the provider's
`deepseek-chat` API model, preserving the DeepSeek family boundary. The API key
previously pasted into chat is treated as compromised and is not reused; a
rotated environment-only credential is required before J1 can run.

For the matrix's preregistered 30% structured-output exclusion rule, a sample is
counted as a fallback if any generated query lacks the runner's `llm:` tactic
marker or any changed revision lacks the configured-LLM realization marker.
This trace-derived definition is frozen before Mistral or Gemma execution.

The active protocol SHA-256 after this change is
`e0221cfa9569ba089136fd017c1175ad282643c4c773b5f661f42ba95c9d7d00`.

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

`annotate_packet status` now gives the human annotation owner a non-mutating
handoff check: per-reviewer completed/blank/invalid counts, adjudication
progress, benchmark/corpus fingerprint compatibility, visible-field mismatch
previews, and booleans for `ready_to_export_adjudication_label_studio` and
`ready_to_compile`. On the current strict packet it reports 300 blank rows for
each reviewer and adjudication, matching the fact that no human labels have been
returned yet.

A fresh strict packet was then generated locally at
`outputs/annotations/falsirag_packet_v1/`, together with separate prediction-free
Label Studio bundles for `reviewer_a` and `reviewer_b`. Both contain 300 tasks,
zero predictions, reviewer-bound context hashes, and standalone instructions.
The packet manifest SHA is
`ae12cf5dcdc0a7ac202dbbc5e3c8a47136c37f8fcf8289c5b5847e2b9c923b24`;
reviewer task SHAs are
`3691e27117a722ef8827282235b2609ebd4a8a33a4c878924ba19f327f03c6ab`
and `f627faf8fdf7c9f71af748926654d8578ae4792647b2c072b9af75db18005e19`.
`falsirag-annotate-packet reviewer-handoff` now also builds deterministic
single-reviewer file-based ZIPs from the same blank templates while excluding
the other reviewer, packet manifest, source benchmark, and machine predictions.
The current ignored ZIP SHAs are `reviewer_a_handoff.zip`
`304ec1db46f6d3b940f7acd37b8474c7b834bdc8448b8f0f5bb08b48abdde1e4` and
`reviewer_b_handoff.zip`
`dd12819bc2592086e23f552cfb70808d66a390cea7a819d6cc7b852c3bfa5c8e`.
They are blank handoff artifacts, not completed human annotations.

## 2026-07-03: Single-author machine-audited study profile completed

The strict human-publication gate remains unchanged, but it is no longer the
only way to reach a well-defined project endpoint. Added
`falsirag-machine-consensus`, which treats controlled benchmark-construction
labels as the reference and freezes how non-gold LLM preannotations and
deterministic weak labels agree, abstain, fall back, or dispute each row. It
rejects stale fingerprints, incomplete sample sets, duplicate source IDs, and
sources that do not explicitly remain `publication_gold:false`.

The current 300-row audit records 299 effective Qwen2.5 labels after one
conservative fallback and 211 non-abstaining rule labels. At least one
non-abstaining machine signal exactly confirms the construction conflict/action
pair for 178 rows; the remaining 122 are retained as machine-disputed
limitations rather than silently promoted to consensus.

Added the separate `falsirag-solo-readiness` gate. It validates the candidate
benchmark, machine-consensus evidence, all 11 complete Qwen development
methods, and the 58-row gold-free technical test bundle. The current local
report passes all four gates with `complete:true`. Its schema explicitly
forbids claims of human gold, human IAA, external blind custody,
publication-ready final evidence, or multi-model generality. The existing
`falsirag-submission-readiness` path continues to require real external roles
and is not weakened by this profile.

The external blind-test handoff was also tightened. `falsirag-build-blind-bundle`
now has `audit` and `package` subcommands. `audit` requires the bundle to contain
exactly `blind_bundle_manifest.json`, `corpus.jsonl`, and
`splits/test_inputs.jsonl`, recomputes manifest fingerprints, verifies the
five-field test schema, recursively rejects gold/provenance keys, and refuses
directories whose name contains `technical` unless a dry-run override is
explicitly supplied. `package` builds a deterministic custodian ZIP containing
only the audited blind bundle, selected config files, a run sheet, and a
handoff manifest. This reduces the risk of accidentally sending the
machine-seeded technical dry run, adjudicated gold, local score files, or
credentials to the external custodian.

## 2026-07-03: Public diagnostic evidence release

The previously ignored local Qwen and machine-audit outputs are now exported as
the tracked `diagnostics/solo_v1/` evidence bundle. It contains 69 fingerprinted
files (about 4.5 MB): all 11 methods' complete 60-row dev predictions, run
identities, run manifests, scores, evaluation reports, two tables, three
figures, the 300-row machine consensus audit, and the gold-free test technical
audit. This closes the gap where README claims could only be checked against
one workstation's ignored `outputs/` directory.

Added `falsirag-solo-release build|verify`. Verification recomputes the exact
file set, all SHA-256 bindings, result-bundle signatures, prediction/report and
report/score links, and artifact outputs. It also rejects symlinks and any
attempt to claim publication gold, human IAA replacement, strict-gate impact,
or publication readiness. The release verifies successfully while remaining
explicitly `publication_ready:false`; it does not change the strict AAAI gate.

## 2026-07-03: Frozen FEVER binary transfer diagnostic

The 100-pair external FEVER candidate set was separated into what its
provenance actually supports. SUPPORTS/REFUTES labels and evidence are inherited
from human-annotated FEVER; temporal, numeric, source, and definition sampling
buckets are machine heuristics and remain `publication_gold:false`. Added
`falsirag-eval-fever-binary run|verify`, a pinned NLI configuration, source
fingerprint and transformation audits, prediction/config/README fingerprints,
metric and confidence-interval recomputation, paired bootstrap, and exact
McNemar verification.

On the frozen visible slice, the heuristic detector obtains accuracy 0.72,
precision 1.00, recall 0.30, and F1 0.462. VeraRAG NLI obtains accuracy 0.72,
precision 0.80, recall 0.40, and F1 0.533. Its paired accuracy difference is
0.00 (95% bootstrap [-0.05, 0.05]); four samples improve and four regress, so
exact McNemar `p=1.0`. The result is retained as an honest external-transfer
failure signal and frozen without tuning. It is not full FAR, typed gold,
external blindness, or a publication-ready main result.

## 2026-07-03: Single-author diagnostic report added

Added `reports/single_author_diagnostic_report.md` as the durable reader-facing
deliverable for the no-human-annotator path. The report summarizes the public
solo evidence bundle, Qwen 11-method dev suite, machine-consensus audit,
diagnostic figures, and the frozen FEVER binary transfer result. It opens with
the permitted diagnostic claim and keeps the forbidden strict claims explicit:
no human gold, no human IAA, no externally held blind test, no final multi-model
generality, and no AAAI main-table evidence.

The report intentionally preserves negative and mixed evidence. FAR has the
strongest local counter-evidence recall and a positive typed-versus-untyped
mechanism signal, but revision accuracy remains modest; the refutation,
boundary, and typed-revision ablations are not monotonic; and FEVER transfer
does not improve paired accuracy. README, the completion audit, proposal
traceability, and paper status now point to the report so the diagnostic
profile has a complete public handoff without weakening the strict submission
gate.

## 2026-07-03: Public solo diagnostic one-command check

Added `scripts/solo_diagnostic_check.sh` as a lightweight verifier for the
single-author diagnostic path. Unlike the full release gate, it does not require
human labels, cloud credentials, ignored local outputs, or external custody. It
verifies `diagnostics/solo_v1/`, verifies the frozen FEVER binary diagnostic,
runs the report/evidence consistency tests, and checks that the reader-facing
report is included in the source distribution. This gives reviewers and future
maintainers one command for the public diagnostic deliverable while keeping the
strict AAAI submission gate separate and fail-closed.

## 2026-07-03: Scarce-review automation fallback triage

The project cannot honestly synthesize two independent human reviewers from
software. The chosen fallback is therefore a reproducible triage layer on top of
the existing machine consensus audit, not a new gold-label source. Added
`falsirag-review-priority`, which reads the frozen
`machine_consensus_rows.jsonl` and writes
`reports/solo_human_review_priority.csv`.

The tracked CSV contains exactly the 122 `machine_disputed` rows, sorted by
machine/reference disagreement strength and then by stable identifiers. It
exposes sample ID, category, construction reference conflict/action, Qwen
preannotation signal, deterministic weak-label signal, claim-limitation flag,
and a plain-language triage reason. It deliberately omits revised-answer text
and revised-answer hashes. The table answers the practical single-author
question: if only a small amount of review time appears later, which rows should
be inspected first? It remains `publication_gold:false` in interpretation and
does not alter the strict submission gate.

## 2026-07-03: Generated dual-track project status snapshot

Added `falsirag-project-status` plus the tracked
`reports/project_status_snapshot.md` and `.json` outputs. The snapshot reads
current repository evidence instead of copying prose from the plan: benchmark
validation, the 69-file solo diagnostic release verifier, frozen FEVER binary
verification, the 122-row review-priority table, reader-facing report files, and
the fail-closed strict submission readiness audit against the tracked template.

The generated status ledger records the single-author machine-audited
diagnostic track as complete while keeping the strict AAAI submission track
false with explicit blockers for human annotation, adjudicated dev runs, final
blind bundle, external returns, attestation, trusted scoring, release archive,
and human paper review. It is intentionally a lightweight status audit; the
full `scripts/release_check.sh` gate remains responsible for release-package and
paper-build validation.

## 2026-07-03: Project-status freshness added to the solo gate

Added a read-only `falsirag-project-status --verify` mode. It rebuilds the
status object from current repository evidence, renders the reader-facing
Markdown in memory, and compares both forms with the tracked snapshots. Missing,
malformed, or stale JSON/Markdown now fails with an explicit error and no file
mutation. `scripts/solo_diagnostic_check.sh` runs this verifier and its focused
tests, so the one-command public diagnostic gate can no longer pass while its
headline project-status ledger is out of date.

## 2026-07-03: Public continuous integration added

Added a least-privilege GitHub Actions workflow for the public repository. A
Python 3.10--3.13 matrix installs only FAR's locked public `dev` and `eval`
dependencies and runs the complete test suite. A separate Python 3.12 job runs
format/lint, static types, the redacting secret scan, candidate-benchmark
validation, and the one-command public diagnostic gate. No API credential or
local VeraRAG checkout is used. Third-party actions are pinned to full commit
hashes, and contract tests preserve the supported-version matrix, read-only
permissions, secret-free design, and required diagnostic commands.

## 2026-07-03: Built distributions now receive isolated smoke tests

Added `scripts/check_release_packages.sh` and `scripts/package_smoke.py`. After
building, the release gate installs the wheel and source distribution into two
independent ephemeral `uv` environments and launches Python in isolated mode,
outside the repository working directory. The smoke probe verifies installed
package metadata/imports, required console entry points, the packaged offline
configuration, and the complete packaged candidate benchmark with its frozen
0.91 counter-evidence recall. The public CI diagnostic job runs the same check,
closing the gap between source-tree tests and actually installable artifacts.

## 2026-07-04: Relaxed machine-audited paper profile

The user authorized a transparent relaxation because no independent human
annotators are available. Added `falsirag-solo-paper-readiness` as a profile
that is deliberately separate from strict AAAI readiness. It verifies the
tracked 69-file solo release, frozen FEVER diagnostic, exact paper source, and
the observed four-way ablation pattern. The gate requires the paper to state
that refutation and boundary removal do not hurt answer correctness and that
removing typed revision raises answer correctness while zeroing revision
metrics. It rejects pending empirical cells and broad component claims.

The paper now includes the fingerprinted Qwen dev main and ablation tables. Its
positive claim is limited to typed-versus-untyped control: +0.078 answer
correctness, +0.420 typed-conflict F1, and +0.217 revision accuracy. It also
reports the FEVER paired-accuracy null result and explicitly disclaims human
gold, external blindness, and multi-model generality. The relaxed profile is
ready; the original strict human/external gate is unchanged and false.

A post-hoc machine-disposition sensitivity check further separates the 60 dev
rows into 35 machine-confirmed and 25 machine-disputed examples. FAR's paired
answer-correctness advantage over untyped remains positive in both groups:
+0.101 (95% bootstrap [0.039, 0.161]) and +0.047 ([0.001, 0.094]),
respectively. The paper reports this only as a category-imbalanced sensitivity
analysis, not independent label validation.

The first public CI run exposed cross-version report drift at approximately
1e-17: Python 3.10/3.11 and 3.12/3.13 summed the same paired values to slightly
different final binary floats, so exact tracked-JSON equality failed. The
readiness generator now rounds derived sensitivity statistics to 15 decimal
places at its serialization boundary. Explicit clean environments on Python
3.10 and 3.11 reproduce the same tracked reports without weakening equality
checks.

## 2026-07-04: RAMDocs formal dev runtime restart

The first RAMDocs dev formal attempt on the Windows GPU was stopped before any
scored suite output existed. At diagnosis it had only a partial initial-answer
checkpoint, no oracle metadata leakage, no duplicate samples, and no logged
errors, but the Qwen Ollama configuration used `unload_after_sample: true`. That setting forced
the 9B model to unload after every RAMDocs item and reload for the next item,
turning a runtime hygiene choice into a multi-day bottleneck.

This is a runtime-only deviation: data, split, prompts, model tag, temperature,
metrics, baselines, G-A rule, and test access policy are unchanged. The RAMDocs
Qwen config now keeps the model alive for 24 hours, does not unload after each
sample, and uses a new cache namespace so the replacement formal run cannot
reuse responses from the abandoned attempt. The abandoned output directory must
not be used as evidence; the replacement run starts from an empty output tree
and binds to the new commit/config hash.

## 2026-07-04: RAMDocs dev checkpoint recovery during Phase A

During heartbeat monitoring, the replacement RAMDocs dev run was found without
the `far-ramdocs-phase-a` tmux session or a live Python suite process. The
output tree remained intact: initial answers were complete at 350/350, FAR was
complete with 350 predictions and an evaluation report, and
`far_minus_typed_conflict` had a partial checkpoint at 275/350. No suite
manifest existed, so G-A was not evaluated.

The immediate recovery failed because the Ollama service had also stopped and
`http://localhost:11434` refused the model-identity inspection request. Ollama
was restarted in tmux session `far-ollama-2plus4` with
`OLLAMA_MODELS=/mnt/d/FAR-models/ollama`, exposing the pinned `qwen3.5:9b`
model from D:. A second recovery attempt failed before writing additional
samples because the manual tmux command did not inherit the D:-backed
HuggingFace cache variables, so the pinned NLI model could not be resolved in
offline mode.

The formal suite was then restarted again from the same output directory and
commit after sourcing `scripts/windows_gpu_env.sh`, restoring
`HF_HOME=/mnt/d/FAR-models/huggingface`,
`HUGGINGFACE_HUB_CACHE=/mnt/d/FAR-models/huggingface/hub`, and
`OLLAMA_MODELS=/mnt/d/FAR-models/ollama`. The existing checkpoints make this a
resume of the same replacement run, not a new scored attempt. The transient
tracebacks are preserved in `/mnt/d/FAR-outputs/ramdocs_dev_v1.log` as recovery
diagnostics; they occurred before additional samples were appended after the
D:-cache environment was restored.

## 2026-07-05: RAMDocs dev resumed after Windows/WSL restart

Heartbeat inspection found that both formal tmux sessions and their processes
had disappeared after the Windows/WSL environment restarted. The last durable
write was `crag_style_reproduction` row 86 at 01:10 +08:00. Initial answers and
the first five completed method outputs remained intact, no suite manifest had
been created, and the formal worktree was still clean at `08e04c6`. The kernel
log contained no OOM, killed-process, NVIDIA Xid, or other experiment failure;
the formal log also contained no new traceback after the previously documented
D:-cache recovery marker.

Ollama was restarted in `far-ollama-2plus4` with its model store on D:, then the
suite was resumed in `far-ramdocs-phase-a` from the same output directory and
commit after sourcing `scripts/windows_gpu_env.sh`. Process inspection confirmed
that the live Python process uses the D:-backed HuggingFace and Ollama paths.
The pinned `qwen3.5:9b` digest is unchanged, its 24-hour residency is active,
and the checkpoint advanced from 86 to 94 without a new error. This remains a
checkpoint continuation of the single replacement formal run; G-A has not yet
been evaluated and Phase B has not started.

## 2026-07-05: Windows training keepalive corrected for systemd linger

Further monitoring established the cause of repeated simultaneous Ollama and
suite termination. The WSL virtual machine remained online and the kernel had
no OOM or NVIDIA error, but `loginctl` reported `Linger=no`. Roughly twelve
seconds after the final SSH session disconnected, systemd stopped the user's
tmux transient scopes. The suite therefore recorded `KeyboardInterrupt` while
waiting for Ollama, and Ollama shut down at the same instant. Checkpoints were
durable at CRAG-style rows 315, 318, and 320 across the diagnosis; no completed
sample was lost or regenerated.

The Windows scheduled task already ran a root WSL keepalive, but that only kept
the VM alive. Its script now also executes `loginctl enable-linger wenyao` before
starting SSH/Tailscale and retains the root VM keepalive loop. Linger preserves
the user manager, but a second disconnect test showed that a tmux server first
created inside an SSH login can still remain attached to that login's lifecycle.
The final arrangement therefore runs the tmux server itself as the enabled
`far-tmux-server.service` user unit with foreground `tmux -D`; training sessions
are children of that persistent server rather than of an SSH session.

A 40-second isolation test with every SSH connection closed confirmed that the
systemd service PID and its tmux pane PID were unchanged. After installing and
enabling the persistent unit, a second 45-second no-SSH test kept the formal
Ollama and suite sessions alive and advanced CRAG-style from row 321 to 322 with
no new error. The tracked PowerShell script, systemd unit, and launcher now
document and enforce the durable setup: the launcher fails closed unless linger
is enabled and the persistent tmux service is active. This is an operational
reliability correction only: the formal output directory, code commit
`08e04c6`, model/config fingerprints, data split, and scoring protocol are
unchanged.

## 2026-07-05: Formal WSL jobs moved from tmux panes to user services

The persistent tmux server test isolated one more WSL/systemd lifecycle edge:
linger kept the tmux server service alive, but panes created from an SSH client
were still placed in transient `tmux-spawn-*.scope` units and stopped shortly
after that login disconnected. The server PID survived while the Ollama and
suite panes exited together. CRAG-style checkpoints remained durable at rows
321 and 334, and the exits again occurred before an in-flight sample could be
appended.

The actual long-lived processes now run directly as enabled systemd user
services: `far-ollama-2plus4.service` and `far-ramdocs-phase-a.service`. The
suite unit requires Ollama, waits for its API, sources the committed D:-backed
environment, appends to the existing formal log, resumes the same checkpoint,
and restarts only on failure. With every SSH connection closed for 45 seconds,
both service PIDs stayed unchanged, restart counters remained zero, and the
checkpoint advanced from 334 to 339 without a new error. The tracked launcher
now starts these services rather than tmux panes. `far-tmux-server.service`
remains useful for interactive shells, but formal process survival no longer
depends on tmux scope behavior.

At 11:06 +08:00 both formal services were stopped again at Self-RAG-style row
133. This event was not a runner failure: systemd recorded `Result=success`, no
restart, an explicit stop of each unit, two reload requests from `systemctl`
client processes, and removal of both enabled symlinks. That evidence is
consistent with a client-issued `disable --now`, not automatic service cleanup
or an experiment exception. The originating command cannot be attributed
because process-exec auditing was not enabled; neither the tracked scripts nor
the Windows scheduled tasks contain a matching stop/disable action. Both units
were re-enabled and resumed from row 133 with the same formal identity. The new
start marker contains the verified D:-backed environment, and the checkpoint
advanced without a new runtime error.

The same explicit disable pattern repeated at 11:13 +08:00 after the next SSH
tool session ended, stopping Self-RAG-style at row 161. The short-lived SSH
session, paired `systemctl` client PIDs, and approximately eighteen-second
delay identify the execution environment's remote-process cleanup rather than
the project runtime. To make the formal run independent of that cleanup, the
existing Windows-owned keepalive task now watches a D:-backed authorization
marker every fifteen seconds. While the marker exists and no suite manifest is
present, it re-enables and starts the two formal user services through WSL root;
when the manifest appears it removes the marker and stops intervening. Manual
stops must remove the marker first. This watchdog cannot alter predictions,
configuration, checkpoints, or scoring; it only restores the declared service
processes for the same formal run.

The watchdog also honors the GPU sharing rule: if FAR's Ollama unit is not
already active, it samples WSL NVIDIA memory and utilization before starting
either service. More than 1500 MiB allocated or more than 20% utilization is
treated as another GPU workload and leaves FAR waiting; the transition is
logged once on D:. If FAR's own Ollama is already active, its allocation is
expected and the suite may resume. At deployment no other compute process was
present, so the current formal run resumed immediately.

## 2026-07-05: RAMDocs dev completed and G-A stop rule triggered

The single replacement formal run completed all 350 dev samples for FAR, the
typed-conflict ablation, and all six baselines. Every method has 350 predictions,
a run manifest, and an evaluation report. The formal suite verifier returned
`valid=true` with no fingerprint error, the frozen protocol fingerprint
`e0221c…`, and data-manifest fingerprint `5cd9ff…`. No RAMDocs test input was
accessed.

FAR and the automatically selected strongest baseline, Multi-Query RAG, both
scored 109/350 strict exact match (0.3114). Their paired difference is 0.0000,
with bootstrap 95% CI [-0.0286, 0.0314] and exact McNemar p=1.0 (16 FAR-only,
16 baseline-only). G-A is therefore false and the preregistered stop rule is
active. No jury annotation, author adjudication, jury gold, multi-model matrix,
or one-shot test evaluation was started; LLM jury tooling remains tooling, not
human IAA.

The verified 53-file RAMDocs evidence release is frozen at
`diagnostics/ramdocs_v1/dev`. A deterministic dev error analysis is stored at
`diagnostics/ramdocs_v1/error_analysis`: 93 rows are correct for both methods,
225 fail for both, and the 32 discordant rows split evenly. FAR has slightly
higher gold coverage (0.7510 vs 0.7457) but slightly lower wrong-answer
exclusion (0.5686 vs 0.5743). Among the 16 baseline-only rows, FAR misses at
least one gold answer in 11 and retains a wrong answer in 9; the analogous
counts for Multi-Query on FAR-only rows are 11 and 6. This identifies answer
selection and wrong-answer suppression, rather than conflict detection alone,
as the immediate dev bottleneck. The formal services were disabled after the
evidence bundle verified successfully, releasing the GPU.
## 2026-07-05 — RAMDocs dev Round 2 方法修订（评测前）

- Round 1 已完成并触发 G-A 停止规则；Phase B、jury gold、多模型矩阵与
  RAMDocs/FalsiRAG test 继续禁止执行。
- dev 错误分析显示 FAR 与最强基线各有 16 个独占正确样本；FAR 的数值修订
  在 discordant 样本上净增益为正，但 `retract` 动作净损失，且 225 个样本
  两者共同错误。主要失败是多答案覆盖不足与错误候选未从最终答案中剔除。
- Round 2 增加一个仅由配置启用的最终证据合并层。输入只包含问题、初始答案、
  类型化修订草稿/轨迹以及已去除 `document_type` 元数据的闭集文档；不加载
  `gold_answers` 或 `wrong_answers`。目标是按实体、时间、范围和独立证据支持
  合并答案，并从最终文本中删除已拒绝候选。
- Round 1 配置与证据保持不变。Round 2 使用
  `experiments/configs/ramdocs_qwen_round2.yaml`、独立缓存 namespace 和独立输出
  目录。正式 dev 重跑将记为第二轮；若 G-A 再次失败，严格执行论文降级规则。
- 仅 FAR 方法发生变化，因此 Round 2 复用 Round 1 已冻结且有 SHA-256 指纹的
  初始答案与最强基线分数，只重跑 FAR 350 条；最终仍对同一 350 个 sample ID
  做配对比较。D 盘作业由 `far-ramdocs-round2.service` 执行，Windows watchdog
  只在 `ramdocs_dev_v2.keep-running` marker 存在且 GPU 空闲时恢复它，并在 FAR
  run manifest 完成后停止 Ollama、释放 GPU。

## 2026-07-05 — 修复 G-K 二分类降级的端到端语义

- 完成实现审计时发现：旧版 `jury_consensus` 在六分类 κ 失败、二分类 κ
  通过时，只把报告字段设为 `active_label_granularity=binary`，样本多数票、联合
  多数与 disputed 分层仍使用六分类冲突类型。这不满足预注册的“降级为二分类
  冲突标签重算”。
- 现已让二分类回退实际使用 `conflict/no_conflict` 投票，并在联合多数中移除
  未获一致支持的类型字段；原始类型票仍单独留痕。编译标签显式记录
  `label_granularity`，二分类标签不再继承某个陪审员的具体类型作为类型金标。
- 评分层新增 corpus-level `conflict_presence_f1`、bootstrap 与配对比较；敏感性
  和多模型矩阵按标签粒度选择 presence-F1 或 typed-conflict-F1。论文 readiness
  同时核验实际使用的粒度和相应冲突指标，继续禁止把二分类回退写成类型一致性。
- 这是对冻结协议既有降级预案的实现修复，不修改 G-K 阈值、家族隔离、G-S、
  G-A 或停止规则；当前 G-A 未通过，Phase B 仍未执行。

## 2026-07-05 — 对齐 Round 2 证据目录默认值

- `falsirag-jury-paper-readiness` 的默认 Round 2 RAMDocs 证据目录曾指向
  `diagnostics/ramdocs_v2/dev`，而 Round 2 release builder 与项目状态账本使用
  `diagnostics/ramdocs_v2/round2`。这会让默认 readiness 检查在证据同步后漏看
  已冻结的 Round 2 manifest。
- 已将默认值改为 `diagnostics/ramdocs_v2/round2`，只影响证据发现路径，不修改
  G-A 判据、停止规则、任何分数或任何 test 访问状态。

## 2026-07-05 — 修复 Windows GPU Ollama 自退出后的恢复策略

- Round 2 运行到 105/350 时，`ollama serve` 在一次 `/api/generate` 500 后以
  status 0 自退出；由于 `far-ollama-2plus4.service` 使用
  `Restart=on-failure`，systemd 没有自动拉起 Ollama，而 RAMDocs runner 对
  Ollama 使用硬 `Requires=`，因此被连带 `SIGTERM` 停止。没有 Python
  traceback、OOM、CUDA error 或 test 访问。
- 已将 Ollama unit 改为 `Restart=always`，并把 RAMDocs suite/round2 unit 对
  Ollama 的硬依赖改为 `Wants=`。这只改变 D 盘 Windows GPU 作业的服务恢复
  行为，不修改实验协议、配置、指标、G-A/G-K/G-S 判据、checkpoint 或任何
  test 状态。

## 2026-07-05 — Round 2 等待 GPU，不抢占 VeraRAG/SelfRAG

- 22:43 +08:00 通过 `ssh windows-gpu` 复核：`far-ramdocs-round2.service` 与
  `far-ollama-2plus4.service` 均为 inactive；`ramdocs_dev_v2.keep-running`
  和 `ramdocs_dev_v2.waiting-for-gpu` marker 仍存在，说明 watchdog 仍应在
  GPU 空闲后恢复 Round 2。
- `/mnt/d/FAR-outputs/ramdocs_dev_v2/runs/far/checkpoint.jsonl` 为 105 行，
  最后修改时间 2026-07-05 17:14 +08:00；尚无 Round 2 `run_manifest.json`
  或 `predictions.jsonl`，因此不能 finalize、verify 或改判 G-A。
- GPU 当时约 5681 MiB、25% utilization，被 VeraRAG/SelfRAG 的
  `official_self_rag` test split 进程占用。按用户指令，FAR 不抢占 GPU，
  不停止 VeraRAG/SelfRAG，也不切换正在运行用的 detached
  `/mnt/d/FAR-workspace/FAR-2plus4` 工作树。
- 未访问或运行任何 test；本条只记录运维状态，不改变 Round 2 方法、协议、
  阈值或任何证据指纹。

## 2026-07-05 — 补齐 Round 2 安全恢复入口

- 新增 `scripts/start_windows_ramdocs_round2.sh`，用于在 Windows/WSL GPU 主机上
  恢复 `/mnt/d/FAR-outputs/ramdocs_dev_v2/runs/far` 的 FAR-only Round 2
  checkpoint。该脚本复用 D: 盘模型/cache 配置和 systemd user services。
- 启动器会先确认 Round 1 suite manifest 已存在、Round 2 尚无
  `run_manifest.json`、systemd linger 与 `far-ollama-2plus4.service` /
  `far-ramdocs-round2.service` 均已安装。GPU 忙时只写入 keep-running 与
  waiting-for-gpu marker，不启动 FAR 或 Ollama；GPU 空闲时才启动服务。
- 同步更新 `docs/PLAN_2PLUS4_EXECUTION.md`，把 Phase A 与 Round 2 的 unit
  安装、启动、状态查看和人工中止命令分开记录。此变更只补齐运维入口，不修改
  Round 2 方法、G-A/G-K/G-S 阈值、停止规则或任何 test 状态。

## 2026-07-05 — 防止 Round 2 checkpoint 跨提交误续跑

- 复核远端状态后确认：当前 105/350 的 Round 2 checkpoint 绑定在
  `/mnt/d/FAR-workspace/FAR-2plus4` 的 detached commit `d8d5f40`，该工作树尚无
  新增的 `start_windows_ramdocs_round2.sh`。由于 `CheckpointWriter` 会比较
  `run_signature`，而正式 run identity 还绑定 clean Git revision，不能为了使用
  新脚本切换到最新 `main` 或把脚本复制进旧工作树造成 dirty 状态。
- 已给新 Round 2 launcher 增加防护：若 `run_identity.json` 已存在，它会读取
  其中的 `source_revision.git_commit`，并拒绝从不同 commit 续跑；同时任何 dirty
  worktree 都会 fail-closed。执行手册也明确当前未完成 checkpoint 应由 Windows
  watchdog 或原 detached 工作树上的既有 systemd units 恢复。
- 该修正只防止运维误操作，不改变现有 checkpoint、方法实现、配置、指标、G-A
  判据或任何 test 状态。

## 2026-07-05 — 恢复 Round 2 FAR-only dev 运行

- 22:52 +08:00 复核远端 GPU：VeraRAG/SelfRAG 计算进程已结束，`nvidia-smi`
  只显示 Xwayland 图形进程；按用户“无任务则直接上进程”的指令，保持
  `/mnt/d/FAR-workspace/FAR-2plus4` 在 detached commit `d8d5f40` 且 clean 的状态，
  删除 `ramdocs_dev_v2.waiting-for-gpu` marker，并直接启动既有
  `far-ollama-2plus4.service` 与 `far-ramdocs-round2.service`。
- 22:53 +08:00 两个服务均为 active；`ollama serve`、`python -m
  experiments.run_ramdocs ... --method far --split dev` 和 `llama-server` 均在运行，
  GPU 显存约 7.6–7.9 GiB、利用率最高 100%。恢复时 checkpoint 仍为 105/350，
  最后一条 `RAM0139`，尚无 `run_manifest.json` 或 `predictions.jsonl`。
- 未切换远端工作树，未复制新脚本到旧 detached checkout，未访问或运行任何 test；
  后续需继续监控 checkpoint 是否从 105 前进，以及是否出现 Ollama/API 错误。

## 2026-07-05 — 增加 Round 2 只读慢解码监控

- 新增 `scripts/check_windows_ramdocs_round2.sh`，用于在 Windows/WSL GPU 主机上
  只读检查 Round 2 状态：systemd 服务、keep-running/waiting marker、checkpoint
  行数与最后样本、GPU、相关进程、Ollama `n_decoded` 尾部，以及 run log 错误。
- 该脚本不启动、不停止、不重启服务，也不改 checkpoint。它的目的只是区分“当前
  样本慢速解码但仍在推进”和“服务异常退出/卡死”，避免把长样本误处理为需要
  重启的故障。当前 105/350 续跑样本属于前者：GPU 100%，`llama-server` CPU
  时间增长，Ollama `n_decoded` 从 114 → 126 → 138。
- 此变更不改变实验协议、方法、配置、阈值或任何 test 状态。

## 2026-07-05 — Round 2 恢复后确认推进

- 23:09 +08:00 复核远端：`far-ramdocs-round2.service` 与
  `far-ollama-2plus4.service` 仍 active，GPU 约 7.9 GiB / 100%。恢复后
  checkpoint 已从 105/350 推进到 108/350，最后观测样本为 `RAM0145`，且
  `final_answer_consolidation.applied=true`。
- 这确认了 22:53 恢复后的慢样本不是卡死；Ollama 样本内多次调用完成后已追加
  新行。尚无 `run_manifest.json` 或 `predictions.jsonl`，因此仍未完成，不能
  finalize/verify 或改判 G-A。
- 未访问或运行任何 test，未切换远端 detached 工作树，未改变运行配置。

## 2026-07-05 — Round 2 持续推进到 114/350

- 23:12 +08:00 复核远端：两个 systemd user services 仍 active，GPU 约
  7.9 GiB / 94%，checkpoint 已推进到 114/350，最后观测样本为 `RAM0156`，
  且 `final_answer_consolidation.applied=true`。
- 尚无 `run_manifest.json` 或 `predictions.jsonl`，因此 Round 2 尚未完成，不能
  finalize/verify 或改判 G-A。未访问或运行任何 test。

## 2026-07-05 — 修复 Windows Round 2 watchdog 部署漂移

- 23:20 +08:00 静态交接核查发现：仓库中的
  `scripts/watch_windows_ramdocs_services.sh` 已支持优先识别 Round 2 marker，
  但 Windows 实际循环调用的 `/mnt/d/FAR-tools/` 副本仍是只识别 Round 1 的旧版。
  这不会中断当前运行，却会导致 Round 2 异常退出后无法按文档自动恢复。
- 已仅同步该运维脚本到 D: 盘工具目录并设为可执行；本地与远端 SHA-256 均为
  `c9c1296c33442402e6e772e67dd0c5b419019beaccfe7de9514db8cf2bde790f`。
  正式实验工作树仍 clean 且保持 detached commit `d8d5f40`，checkpoint 未修改，
  两个服务仍 active，同步后继续推进到 126/350。
- 新版 watchdog 在 Round 2 `run_manifest.json` 出现后会移除 marker 并停止
  Round 2/Ollama 服务；异常退出时则先遵守 GPU 占用门禁，再恢复同一 checkpoint。
  未访问或运行任何 test，未改变方法、配置、协议或 G-A 判据。

## 2026-07-05 — 关闭 Round 2 完成 manifest 的竞态窗口

- 进一步静态核查 runner 完成路径时确认：`CheckpointWriter.finalize()` 会先写基础
  `run_manifest.json`，调用方随后才补写 `gold_loaded_by_runner=false` 等 RAMDocs
  字段。旧 watchdog 只检查文件存在，理论上可能在两次原子写之间把基础 manifest
  误判为完成并停止 runner。
- watchdog 现仅在 Round 2 manifest 同时满足 `status=complete`、`partial=false`、
  `split=dev`、`expected=completed=350`、`gold_loaded_by_runner=false` 时才删除 marker
  并释放 GPU；JSON 不完整、字段缺失或系统 `python3` 不可用时均失败关闭并继续等待。
  Round 1 既有完成语义保持不变。
- 已通过 shell 语法检查，并把 D: 盘实际执行副本更新为 SHA-256
  `a312bb944133010ca88b82fb2ad3b1cafad533dfbb585a1a06b3ee9f2dcf09f3`；远端
  `/usr/bin/python3` 可用。同步时 Round 2 已推进到 129/350，两个服务仍 active，
  尚无 manifest。未访问或运行任何 test 数据或测试套件。

## 2026-07-05 — 加固陪审团 G-K 输入的失败关闭校验

- 静态审计发现 `jury_consensus` 原先依据 juror manifest 自报的 `fallbacks` 计算
  `zero_fallbacks`；虽然独立 `jury-annotate --verify` 能发现计数不一致，consensus
  入口本身未重新计数。损坏或误改的 manifest 因而存在让 G-K 错误放行的风险。
- consensus 现从逐条 annotation 重新识别 fallback，并要求它与 manifest 计数
  一致；同时强制校验 manifest 完整标志、期望/实际样本数、逐行 schema、juror
  身份、模型家族和 `publication_gold=false` / `human_annotator=false` 来源标志。
  独立 juror verifier 也增加同样的完整性与来源检查。
- 仅完成 AST 语法解析和 diff whitespace 检查，未运行任何测试套件，也未执行
  陪审团。此变更不放宽 G-K 阈值，只防止不完整或篡改来源进入 κ 与多数票计算。
  同期 Round 2 正常推进至 131/350，两个服务 active，日志无错误。

## 2026-07-05 — 禁止 G-S 失败时生成 `jury_gold`

- 静态审计发现 `jury-adjudication compile` 原先在 G-S 未通过时会排除 disputed
  样本，但仍生成带 `jury_gold: true` 的部分标签层。后续 paper readiness 虽会拒绝
  G-S 失败，制品语义本身仍违反“G-S 通过后才能 compile”的预注册规则。
- `compile` 现要求 G-K 与 G-S 均明确通过，否则直接失败且不创建标签目录；不再
  生成排除 disputed 样本的伪 jury-gold 层。它会重新计算四字段联合自一致率，并
  核对两轮冻结文件、协议指纹、来源 juror 身份/模型家族/annotation 指纹与 fallback
  计数，不能只信任报告中的布尔值。
- 14 天与 20% 分层重抽样也在 compile 时重新执行：验证 Round 2 创建时间晚于冻结
  门槛，逐类按固定 seed 重建期望样本和顺序，并要求 completed 文件完整覆盖该冻结
  packet。任何重复、缺失、替换或来源漂移均失败关闭。
- 仅执行 AST 语法解析、行长和 diff whitespace 检查，未运行测试套件或陪审团，
  未访问 test。同期 Round 2 正常推进至 136/350（`RAM0183`），服务 active、无错误。

## 2026-07-05 — 让陪审团与作者仲裁绑定同一真实盲包

- 盲态静态审计确认 juror manifest 原先只绑定 `packet_manifest.json`，未绑定实际被
  读取的 `adjudications.jsonl`。若后者在运行之间被替换，三个 juror 仍可能声称
  使用同一 packet；作者仲裁也没有强制与 juror 的实际输入逐文件一致。
- 新增共享盲包加载器：要求 annotation packet schema、样本数和 sample ID 完整，
  adjudication 模板不得已有 gold/adjudicator，顶层、claim 与 evidence 字段采用
  白名单，禁止 construction label、evidence role 或额外系统输出混入。juror manifest
  新增实际盲行文件 SHA-256；consensus 要求三者相同并把它传入报告，作者 Round 1/
  Round 2 必须与该哈希及 packet manifest 哈希一致。
- 作者 freeze 现在逐字段对照原 packet，仅允许 `author_annotation` 改变；compile
  重新验证 Round 1/2 packet、完成文件、consensus、juror 配置与指纹链。任何题目、
  证据、排序、隐藏字段或来源替换都会失败关闭。
- 三个 jury YAML 新增明确的 `llm.model_family`（DeepSeek / GLM / Meta）；annotate
  要求 CLI family 与配置完全一致并强制 temperature=0，不能把系统家族配置谎报成
  陪审团家族。consensus 报告同时冻结配置 SHA-256。
- 仅执行 AST/YAML 解析、模块导入、行长和 diff whitespace 检查，未运行测试套件、
  陪审团或任何 test 数据。同期 Round 2 正常推进至 146/350（`RAM0197`），GPU
  约 7.8 GiB / 94%，两个服务 active、日志无错误。

## 2026-07-05 — 修复 jury-gold 复评与三家族矩阵的输入门禁

- B4 静态审计发现合法 `no_conflict` jury annotation 通常没有建议修订文本，但
  `_overlay_benchmark` 原先要求每条标签都必须提供 revised answer，导致完整标签层
  仍无法复评。现将无冲突样本的参考答案明确设为原始 initial answer；冲突样本仍
  必须提供作者/陪审员修订文本。
- 完整 jury labels 现必须通过 G-K/G-S、覆盖完整 300 条 benchmark、无 excluded
  disputed 样本，且 manifest/逐行 `jury_gold=true`、`publication_gold=false`、
  `human_iaa=false` 与哈希均一致。`unanimous_only` 仅作为带来源指纹的显式子集视图，
  不再允许任意部分标签伪装为完整 jury gold。
- Qwen rescore 强制精确包含预注册 11 方法；Mistral/Google 强制精确包含 FAR、
  untyped、CRAG-style、CounterRefine-style 四方法。每个预测文件必须匹配原 suite
  的 run-manifest SHA-256、完整行数和模型 family；FAR 总是先评分，避免 untyped
  配对比较依赖尚未生成的 baseline scores。
- 三口径敏感性固定为 Qwen，并重新校验 consensus、labels 与原 construction report
  指纹。模型矩阵现在必须同时提供 Qwen/Mistral/Google 三个输入、绑定同一 jury
  labels manifest，重新计算 FAR sample-level 结构化回退率，并验证 untyped report
  与 rescored predictions 指纹后才应用 `> 0.30` 剔除规则。
- 仅执行 AST 解析、模块导入、行长和 diff whitespace 检查，未运行测试套件、模型
  或 test 数据。同期 Round 2 正常推进至 157/350（`RAM0213`），服务 active、无错误。

## 2026-07-05 — 将 dev 门禁接入 one-shot intent 与论文 readiness

- 最终路径审计发现 `falsirag-one-shot prepare` 原先只要求 clean worktree 和非空
  method 列表，不核验 G-A/G-K/G-S 或 dev 分析是否完成；因此即使停止规则仍生效，
  也能生成一个形式上有效的 test intent。
- prepare 现强制读取并冻结四组前置证据：通过的 350 条 RAMDocs dev G-A manifest、
  完整 300 条且 G-K/G-S 均通过的 jury labels、Qwen 三口径敏感性、包含三个系统
  家族的 dev 矩阵。任一协议指纹、样本数、标签来源、哈希或门禁不符即拒绝生成
  intent；FalsiRAG/RAMDocs test 输入条数必须分别为 58/150。
- committed intent 新增四份前置证据哈希；seal 重新核对 intent schema、commit 祖先、
  target、输入指纹、方法集、suite schema、gold 未载入状态、每方法完整预测数以及
  score 样本数。执行文档已补全新的必需参数示例。
- `falsirag-jury-paper-readiness` 不再只看自报布尔值：它会校验 consensus 行文件与
  300 条标签、G-K/G-S/非真人来源、Qwen 11 方法敏感性子 manifest、三家族矩阵行、
  共享 label hash，以及 FalsiRAG/RAMDocs 两套 test score 的目标 schema 和 seal
  交叉指纹。仍明确输出 `can_claim_human_iaa=false`。
- 仅执行 AST 解析、模块导入、行长和 diff whitespace 检查，未运行测试套件或访问
  test。同期 Round 2 正常推进至 167/350（`RAM0229`），服务 active、无错误。

## 2026-07-05 — 禁止 `--allow-test` 绕过已提交 intent

- 继续审计发现 prepare 虽已要求完整 dev 证据，但底层 `run_suite`、FAR、baseline
  与 RAMDocs runner 仍可仅凭 `--allow-test` 读取 test inputs，绕过 intent。停止规则
  因而仍主要依赖操作者自律，而非执行入口。
- 新增进程内 one-shot 授权上下文：FalsiRAG 与 RAMDocs 正式 test suite 必须同时
  提供 `--allow-test` 和已提交的 `--one-shot-intent`。suite 会在读取测试输入前验证
  target、58/150 条输入 SHA-256、数据 manifest、精确方法集、intent commit 与所有
  pretest evidence；授权只在该 suite 调用的动态作用域内有效。
- `load_run_inputs`、`select_samples` 与 RAMDocs initialize/run 现均要求该作用域。
  因此直接调用底层 FAR、baseline 或 RAMDocs runner 时，即使传 `--allow-test` 也会
  在 test 文件载入前失败。成功 suite manifest 会写入 intent ID、哈希与 commit，
  seal 必须再次逐项匹配。
- 执行文档已明确正式 test 只能走两个 suite 入口。仅完成 AST 解析、模块导入、行长
  和 diff whitespace 检查，未运行测试套件或访问 test。同期 Round 2 正常推进至
  171/350（`RAM0238`），GPU 约 7.8 GiB / 92%，服务 active、无错误。

## 2026-07-05 — 让 jury evidence release 可独立重算

- 静态审计发现旧 `build-jury` 只复制 consensus、最终 labels、敏感性与复评结果，
  未包含三位 juror 原始输出、作者 Round 1/2 仲裁或三个系统家族的源 suite；旧
  verifier 因而只能检查 bundle 文件哈希和几个自报 gate 布尔值，无法重算 G-K/G-S。
- `build-jury` 现强制接收完整 benchmark 路径，并复制三份独立 juror bundle、作者
  盲态仲裁目录、consensus、compiled labels、Qwen/Mistral/Google 三个源 dev suite、
  三个 jury-gold rescore、Qwen 敏感性和最终矩阵。bundle manifest 明确列出 juror
  IDs 与系统家族，仍固定 `publication_gold=false`、`human_iaa=false`。
- `verify-jury` 现在从包内源制品重新执行 consensus verifier，重新 compile G-S 后
  的 300 条 labels，重算三个家族的 dev 分数、Qwen 三口径敏感性与模型矩阵，并与
  跟踪结果逐 manifest/逐标签比较。任何来源缺失、仲裁漂移、模型预测漂移或报告
  自报值不一致都会失败关闭。
- 执行文档已补充完整 build/verify 命令。仅执行 AST 解析、模块导入、行长和 diff
  whitespace 检查，未运行测试套件、模型或 test 数据。同期 Round 2 正常推进至
  177/350（`RAM0250`），服务 active、无错误。

## 2026-07-05 — 对齐 README、论文与 2+4 状态账本

- 状态审计发现 `paper/STATUS.md` 仍声称只有 relaxed 与 strict 两个 profile，未列出
  已实现但尚未形成正式证据的 2+4 替代档位；traceability 也只记录 Round 1 G-A
  失败，遗漏正在运行的 dev-only Round 2。
- 论文状态页现明确区分三个档位：已就绪的单作者机器审计档位、尚在执行且不得称为
  真人 IAA 的 2+4 档位、以及没有被 2+4 取代的严格真人/外部档位。README 与协议
  矩阵同步记录 Round 2 至少 177/350、未 finalize、Phase B 仍关闭。
- traceability 同时写明 test 读取需已提交 intent 动态授权，以及 jury release 必须
  从 juror/作者仲裁/源 suite 重算。23:47 +08:00 再次复核时 checkpoint 已继续到
  181/350（`RAM0255`），两个服务 active、日志无错误。未访问或运行任何 test。

## 2026-07-05 — 补齐并诚实降级 Phase 0 三模型 smoke 状态

- 逐项核查 `PLAN_2PLUS4.md` 的 Phase 0 产物时确认：仓库和远端均不存在 Mistral、
  Gemma、Llama 三模型 smoke 记录；远端 Ollama 当前只有 `qwen3.5:9b`、`qwen2.5:7b`
  与 `glm4:9b`。此前把整个 Phase 0 概括为“证据完成”会掩盖这一缺口。
- 新增 `scripts/smoke_2plus4_models.sh`：只在 Windows RAMDocs 服务停止且 GPU 空闲时
  运行，缺失模型只有显式 `--pull` 才下载，并要求 D: 至少 20 GiB 可用。模型目录沿用
  `windows_gpu_env.sh` 的 D: 配置；短提示不读取 benchmark，每个家族输出协议指纹、
  对应配置 SHA-256、模型摘要和 `benchmark_data_accessed=false` 的 JSON 记录。
- 当前 Round 2 正在占用 GPU，因此没有执行或伪造 smoke；traceability 明确标记为
  “工具完成、证据待执行”。脚本通过 shell 语法与 diff whitespace 检查，未运行
  模型、测试套件或任何 test 数据。23:51 +08:00 只读复核时 Round 2 已继续到
  189/350（`RAM0269`），两个服务 active、日志无错误。

## 2026-07-06 — 修复 WSL 重启时的 systemd ordering cycle

- Windows/WSL 于 07:47 +08:00 重启。keep-running watchdog 在登录后把 Ollama 与
  Round 2 从同一 checkpoint 自动恢复，07:53 已继续写入 221/350，确认没有丢行；
  systemd unit 自身 `NRestarts=0`，不是应用崩溃。
- 启动 journal 同时报告 `default.target → far-ramdocs-round2 → far-ollama-2plus4 →
  default.target` ordering cycle。根因是 Ollama unit 同时 `WantedBy=default.target`
  又声明 `After=default.target`；systemd 会删除 Round 2 的初始启动 job，再依赖
  watchdog 补救。
- 已移除多余的 `After=default.target`，同步到远端用户 unit 并执行 daemon-reload。
  Ollama/Round 2 主 PID 在 reload 前后保持不变，未中断当前样本；`systemd-analyze
  --user verify` 无输出，checkpoint 随后推进至 224/350。未访问或运行任何 test。

## 2026-07-06 — 收紧 Ollama 启动稳定性门禁

- 回看持久化 run log 后确认，2026-07-05 23:56 +08:00 曾出现一次瞬时 Ollama
  不可用：Round 2 的单次 `/api/tags` 预检查刚通过，Ollama 随即拒绝模型身份请求，
  runner 失败退出；watchdog 于 23:57 先记录 GPU 等待，之后从同一 checkpoint 恢复。
  该故障未写入错误行或损坏已有预测，但说明单点健康探针存在竞态。
- Phase A 与 Round 2 units 现要求 `/api/tags` 连续三次成功（间隔 2 秒）才启动 runner；
  任一次失败都会重新开始稳定窗口。已同步两个远端 unit 并 daemon-reload，当前 Round 2
  PID `741` 在 reload 前后不变，`systemd-analyze --user verify` 无输出。
- 部署后 checkpoint 继续推进至 226/350，两个服务 active，近 10 分钟无错误。未访问
  或运行任何 test，也未改变实验方法、配置、checkpoint 或 G-A 判据。

## 2026-07-06 — 将第二轮失败分析纳入可验证证据链

- 补齐 `experiments.ramdocs_round2_error_analysis.verify_analysis`：它不信任报告自报
  数字，而是重新验证 Round 2、从冻结 score 文件重算四类配对结果和全部 discordant
  sample ID，并逐项核对 350 条覆盖、停止判定、来源 SHA-256 与非真人/非 test 声明。
- Round 2 evidence release 在 G-A 失败时现强制要求有效的 `round2/error_analysis`，
  manifest 必须写入 `paper_downgrade_required=true`；内嵌 verifier 会再次从 bundle
  的冻结 Round 1/2 制品重算，不能用同时改写报告和指纹的方式掩盖漂移。
- 仅完成 Python 字节码编译、diff whitespace 与静态内容检查，没有运行测试套件或
  访问任何 test。08:01 +08:00 只读复核时 checkpoint 为 231/350（`RAM0330`），
  两个服务 active、GPU 约 7.9/8.2 GiB，最近 journal 没有新增运行错误。

## 2026-07-06 — 将 2+4 路线纳入企划总账与完成验收

- `PROJECT_PROPOSAL.md` 原顶层执行状态仍只列出机器审计诊断、宽松论文和严格真人
  三条旧路径，未把已经预注册并实施的 2+4 替代路线列为独立证据档位；总完成审计
  也没有它的验收与停止规则，容易造成“工具存在但企划仍要求真人才能完成”的冲突。
- 企划总账现明确四档：诊断、宽松论文、2+4 单作者证据、严格真人证据。2+4 档位
  明确绑定 Round 2 G-A；通过才可进入 G-K/G-S/跨家族矩阵，失败则以可重算错误分析
  和论文降级完成预注册失败分支，不得绕过门禁。
- `docs/COMPLETION_AUDIT.md` 同步加入 2+4 的实现、实证与来源边界验收，且保留
  `publication_gold:false`、`human_iaa:false` 和非外部保管盲测红线。
- `docs/PROPOSAL_TRACEABILITY.md` 也补入同一独立档位，并把旧的“三档状态账本”
  更正为当前代码实际生成的四档；待办不再被笼统描述成仅有外部证据，也包括受预注册
  门禁约束的进行中实验。

## 2026-07-06 — 为 Phase 0 三模型 smoke 增加独立验真

- 完成度审计确认 `scripts/smoke_2plus4_models.sh` 能生成 Mistral/Gemma/Llama 三份
  记录，但此前没有独立 verifier；自报 `smoke_passed=true` 和配置哈希不足以形成
  可复核证据。
- 新增 `experiments.model_smoke_2plus4` 与 CLI `falsirag-verify-2plus4-smoke`，严格
  要求精确三文件集合，逐家族核对活动协议、当前配置 SHA-256、固定模型名、Ollama
  64 位 digest、带时区时间戳、`SMOKE_OK` 响应及非 benchmark/非真人来源声明。
- smoke 脚本现在生成后自动调用 verifier。当前 Round 2 仍占用 GPU，未拉取模型、
  未生成或伪造 smoke 证据；只完成 Python 语法/导入、shell 语法和 whitespace 静态检查。
- 安装包 smoke 的必需 console-script 集合同步加入该 verifier，防止源码入口存在但构建
  后 wheel 漏装命令。按本轮限制未执行 package smoke 或其他测试。

## 2026-07-06 — 补全 Phase B 作者盲态仲裁 SOP

- 执行手册此前只展示 `build-round1`，省略三份 juror 的独立 verify、consensus
  verify、两轮 freeze、14 天后 build-round2 以及最终 compile 的完整命令；工具虽然
  已实现，操作者仍无法仅按文档完成 G-K/G-S 证据链。
- 手册现补齐逐步可执行命令，并明确两轮 `author_annotation` 必须由作者本人在盲态
  下填写；Codex、其他 LLM 或自动脚本代填只能算新增机器 juror，不能冒充作者仲裁。
  最终标签继续固定 `publication_gold:false`、`human_iaa:false`。
- 本次只审计 CLI 与补文档；G-A 尚未通过，没有启动 jury、读取 test 或生成任何
  作者仲裁制品。

## 2026-07-06 — 把 G-A 停止规则下沉到 juror 执行入口

- 静态审计发现 jury readiness 和 one-shot 会检查 G-A，但 `falsirag-jury-annotate`
  本身只靠执行手册禁止提前运行；操作者仍可能在 Round 2 未通过时花费 API/GPU 生成
  Phase B 标注，违背预注册停止规则。
- 新增 `experiments.phase_b_gate.require_phase_b_authorized`，从 RAMDocs 数据、Round 1、
  Round 2 和冻结配置重新执行正式 verifier，并要求 G-A/Phase B 授权为真、停止规则
  为假、dev-only 与非真人来源声明完整。juror 在模型初始化和写文件之前必须通过它。
- 三份 juror manifest 现绑定同一个 Round 2 manifest、Round 1 suite 与配置 SHA-256；
  juror verifier 会重新验证并逐字段比较，consensus 拒绝缺失、不同或无效的 G-A 绑定。
  当前 G-A 未通过，因此新入口按设计无法运行；未启动 jury 或访问 test。
- consensus CLI 也强制接收同一组 RAMDocs 路径并重新执行 G-A verifier；构建与 verify
  都要求三份 juror 的 gate 对象与实时重算结果完全相同。作者仲裁入口继续检查 consensus
  中的 350 条 G-A/Phase B 授权，形成执行入口、聚合、仲裁三层停止规则。
- `scripts/run_2plus4_model_family.sh` 同步在模型 suite 启动前调用同一 G-A gate，默认
  指向冻结的 `diagnostics/ramdocs_v2` release，并提供四个显式路径环境变量。因而失败
  分支也不能误跑 Mistral/Gemma 矩阵；Phase 0 的非 benchmark smoke 不受此门影响。
- 编译后的 jury labels 现继承完整 `phase_b_gate`；复评、jury release、paper readiness
  与 one-shot intent 都要求它和 consensus 一致，其中 readiness 重新执行 Round 2
  verifier，intent 至少逐 SHA 绑定实际 RAMDocs gate manifest。这样 RAMDocs 外部证据
  与 jury/matrix/test 不再是两组仅靠布尔值并列的制品。

## 2026-07-06 — 为第二轮失败增加论文降级门

- 失败分支已有可重算错误分析和 `paper_downgrade_required`，但此前没有工具验证论文
  真的从 2+4 正结果降级为适用边界分析；只冻结 JSON 仍可能留下过强摘要或状态页。
- 新增 `falsirag-round2-failure-readiness`：重算完整 Round 2 release，要求两轮停止、
  applicability-boundary、Phase B/held-out 未运行、upstream labels 和非真人 IAA 披露，
  并拒绝 RAMDocs 优势、jury 确认或外部盲测等失败后禁用主张。
- 当前 Round 2 尚未完成，因此只实现门禁和运行手册，没有提前改写论文结果、生成
  readiness 报告、运行测试或访问 test。

## 2026-07-06 — 将 Phase 0 三模型 smoke 纳入两条终局门

- 完成度审计发现三模型 smoke 虽有生成与独立 verifier，但成功的 jury paper gate 和
  第二轮失败降级 gate 都未要求它，Phase 0 明列的必交制品仍可能被跳过。
- 两条 readiness 现共同调用 `verify_smoke_records`，要求同步到
  `diagnostics/model_smoke_2plus4` 的 Mistral/Gemma/Llama 精确三文件集合、模型 digest、
  当前配置和活动协议全部有效，并把三份记录 SHA-256 纳入最终 evidence 字段。
- 执行手册补齐 Windows D: → Mac 诊断目录的 rsync 与二次 verify。当前 GPU 仍由
  Round 2 占用，未拉取模型、运行 smoke、测试或访问 test。

## 2026-07-06 — Phase B 前登记 J2 本地 GLM 偏离

- 原注册矩阵写 J2 为智谱 API 的 GLM-4-Flash 或同级模型，但项目没有可用智谱凭据；
  实际冻结配置一直是远端 D: 已有的本地 Ollama `glm4:9b`。若不在执行前登记，配置与
  协议来源声明会不一致。
- 在 G-A 尚未通过、任何 juror 尚未运行时，将 J2 固定为本地 GLM4 9B。模型家族仍是
  GLM，与 Qwen/Mistral/Google 系统家族零重叠；prompt、temperature=0、结构化输出和
  独立标注协议均不变，成本降为 0。正式证据必须记录配置哈希与 Ollama digest。
- 本偏离不参考 jury 或 test 结果，也不把 J2 或三陪审员协议称为真人标注/IAA。

## 2026-07-06 — 固定 juror 精确身份与可续跑 provenance

- `jury_annotate` 过去只校验调用方自报 family 和 config 中的 family 相同，仍可把任意
  DeepSeek/GLM/Meta 模型塞入 J1/J2/J3；resume 也只看 juror ID/family，可能跨提交、
  配置或可变 Ollama tag 混合标注行。
- annotator 现强制精确映射 J1=`deepseek-chat`、J2=`glm4:9b`、J3=`llama3.1:8b`，
  并在首行写入前冻结 `run_identity.json`：干净 Git commit、实现哈希、配置、活动协议、
  prompt、盲包、G-A 授权和运行时身份；J2/J3 还必须有 64 位 Ollama digest。
- resume 要求当前身份与原始 JSON 全等；juror verifier、consensus、作者 compile 和最终
  evidence release 均绑定 run identity SHA 与 runtime identity。当前 Phase B 未启动，
  只完成静态语法/导入检查，未运行模型、测试或访问 test。

## 2026-07-06 — 保留 Phase A 历史协议指纹谱系

- J2 偏离使当前 `PLAN_2PLUS4.md` SHA 从 `e022…d00` 变为 `0a5e…ad9`。若只替换全局
  active 常量，已冻结 RAMDocs 导入、Round 1 8×350 suite 与正在运行的 Round 2 会被
  错误判成 stale，等同于用 Phase B 部署变化追溯性改写已完成 Phase A。
- 新增 `PROTOCOL_PHASE_A_SHA256=e022…d00`：RAMDocs 导入、dev suite 与 Round 2
  始终按该历史协议验证；偏离后的 juror、smoke、错误分析、release、readiness 和未来
  one-shot 使用新 `PROTOCOL_ACTIVE_SHA256=0a5e…ad9`。RAMDocs test 若获授权也使用
  当时 active 指纹，而不是沿用 dev 历史值。
- `verify_active_protocol` 已对当前文档新 SHA 通过；该谱系不改 G-A 数据、方法、阈值
  或运行中 checkpoint，也未访问或运行 test。

## 2026-07-06 — 加固 Ollama 启动期身份检查

- Round 2 远端 systemd 在 08:45 +08:00 观察到一次可恢复失败：`/api/tags` 预检查
  通过后，runner 绑定 `qwen3.5:9b` 运行时身份时仍遇到 `Connection refused`。随后
  `Restart=on-failure` 自动恢复，checkpoint 继续前进且未出现重复 sample。
- `experiments.runner._ollama_model_identity` 现对 Ollama `/api/tags` 做有界重试
  （默认 60 秒，2 秒间隔），但仍要求配置模型出现在 tags 中并暴露不可变 digest；
  因而只消除服务刚启动的 HTTP 竞态，不放松模型、digest 或正式 run identity 门禁。
- 该改动未触碰正在运行的远端 service、未切换工作树、未修改 checkpoint，也未运行测试
  或访问 test。

## 2026-07-06 — Round 2 完成并触发失败降级分支

- 09:30 +08:00 左右，Windows watchdog 在 Round 2 319/350 时停止
  `far-ramdocs-round2.service` 与 `far-ollama-2plus4.service`。诊断显示
  checkpoint 未损坏、0 duplicate；GPU 仅有 Xwayland 图形占用，但空闲判定因短暂
  utilization 残留写入 `ramdocs_dev_v2.waiting-for-gpu`。确认无其他计算进程后，
  删除 waiting marker 并用同一 user service 从原 checkpoint 安全恢复；恢复后
  checkpoint 从 319 推进到 321，重复数仍为 0。
- Round 2 FAR-only dev run 最终完成 350/350，`runs/far/run_manifest.json`
  为 `status=complete`、`partial=false`、`errors=0`、
  `gold_loaded_by_runner=false`，prediction SHA 为
  `b74a42264fd40e962ca883687fae63a2832ff50869fd4f02687f56771e357eb5`。
  完成后才将远端正式工作树从 `d8d5f40` 切到最新 `main` `88340ac`。
- 使用 `experiments.ramdocs_round2 finalize` 与 `verify` 重算 Round 2：
  FAR strict exact match 为 0.3086，冻结 Round 1 最强 `multi_query_rag`
  为 0.3114；配对差 -0.0029，95% CI [-0.0314, 0.0286]，McNemar p=1.0。
  `gate_a_passed=false`、`phase_b_authorized=false`、`stop_rule_triggered=true`。
- 已生成 `experiments.ramdocs_round2_error_analysis`：FAR-only 15、baseline-only
  16、共同正确 93、共同错误 226；报告设置
  `paper_downgrade_required=true`、`test_accessed=false`、`human_iaa=false`。
  `experiments.evidence_2plus4 build-ramdocs-round2` 与
  `verify-ramdocs-round2` 已在远端通过，并同步到本地 `diagnostics/ramdocs_v2`；
  本地 verifier 同样返回 `valid=true`。
- 按预注册停止规则，Phase B not run：DeepSeek/GLM/Meta jury、作者盲态仲裁、
  G-K/G-S、jury rescoring 与三系统家族矩阵均未运行。Held-out not run：
  FalsiRAG-Bench 与 RAMDocs test 均未访问。论文和状态文档已改写为
  typed-conflict-control applicability-boundary 分析，并明确 RAMDocs 是
  upstream labels，不是 human inter-annotator agreement 或 publication-grade
  human gold。

## 2026-07-06 — 完成 Phase 0 三模型 smoke 与失败分支终局验收

- 修正 Phase 0 Google 模型名称：原配置使用 Ollama 不存在的
  `gemma2:9b-instruct`，现统一为实际发布 tag `gemma2:9b`，并同步更新生成脚本、
  独立 verifier 与运行配置；没有借此改变模型家族、实验结果或 G-A 判据。
- Windows GPU 在 D: 盘完成 Mistral `mistral:7b-instruct`、Google `gemma2:9b`
  与 Meta `llama3.1:8b` 固定短提示 smoke。Llama 的 Ollama 并行拉取两次在同一
  分片附近停滞，第一次残留 blob 随后经 SHA-256 校验确认损坏；该损坏文件被删除，
  改用官方 Ollama registry 单连接下载同一 digest，下载后先由 `sha256sum -c`
  验证通过，再原子放入 D: Ollama blob 存储，最终 Ollama manifest 写入成功。
- 远端生成的三份记录已同步到 `diagnostics/model_smoke_2plus4`。远端脚本内 verifier
  与本地 `experiments.model_smoke_2plus4` 均返回 `valid:true`，精确三家族记录 SHA
  分别为 Mistral `156bcdd7…77b3`、Google `18696c41…502b`、Meta
  `4829dfae…c77b`；记录明确 `benchmark_data_accessed:false`、
  `publication_gold:false`、`human_iaa:false`。
- 重新运行 `experiments.ramdocs_round2_failure_readiness` 得到 `ready:true`、
  `gate_a_passed:false`、`phase_b_run:false`、`test_accessed:false`。因此 2+4
  企划按预注册失败分支完成闭合：保留第二次 G-A 失败与论文降级，不启动 LLM jury、
  作者仲裁、模型矩阵或任何 held-out/test。全程未运行测试套件，也未访问 test 数据；
  三模型 smoke 不是人类标注、真人仲裁或真人 IAA。

## 2026-07-06 — 注册长期路线并冻结 WS1 analysis-before-look 实现

- 将 `docs/PLAN_LONGTERM_OPTIMIZATION.md` 注册为 post-stop-rule 长期路线，活动
  SHA-256 为 `91eb3205fe127271bc5f4882025243d9974a711e311ef074fcbde09aa86e7cf7`；
  F1–F10、六工作流、决策树及后续 `deviation:` 纪律均由
  `experiments.protocol_longterm` fail-closed 校验。
- 在查看正式 226 条 both-incorrect 内容之前，冻结 WS1 六桶唯一优先级、两套 350 条
  分层、集合 F1 描述性口径、四个假设的三态阈值和 dev 五臂逐样本翻转定义；新增
  `experiments.attribution` 零模型构建器与 `experiments.evidence_attribution` 独立重算
  verifier，G-R1 要求唯一覆盖 226 条并报告全部四个预注册假设。
- analysis-before-look 由 Git 谱系强制执行：正式构建必须显式传入已推送且属于
  `origin/main` 的冻结提交，当前路线/实现/verifier/合成单测必须与该提交逐字节一致。
  发布物明确记录 `model_calls=0`、`publication_gold=false`、`human_iaa=false`、
  `test_accessed=false`、`reopens_gate_a=false`。
- 截至本条记录，尚未运行正式 WS1 构建、未读取正式 226 条内容、未调用任何模型、未
  访问或运行任何 test；验证只使用手写合成样本。正式数据只能在本冻结提交推送后读取。

## 2026-07-06 — WS1 首次运行的 RAMDocs 无正确文档偏离

- 冻结提交 `5f65ad7` 推送后首次运行正式 WS1。构建器在写出发布目录前 fail-closed：
  实现假定每题至少一篇 `document_type=correct` 文档，但 dev schema 聚合显示 350 题中
  348 题有 1–10 篇正确文档、2 题没有任何正确文档。这是上游数据事实，不是 test、模型
  输出或结果门禁；本次诊断未访问 RAMDocs test 或 FalsiRAG-Bench held-out。
- `deviation:` 修复只把空正确文档集合的 recall 明确定义为 0，使它按已注册“未命中任何
  正确文档”的最早失败规则进入 `retrieval_miss`；同时逐行记录
  `correct_document_available=false`，并在分层制品和报告公开 available=348 / unavailable=2。
  六桶集合及优先级、350 条 none/partial/complete 分层、四个假设阈值和 G-R1 均未改变。
- 首次失败未生成 `diagnostics/attribution_v1` 或报告半成品。修复必须通过合成回归检查并
  作为已推送的新冻结提交后，才允许第二次正式构建；仍为零模型调用、非真人 IAA、非
  publication gold，不重开 G-A。

## 2026-07-06 — WS1 G-R1 通过，四个机制假设均未获支持

- 偏离提交 `cded2b7` 推送后完成唯一正式构建；独立 verifier 从冻结输入重新计算六桶、
  两套分层、集合 F1、五臂翻转和四假设，返回 `valid=true`、`gate_r1_passed=true`、
  `model_calls=0`、`test_accessed=false`。证据包位于 `diagnostics/attribution_v1`，外部
  报告位于 `reports/mechanism_attribution.md`。
- 226 条共同错误按最早阶段唯一归类：retrieval miss 4、conflict undetected 72、
  conflict detected but revision wrong 103、answer-set incomplete 35、overfull 12、
  format/EM mismatch 0。正确文档完整检索子集有 179 条，但 FAR−baseline strict EM 为
  -0.0112，95% CI [-0.0503, 0.0279]，因此 H-upstream 不支持。
- RAMDocs 冲突检出率 0.449，dev 为 0.883，冲突分布 TV=0.446；但 RAMDocs 已检出子集
  FAR−baseline 仅 +0.0064，CI [-0.0446, 0.0573]，未满足注册的严格正效应条件，
  H-conflict-shape 不支持。描述性集合 F1 差 -0.0031，CI [-0.0200, 0.0133]，
  H-metric 不支持且不重开 G-A。
- dev 上 FAR 相对 untyped 有 34 条连续分数正增益，全部发生在 changed revision 路径，
  而非预注册预测的 detected-without-change 路径，因此 H-component 不支持。结合
  minus-typed-revision 的均值优势，这说明 revision 同时承载局部收益与更大的异质性伤害；
  后续论文不得继续写“效应位于 detection 而非 revision”，应改为“修订路径是收益与失效
  共同发生的核心中介”，并保留机器审计/dev/单模型限定。
- 本结果推翻的是路线图中的可证伪解释假设，不改写 F1–F10：RAMDocs 两轮 G-A 仍失败，
  Qwen dev 的 typed−untyped +0.078 仍保留，但简单的 upstream-only、metric masking 和
  detection-only 故事均被关闭。WS2/WS3 必须据此采用更窄、更机制化的边界表述。

## 2026-07-06 — 完成 WS5 功效回顾并制度化 G-P

- 新增 `experiments.power`：配对二元设计的解析 exact McNemar 功效/MDE、固定种子 Monte
  Carlo 复核、三家族分层 McNemar 功效、家族聚类 bootstrap 与 2/3 方向一致概率；所有
  参数和源制品 SHA 写入 `diagnostics/power_v1`，独立 verifier 可完整重算并逐字节比较。
- 历史回顾显示：Qwen 60 条 typed/untyped 的冻结二元不一致率为 19/60=0.317，+3pp 和
  +7.8pp 的 exact 功效分别仅 0.038 / 0.132；达到 60% / 80% 功效的 MDE 约为 17.1pp /
  20.6pp。RAMDocs 两轮在约 9% 不一致率下对 +3pp 的功效仅 0.388 / 0.399，证实旧 G-A
  对小效应缺乏检测力，但不改变其两次失败判定。
- WS2 预设计固定为 3 家族 × 60 配对、目标 +0.078、沿用 Qwen 不一致率；10,000 次模拟
  得到分层 McNemar 功效 0.414、家族聚类 bootstrap 正区间概率 0.595、至少 2/3 家族
  正方向概率 0.930。主功效低于 G-P 0.60，因此强制登记为
  `directional_reproduction`：G-F 不显著不能证明无效，方向不一致仍可收窄为
  Qwen-specific。
- `docs/EXPERIMENT_PLAN.md` 现要求今后所有正式预注册绑定 n、不一致率依据、目标效应、
  alpha、模拟次数与 seed；功效低于 0.60 时必须预先降格，禁止事后换指标/子集/家族或
  增加 Round 2。`falsirag-power verify` 返回 `valid=true`、`gate_p_completed=true`、
  `model_calls=0`、`test_accessed=false`；本工作未调用模型或读取任何 held-out/test。

## 2026-07-06 — 注册 WS2 三家族方向性复现

- 新增独立预注册 `docs/PLAN_FAMILY_DEV.md`，活动 SHA-256 为
  `5acc611bf8bb79740a996cc7bc9bd262bc55a661373f070670da19f7aa48433b`。
  固定 60 条 dev、typed/untyped 两臂、Mistral/Google/Meta 三家族、三个 Ollama digest、
  配置 SHA、answer correctness 唯一主指标、0.8 binary McNemar 阈值、家族 cluster
  bootstrap、机器标签敏感性与一次运行/无 Round 2 纪律。
- G-P 的 0.414 主功效已写入预注册，研究级别在看任何新预测前固定为
  `directional_reproduction`。G-F 仍按合并连续差 >0 且双侧分层 exact McNemar p<0.05
  计算，但不显著只能视为功效受限；少于 2/3 家族正方向或合并差非正才触发
  Qwen-specific 收窄。
- 新增与 Mistral/Gemma 同构的 `llama_open.yaml`；`protocol_family_dev` 绑定 dev/corpus、
  G-P manifest、smoke digest、三配置及干净已推送提交。专用 runner 只创建
  `bench/splits/dev.jsonl` 的 60 条 dev view，不读取 train、FalsiRAG test_inputs 或
  RAMDocs test；每家族先跑两臂各 5 条 calibration，再跑两臂各 60 条正式样本。
- `experiments.evidence_family_dev` 将从原始预测独立重算全部 score/report、合并 G-F、
  cluster CI、方向和标签分层，并核验 390 次 pipeline 样本执行、运行时 digest、配置、
  提交与全制品 SHA。单个 pipeline 样本可能触发多个本地 Ollama 请求，因此只记录样本
  执行数和 `api_cost_usd=0`，不伪称精确模型调用数。
- 截至本条记录，WS2 尚未运行 calibration 或任何正式样本，未启动 GPU 模型、未生成
  family-dev prediction，也未访问或评测 held-out/test；当前检查仅为合成测试、配置静态
  校验和 dev-only input view 回归。

## 2026-07-06 — WS2 在 D: 盘启动 Mistral calibration

- 将已推送的 `bd57585` 通过 Git bundle 部署到 Windows D: 的全新干净工作树
  `/mnt/d/FAR-workspace/FAR-longterm`；远端 GitHub fetch 曾卡住，安全终止后未改动冻结
  提交。dev-only view 在 `/mnt/d/FAR-outputs/family_dev_input_v1` 验证为 60 条、无
  train/test，dev 与 corpus SHA 均符合预注册。
- 旧 `far-ollama-2plus4` 会被已完成分支的 watchdog 正确停止，因此另建 transient
  `far-ollama-family-dev`，仍从 D: 的 Ollama 模型目录服务；三个 tag 的运行时 digest
  均与预注册一致。`far-family-dev` 按 Mistral → Google → Meta 顺序运行并可从各自
  checkpoint 恢复。
- 首次 transient 启动命令的 shell 循环变量被提前展开为空，argparse 在加载模型前退出，
  未写 prediction；随后改为三个显式 family 命令。当前 Mistral 两臂 5 条 calibration
  已开始，首个样本为 `F0182`，GPU 正常占用。该运维修正不改方法、配置、digest、样本、
  指标、G-F/G-P 或 claim level。
- transient family service 在 Mistral typed calibration 5/5、untyped 2/5 后被 systemd
  回收，日志无 Python/Ollama 错误，第三条尚未写 checkpoint。为避免短生命周期 transient
  unit 再次中断，新增两份不自动 enable 的持久 user-unit 模板，安装到远端后从同一
  `bd57585` checkpoint 恢复；typed 5 行与 untyped 2 行保持原样。该运维偏离发生在任何
  60 条正式 prediction 之前，不修改实验实现、配置、cache、校准样本或统计判定。

## 2026-07-06 — 完成 WS6-0/1/2/4 首轮仓库收敛

- 体积审计：`diagnostics/` 约 29 MiB，全仓 tracked 文件约 35 MiB，最大单文件约 2.1
  MiB，均远低于约 200 MiB 迁移阈值；当前不启用 Git LFS、不迁移 GitHub Release，避免
  无必要破坏已有 verifier 路径。
- 将历史 `output/pdf` 两份本地 PDF 移入已忽略的 `outputs/pdf`，删除空的 legacy
  `output/`，并在 `.gitignore` 明确忽略 `/output/`；今后临时运行统一使用 `outputs/`。
- 新增 `docs/CONTRIBUTING.md`，制度化“新正式实验先过 G-P、新论文制品必须有独立重算
  verifier + fail-closed 合成测试 + provenance + 复现命令”的约定。
- 新增 `scripts/check_markdown_links.py` 与合成测试，并接入 public-diagnostic CI；本地首次
  检查所有 tracked Markdown 交叉引用通过。维护结果写入
  `reports/repository_maintenance.md`，不改变任何研究事实或 held-out 状态。

## 2026-07-06 — WS4 主线改为 TMLR 机制与边界论文

- README 和 `paper/STATUS.md` 现在明确：AAAI-27 严格档保留工具但不再投入，只有未来
  真正获得两名独立真人标注者、独立仲裁和外部保管方才可重启；LLM jury 不替代这些角色。
- 论文摘要、结果、限制与结论加入已冻结 WS1 数字：226 条六桶、完整检索子集 null、集合
  F1 null、四假设均不支持，以及 34 个 typed 正增益全部位于 changed revision 路径。
  中心叙事从“效应位于 detection”改为“revision 同时中介局部收益和更大的异质性伤害”。
- 当前稿仍保留可编译的 AAAI 工作格式，待 WS2/WS3 结果落定后迁移正式 TMLR 模板；内容
  主张已先完成收窄。跨家族运行未完成前，论文仍明确不声称 multi-model generality。

## 2026-07-06 — 注册 WS3 外部边界测绘

- 新增独立预注册 `docs/PLAN_BOUNDARY_MAPPING.md`，活动 SHA-256 为
  `a8aa260aec7b92f2d51bc4c14ce78b0f355b2b61e543c5ace0cff52c5c1d34a3`。该研究从一开始
  固定为 `directional_boundary_mapping`，不设全局胜负门禁，不重开 RAMDocs G-A，不把
  外部上游标签称为 FAR 真人 IAA 或 publication-grade human gold。
- WS3 只纳入两个许可和划分可审计的公开 dev 诊断：WikiContradict 150 条
  （导入 manifest SHA `b3b3b80c44600579e15cfe4e9071040cfd99cc3d49ed716ee9dd603435a07765`）
  与 Google CONFLICTS 150 条（导入 manifest SHA
  `ec12941a2e98461219858d56a6a07545ba4d5ac70eca96dac2f6148b4ccb86e5`）。FaithEval 因官方
  只有 test split 排除；ClashEval/ConflictBank 因许可元数据不足或来源边界不清排除。
- 新增 `bench.build.boundary`、`experiments.protocol_boundary`、`experiments.boundary` 与
  `experiments.evidence_boundary`。运行器绑定 Qwen3.5 9B digest、配置 SHA、干净已推送
  source commit、两臂 `far`/`far_minus_typed_conflict`、每基准 5×2 calibration + 150×2
  formal，并强制 Wiki → Google、calibration → formal。`run-all` 入口用于远端 D: 输出。
- G-P 预先确认 n=150、Qwen dev 不一致率 19/60、目标 +0.078 的 exact McNemar 功效仅
  0.348（20,000 次 Monte Carlo 0.344），因此 null 不可解释为无效；任何正方向也只能支撑
  对应公开 dev 分布和固定 Qwen runtime 的边界描述。
- 本条记录前后仅完成 importer/protocol/runner/verifier 的静态检查和合成测试；尚未启动
  WS3 calibration 或正式 prediction，未访问 FalsiRAG held-out/test、RAMDocs test 或任何
  官方 test-only 外部数据。

## 2026-07-06 — WS2 Mistral formal FAR checkpoint 恢复

- 远端 `far-family-dev.service` 在 Mistral calibration 两臂完成、`runs/mistral/far` 写入
  5/60 checkpoint 后变为 inactive，未生成 `run_manifest.json` 或 family manifest；systemd
  显示 exit status 0，日志停在 `far: start F0037` 附近，无 Python traceback、OOM、Xid 或
  方法级错误。Ollama 曾记录短暂 `/api/tags` 连接/超时失败，但随后服务恢复。
- GPU 空闲且 `far-ollama-family-dev` active 后，从同一 D: 工作树、同一 `bd57585` 干净提交、
  同一服务定义和同一 checkpoint 重新 `systemctl --user start far-family-dev.service`。
  `CheckpointWriter` 跳过已有 calibration 和 formal 5 条，重新进入 `runs/mistral/far`
  的 `F0037`；未修改配置、digest、样本、方法、指标、G-F/G-P 或 claim level。
- 这是正式样本期间的运维恢复，不是实验偏离或 Round 2；若同类 inactive 状态重复出现，
  需优先诊断 Ollama/session 生命周期，再决定是否调整服务保活，且必须继续保持 D: 输出与
  checkpoint 原样恢复。

## 2026-07-06 — CI fixture 与 readiness 快照维护

- GitHub Actions 在收紧 2+4 证据门禁、Phase B 授权、one-shot test intent 与发布清单后，
  暴露出若干旧合成 fixture/快照仍按旧 schema 构造数据。维护范围限定为测试桩、reader-facing
  readiness JSON 与 release manifest 预期成员；未放松生产门禁，未把 LLM jury 表述为真人 IAA。
- 旧的 blind/test split 单元情景改为验证 fail-closed：没有已提交的一次性 test intent 时必须拒绝
  外部 blind return / test suite 路径。合成 jury 与 family-dev fixture 则补齐 run identity、source
  fingerprint、Phase B authorization、jury source/adjudication provenance 与 family 8-method 报告字段。
- 本次仓库维护不访问 FalsiRAG held-out/test、RAMDocs test 或外部官方 test-only 数据；远端 WS2 family
  dev 保持在 D: 工作树继续运行，Round2 RAMDocs dev 已按既有停止规则停在 G-A 未通过后的降级路径。

## 2026-07-06 — WS6 仓库维护审计命令化

- 新增 `falsirag-repository-maintenance`，把 WS6 的工程状态从静态说明升级为可重算审计：
  统计全仓跟踪体积、`diagnostics/` 体积、最大跟踪文件、`output/` 停用状态与 `outputs/`
  忽略策略，并生成 `reports/repository_maintenance.{json,md}`。
- 当前审计为 `valid:true`：`diagnostics/` 跟踪体积约 28.233 MiB，全仓跟踪体积约 37.637 MiB，
  最大跟踪文件为 `bench/external/ramdocs_v1/corpus.jsonl`（约 2.553 MiB），均低于长期路线图
  的迁移阈值；`output/` 无跟踪文件，`outputs/` 仅跟踪 `.gitkeep`。
- 该命令只检查仓库工程卫生，不读取 held-out/test，不调用模型，不改变 F1–F10、RAMDocs
  停止规则、Phase B 状态或任何实验门禁。
- 随后将该命令接入 public-diagnostic CI，并更新 workflow contract 与 traceability 文档；
  今后 `diagnostics/` 体积或 `output/`/`outputs/` 收敛规则漂移会在公开 CI 中 fail-closed。

## 2026-07-06 — WS2 family-dev 只读监控入口

- 新增 `scripts/watch_windows_family_dev.sh`，从 Mac 侧通过 `ssh windows-gpu` 打印 WS2
  `far-family-dev` / `far-ollama-family-dev` 状态、dev-only input manifest、三家族两臂
  calibration/formal checkpoint 行数、run manifest、日志尾、相关进程与 GPU 状态。
- 该脚本是只读巡检入口：不启动或停止 systemd unit，不写 marker，不 finalize，不读取
  held-out/test，也不改变正在 D: 工作树上运行的 `bd57585` 冻结 WS2 formal run。

## 2026-07-06 — WS2 Mistral formal FAR 20/60 checkpoint 恢复

- 新增只读监控脚本后巡检发现 `far-family-dev.service` 变为 inactive/dead，但
  `/mnt/d/FAR-outputs/family_dev_v1/runs/mistral/far/checkpoint.jsonl` 仅 20/60，且未生成
  `run_manifest.json`。日志停在 `far: start F0100`，无 Python traceback、OOM、Xid 或
  schema 错误；`far-ollama-family-dev` 仍 active，GPU 空闲。
- 按 WS2 恢复规则，从同一 D: 工作树、同一服务定义、同一 checkpoint 重新
  `systemctl --user start far-family-dev.service`。服务恢复为 active，Python runner 重新进入
  Mistral `run-family`；`CheckpointWriter` 将跳过已有 20 条正式 FAR 样本继续运行。
- 本次恢复不改变配置、digest、样本、方法、指标、G-F/G-P、claim level 或输出目录；它是
  正式 dev 运行的运维恢复，不是实验偏离、Round 2 或结果驱动调整。

## 2026-07-06 — WS2 Mistral formal FAR 38/60 checkpoint 恢复

- 只读监控在稍后巡检中再次发现 `far-family-dev.service` 与 `far-ollama-family-dev.service`
  均为 inactive/dead；Mistral formal FAR checkpoint 为 38/60，未生成 `run_manifest.json`。
  日志停在 `far: start F0193`，仍无 Python traceback、OOM、Xid 或 schema 错误。GPU 上仅见
  桌面/Xwayland 残留，不是其他训练任务占用。
- 按既定恢复规则，从同一 D: 工作树、同一服务定义、同一输出目录和同一 checkpoint 重新
  `systemctl --user start far-family-dev.service`。服务恢复为 active，`far-ollama-family-dev`
  同步 active，runner 重新进入 Mistral `run-family` 并将跳过已有 38 条正式 FAR 样本。
- 与 20/60 恢复相同，本次操作不改配置、digest、样本、方法、指标、G-F/G-P、claim level
  或输出目录。重复 inactive 模式暂按运维生命周期问题处理；正式运行期间不修改服务语义，
  以免引入注册后实现偏离。

## 2026-07-06 — WS2 Mistral formal FAR 用户暂停于 39/60

- 后续巡检确认 `far-family-dev.service` 再次 inactive/dead，而 `far-ollama-family-dev.service`
  active；Mistral formal FAR checkpoint 仍为 38/60，未生成 `run_manifest.json`。日志仍停在
  `F0193` 附近，无 Python traceback、OOM、Xid、磁盘满或 schema 错误；D: 盘约剩 67 GiB。
- 运维诊断发现安装的 user service 用分号串联 Mistral → Google → Meta 三个 `run-family`
  命令，因此子命令异常/早退可能不会让 systemd 报 `failed`。为暴露真实状态且避免继续
  误串后续 family，使用 transient user service `far-family-dev-mistral-resume` 仅恢复
  Mistral family：同一 D: 工作树、同一 `bd57585` 冻结提交、同一输出目录和同一 checkpoint，
  不修改实验代码、配置、digest、样本、方法、指标、G-F/G-P 或 claim level。
- transient resume 成功重新进入 `F0193`，并在用户要求“别训练了”前完成该样本，使
  `/mnt/d/FAR-outputs/family_dev_v1/runs/mistral/far/checkpoint.jsonl` 从 38/60 前进到
  39/60；随后按用户要求停止 `far-family-dev-mistral-resume.service`、
  `far-family-dev.service` 和 `far-ollama-family-dev.service`。最终只读复核显示三个服务均为
  inactive，未见 `family_dev`、Ollama 或 llama 推理进程，GPU 进程表仅剩桌面/Xwayland。
- 本次操作是用户暂停与运维恢复记录，不是评分、finalize、Phase B 启动、G-A/G-K/G-S 判定或
  结果驱动调整；未访问或运行任何 test。用户随后明确要求 2026-07-06 晚间不再训练，
  下一次 WS2 family-dev 恢复不得早于 2026-07-07，且恢复前仍需重新确认 GPU 与服务状态。
- 为避免后续心跳或手动恢复把用户暂停误判为异常，新增 `docs/CURRENT_OPERATIONAL_STATE.md`
  作为当前运行状态入口，并在 README 与复现手册的 WS2 小节中链接该文件。该文件只记录
  当前断点、暂停窗口和恢复前只读检查，不启动服务、不写远端 checkpoint、不改变实验协议。

## 2026-07-07 — WS2 Mistral formal FAR 从 39/60 恢复

- 用户要求的 2026-07-06 夜间暂停窗口结束后，先做只读核验：三个 WS2 服务均为
  `inactive`，没有残留 family-dev/Ollama/llama 推理进程；冻结 D: 工作树仍为干净提交
  `bd57585716b4c046db97311209a0d9f7ec340e6d`；Mistral FAR checkpoint 为 39 个唯一 ID，
  未生成 run manifest；D: 盘约剩 72 GiB；GPU 无 compute 任务，仅有桌面显存占用。
- 启动 `far-ollama-family-dev.service` 后，运行时 `mistral:7b-instruct` digest 精确匹配预注册值
  `6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf`。随后使用
  `far-family-dev-mistral-resume.service` 仅续跑 Mistral family，没有启动旧
  `far-family-dev.service` 的 Mistral → Google → Meta 分号串联命令。
- 10:03 CST 复核时 transient service 为 active、`NRestarts=0`，runner 已跳过 39 条已完成
  样本并进入 `far: start F0194`；checkpoint 尚保持 39/60，未完成样本不计入行数。
- 10:05 CST，`F0194` 在 115.04 秒后完成并写入 checkpoint；只读复核确认 40/60、40 个
  ID 唯一，service 仍为 active、`NRestarts=0`，随后进入 `F0204`。
- 本次运维恢复继续使用同一输入、输出、checkpoint、配置和冻结提交，不修改模型 digest、
  样本、方法、指标、G-F/G-P 或 claim level；未评分、未 finalize、未访问或运行任何 test。

## 2026-07-07 — WS4 论文机制—边界主张对齐

- 对照长期优化计划静态审计 `paper/` 后发现，正文已披露 RAMDocs 双失败和负消融，但独立
  `paper/abstract.txt` 仍停留在“等待真人双标注后再披露结果”的旧阶段，已与当前冻结证据
  和正文摘要不一致。现将其同步为同一窄主张：Qwen machine-audited dev 上 typed-vs-untyped
  为正，RAMDocs 两轮没有端到端优势，revision 同时中介局部收益与聚合准确率代价。
- 论文标题改为直接询问 typed conflict control 何时有效；引言贡献列表现明确包含
  applicability-boundary account，不再把完整 FAR 架构或每个查询/修订组件写成已获支持。
- 将 G-P 的 0.414 exact-McNemar 功效和 `directional_reproduction` 限定写入实验设计；这不会
  改写 G-F，也明确禁止未来把不显著结果解释为机制不存在。
- 推送后 GitHub CI 自动触发，fail-closed 地发现 `paper/main.tex` 的新 SHA 尚未传播到
  `reports/solo_paper_readiness.json` 与 `reports/project_status_snapshot.json`；失败只来自这两份
  派生报告过期。按证据依赖顺序先重生成 solo readiness，再重生成 project status，两个报告
  继续为 `ready:true` / diagnostic `complete:true`，并绑定新的 paper SHA
  `ad31e0631a0d26c9e1fed55bdba0e16f91882d83c4e8030bb4c1c514fe3d065f`。
- 本次仅修改论文与状态文本，未调用模型、未读取预测结果以调整门禁、未访问或运行任何
  held-out/test 数据，且不改 F1–F10、实验配置、样本、digest、指标或停止规则；本地没有运行
  测试套件，派生报告命令只重算已冻结 dev 证据和文本指纹。
