# Reproduction Guide

For the role-by-role path from completed annotation through external blind
custody, trusted scoring, and final acceptance, use
`docs/EXTERNAL_ACTION_PACKET.md`.

## Environment contract

FAR declares Python 3.10+ support in `pyproject.toml`. The checked-in
`.python-version` pins the local development environment to Python 3.12, but
the static type/lint contract targets Python 3.10 so the artifact does not
silently drift beyond the proposal's compatibility claim. Use:

```bash
uv run ruff check .
uv run mypy far bench baselines eval experiments tests
uv run python -m pytest
```

before publishing or replacing paper numbers.

On the final submission commit, run the single fail-closed release gate:

```bash
FAR_SUBMISSION_EVIDENCE=submission/evidence.json bash scripts/release_check.sh
```

It executes formatting/lint/type/tests, benchmark validation, the redacting
secret scan, SBOM generation, wheel/sdist build, PDF compilation for the paper,
supplement, and reproducibility checklist, and release checksums for the package
plus generated audit/PDF artifacts and the exact submission-evidence snapshot.
It then runs the full submission-readiness audit against that newly generated
manifest. It first requires a clean Git worktree, and the checksum manifest
records the exact commit. Omitting `FAR_SUBMISSION_EVIDENCE` deliberately uses
the template in incomplete diagnostic mode; that mode cannot claim submission
readiness. Human annotation, external blind custody, author metadata, and policy
review remain separate governance inputs and are not falsely automated by this
script.

Generate and validate the declared-dependency CycloneDX 1.5 SBOM before a
release build:

```bash
uv run falsirag-generate-sbom \
  --output build/sbom/far-sbom.cdx.json --check --json
```

The generator is adapted from VeraRAG's MIT-licensed release tooling. It binds
the project name/version and every required or optional dependency group from
`pyproject.toml`; validation rejects stale, missing, duplicated, or malformed
components.

After building the wheel and source distribution, fingerprint the complete
release set:

```bash
uv build
uv run falsirag-release-checksums \
  --sbom build/sbom/far-sbom.cdx.json \
  --artifact paper_main_pdf=paper/build/release/main.pdf \
  --output build/release-checksums.json --check --json
```

The checksum manifest always requires the source distribution, wheel, and
CycloneDX SBOM roles, and accepts additional `--artifact ROLE=PATH` entries for
paper PDFs, benchmark validation reports, secret-scan reports, submission
evidence snapshots, or other final release deliverables. It validates every
recorded path, byte size, and SHA-256 hash. The standalone validator retains
that three-role minimum for intermediate package checks; the final submission
readiness gate is stricter and requires all nine artifacts emitted by
`scripts/release_check.sh`: those three package artifacts, both audit reports,
the evidence snapshot, both paper PDFs, and the reproducibility-checklist PDF.
The readiness report is generated only after that manifest and is not hashed
back into its own dependency graph; this avoids a circular, unsatisfiable
checksum. The release gate also verifies that the fingerprinted evidence file
is byte-for-byte the evidence object being audited.

Scan tracked and unignored text files before every commit or release:

```bash
uv run falsirag-scan-secrets --json
```

The scanner recognizes high-confidence OpenAI/DeepSeek, Anthropic, GitHub, AWS,
private-key, and literal secret-assignment patterns, skips documented
placeholders, and prints only redacted findings. Use `--include-ignored` for a
local workstation audit that also covers ignored `.env` files.

## Build and validate data

```bash
uv run python -m bench.build.extend_from_verabench \
  --source-dir ../VeraRAG/data/verabench --output-dir bench
uv run falsirag-validate-bench --output outputs/benchmark_validation.json
uv run python -m bench.build.import_fever_slice
```

The build is deterministic. Any data change requires regenerated fingerprints.

## Human annotation

```bash
uv run python -m bench.build.annotate_packet build \
  --data-dir bench --output-dir outputs/annotations \
  --annotator annotator_a --annotator annotator_b
# Freeze both completed files, then complete adjudications.jsonl.
uv run python -m bench.build.annotate_packet compile \
  --data-dir bench --packet-dir outputs/annotations \
  --output-dir outputs/adjudicated_bench
```

The compiler rejects missing labels, mismatched fingerprints, and incomplete
adjudication. It reports three Cohen's kappa values without inventing them.

## Automatic preannotation

When humans are not yet available, generate non-gold LLM suggestions from a
blind packet:

```bash
export DEEPSEEK_API_KEY="<paste key here>"
uv run falsirag-auto-annotate generate \
  --packet-dir outputs/annotations \
  --output-dir outputs/deepseek_preannotations \
  --config experiments/configs/deepseek.yaml \
  --preannotator-id deepseek_chat_v1
```

The output is review aid only. It deliberately cannot satisfy the independent
annotation, adjudication, or Cohen's kappa publication gates. See
[`docs/AUTO_ANNOTATION.md`](AUTO_ANNOTATION.md).

To create an editable human review draft from preannotations:

```bash
uv run falsirag-auto-annotate draft \
  --packet-dir outputs/annotations \
  --preannotation-dir outputs/deepseek_preannotations \
  --output-dir outputs/deepseek_review_draft \
  --reviewer-id annotator_a
```

The compiler rejects unreviewed machine drafts until `human_reviewed` is set to
`true` by a human reviewer.

## Runs and resume

Use `experiments/configs/{deepseek,qwen_plus,qwen_open}.yaml`. API configs name
the required environment variable. Re-run the identical command to resume;
changing code, data, config, split, or limit requires a new output directory.
The held-out test requires `--allow-test`.

Before spending cloud API budget, run the non-secret readiness preflight:

```bash
bash scripts/check_cloud_run_readiness.sh
```

This verifies that the DeepSeek and Qwen Plus configs still point to the pinned
provider/model names, require dense/NLI local snapshots, keep caches under the
ignored `outputs/` tree, and use environment variables for keys. It does not
print or persist secret values. By default it also rejects tracked worktree
changes, because a formal run should bind to a committed source revision; use
`--allow-dirty` only for local diagnostics. When rotated credentials are ready,
require the environment variables explicitly:

```bash
export DEEPSEEK_API_KEY="<rotated key>"
export DASHSCOPE_API_KEY="<rotated key>"
bash scripts/check_cloud_run_readiness.sh --require-keys
```

On the Windows GPU host, keep result bundles on D::

```bash
bash scripts/check_cloud_run_readiness.sh \
  --output-root /mnt/d/FAR-outputs/cloud_suites \
  --require-keys
```

After the preflight passes and no local-Qwen suite is active, start a
cloud-backed suite in tmux without exposing the key in the visible command
string. The starter removes the temporary tmux-global key immediately after
the new session inherits it, so unrelated future sessions cannot inherit the
credential:

```bash
ssh windows-gpu
source ~/miniconda3/etc/profile.d/conda.sh
conda activate train
cd /mnt/d/FAR-workspace/FAR
source scripts/windows_gpu_env.sh
export DEEPSEEK_API_KEY="<rotated key>"
CONFIG=experiments/configs/deepseek.yaml \
  bash scripts/start_windows_cloud_suite.sh
```

For Qwen Plus, export `DASHSCOPE_API_KEY` and set
`CONFIG=experiments/configs/qwen_plus.yaml`. The starter writes outputs under
`/mnt/d/FAR-outputs`, records the latest path in
`/mnt/d/FAR-outputs/latest_far_cloud_suite_path.txt`, and refuses to overlap
with an active `falsirag-suite` or Ollama `llama-server` unless
`ALLOW_CONCURRENT=1` is set intentionally. It also inherits the preflight's
clean-worktree requirement; if the remote tree is known to be a deliberate
rsync copy whose `.git` metadata is stale because `.git` was excluded, set
`ALLOW_DIRTY=1` only after recording the local commit used for the sync.

The DeepSeek config names `deepseek-v4-flash` explicitly. The provider's
[2026-04-24 change log](https://api-docs.deepseek.com/updates/) states that the
legacy `deepseek-chat` alias is retired on 2026-07-24, so it is not suitable for
a run that must remain reproducible through the AAAI-27 deadline.
The DashScope config likewise pins
[`qwen3.7-plus-2026-05-26`](https://help.aliyun.com/en/model-studio/text-generation-model/)
instead of the rolling `qwen-plus` alias.
The open model uses Ollama's official
[`qwen3.5:9b`](https://ollama.com/library/qwen3.5) tag. Record the local Ollama
model digest before freezing results. The runner queries `/api/tags`, includes
the digest in the run signature, and fails before inference if the configured
tag is missing or has no immutable digest. `qwen_open.yaml` also sets
`think: false`: the experiment needs parseable final answers, not hidden
reasoning text. The adapter fails closed if Ollama returns thinking without a
final response, preventing an incomplete chain of thought from being scored as
the model answer. On the 8 GiB WSL host it also sets
`unload_after_sample: true`. Ollama 0.30.11 otherwise retained a multi-gigabyte
cross-request prompt cache until Linux killed the model process. FAR keeps the
model resident for all calls within one sample, then explicitly unloads it to
clear that cache; this bounds host memory while avoiding a reload before every
claim/query/revision call.

The three formal API configs share BM25+BGE hybrid RRF and a pinned BGE
CrossEncoder reranker, so model comparisons do not confound the generator with
a different retriever.
They retain the top two reranked documents per typed query. On the frozen
development split, increasing this cutoff from two to five did not improve
counter-evidence recall (both were 0.95) and reduced mean evidence precision
from 0.169 to 0.056; the held-out test remains untouched.
The cloud-backed DeepSeek and Qwen Plus configs target CUDA for dense retrieval
and reranking. On the 8 GB Windows GPU, `qwen_open.yaml` keeps those components
on CPU so Ollama's 9B generator can retain the GPU without competing for VRAM.
This changes only execution placement: all formal configs retain identical
models, revisions, weights, cutoffs, and conflict settings.
`formal_stack_smoke.yaml` is the portable CPU systems check, while
`formal_stack_cuda_smoke.yaml` validates the same retrieval stack on CUDA with
LLM calls disabled.
Install the complete optional retrieval stack before a formal run:

```bash
uv sync --extra experiment
uv pip install --no-deps -e ../VeraRAG
```

They also share `cross-encoder/nli-distilroberta-base` for VeraRAG's conflict
graph with `require_nli: true`. Each model is pinned to an immutable Hugging
Face revision and resolved to a local snapshot before construction; the checked
configs therefore require those snapshots to be pre-cached. A formal run aborts if hybrid retrieval
loses dense search or if NLI cannot load; it must never silently relabel a
rule-only run as the configured method. Graph-originated and transparent FAR
fallback conflicts are distinguished in each trace by `metadata.detector`.

Before spending API budget, verify those exact pinned assets and the batched
VeraRAG graph offline:

```bash
uv run falsirag-run \
  --config experiments/configs/formal_stack_smoke.yaml \
  --output-dir outputs/formal_stack_smoke \
  --limit 5
```

This diagnostic uses the formal retriever and conflict stack with LLM calls
disabled. It is a systems check, not a paper result.

On the Windows host, use the CUDA variant before a cloud-backed formal run:

```bash
falsirag-run \
  --config experiments/configs/formal_stack_cuda_smoke.yaml \
  --output-dir /mnt/d/FAR-outputs/formal_stack_cuda_smoke \
  --limit 5
```

## Windows GPU / WSL storage-safe setup

The configured GPU host has limited C: space. Keep code, model caches, runtimes,
and outputs on D: rather than under the WSL home directory:

From the Mac, synchronize only the working tree. Anchor top-level build/output
exclusions with a leading slash: an unanchored `--exclude 'build'` would also
remove the required `bench/build` Python package.

```bash
rsync -az --delete \
  --exclude '/.git' --exclude '/.venv' --exclude '__pycache__' \
  --exclude '/.pytest_cache' --exclude '/.mypy_cache' --exclude '/.ruff_cache' \
  --exclude '/outputs' --exclude '/output' --exclude '/build' --exclude '/dist' \
  /Users/xuwenyao/FAR/ windows-gpu:/mnt/d/FAR-workspace/FAR/
```

Then enter the D:-backed checkout:

```bash
ssh windows-gpu
source ~/miniconda3/etc/profile.d/conda.sh
conda activate train
source /mnt/d/FAR-workspace/FAR/scripts/windows_gpu_env.sh
cd /mnt/d/FAR-workspace/FAR
```

The environment file sets Hugging Face caches to `/mnt/d/FAR-models/huggingface`,
Ollama weights to `/mnt/d/FAR-models/ollama`, the user-level Ollama runtime to
`/mnt/d/FAR-runtime/ollama`, optional Python packages to
`/mnt/d/FAR-runtime/python/site-packages`, and experiment outputs to
`/mnt/d/FAR-outputs`. Install a missing optional package without growing C: via:

```bash
python -m pip install --target "$FAR_PYTHON_SITE" <package>
```

Check those values before any large download:

```bash
env | grep -E '^(HF_HOME|HUGGINGFACE_HUB_CACHE|OLLAMA_MODELS|FAR_OUTPUT_ROOT)='
df -h /mnt/c /mnt/d
```

Start the model server in a detached tmux session:

```bash
tmux new -s far-ollama
source ~/miniconda3/etc/profile.d/conda.sh
conda activate train
source /mnt/d/FAR-workspace/FAR/scripts/windows_gpu_env.sh
ollama serve
# Ctrl+B, then D
```

Pull and run the fixed open model from a second session. The model digest is
captured automatically in FAR's run signature:

```bash
source /mnt/d/FAR-workspace/FAR/scripts/windows_gpu_env.sh
ollama pull qwen3.5:9b
CUDA_VISIBLE_DEVICES="" falsirag-run \
  --config experiments/configs/qwen_open.yaml \
  --data-dir bench \
  --output-dir /mnt/d/FAR-outputs/qwen_open_dev \
  --split dev
```

`CUDA_VISIBLE_DEVICES=""` applies only to the FAR client process. The already
running Ollama server remains on the GPU, while BGE and NLI remain on CPU and
cannot exhaust the 8 GB device alongside Qwen. Do not set it on `ollama serve`.

For the complete open-model suite on the configured Windows GPU host, prefer
the guarded starter. It starts Ollama from the D:-backed runtime if the API is
not already reachable, refuses to collide with an existing suite tmux session,
creates a timestamped output directory under `/mnt/d/FAR-outputs`, and records
that directory in `/mnt/d/FAR-outputs/latest_far_corrected_suite_path.txt`:

```bash
ssh windows-gpu
bash /mnt/d/FAR-workspace/FAR/scripts/start_windows_qwen_suite.sh
```

Override `SUITE_SESSION`, `SUITE_ROOT`, `CONFIG`, `DATA_DIR`, or `SPLIT` only
when intentionally starting a separate run. Check progress later with:

```bash
ssh windows-gpu 'bash /mnt/d/FAR-workspace/FAR/scripts/check_windows_qwen_suite.sh'
```

The status helper reports checkpoint counts, the age of the newest checkpoint,
run manifests, process/GPU/disk state, and an explicit warning when another
generation client is sharing the host. Override the default 30-minute stale
threshold for a shorter diagnostic window with, for example,
`STALE_SECONDS=300`; a stale warning means no new checkpoint was written in the
window, not by itself that the live process should be killed.

Once both corrected FAR and `minus_typed_conflict` are complete, collect and
score the core pair from the Mac with:

```bash
bash scripts/sync_qwen_core_comparison.sh
```

The collector reads the remote latest-path marker, requires both manifests to
be complete 60/60 with zero errors and `partial: false`, then rsyncs only those
two run bundles into ignored local outputs. It validates each bundle, evaluates
FAR, evaluates untyped FAR against the fingerprint-bound FAR score rows, and
writes the paired bootstrap/McNemar report. It exits before rsync if either run
is partial or missing. Override `REMOTE_HOST`, `REMOTE_LATEST_PATH_FILE`,
`LOCAL_ROOT`, `RESAMPLES`, or `SEED` only for an intentionally different
frozen comparison.

The artifact builder checks `FAR_UNICODE_FONT` first, then standard macOS,
WSL/Windows, and Linux Noto locations. It records the selected font path and
SHA-256 in `artifact_manifest.json`; on this host it can read the existing
Windows CJK font without copying another font onto C:.

Supported `retrieval.backend` values are `lexical` (offline diagnostics),
`vera_bm25`, `vera_dense`, `vera_faiss`, and `vera_hybrid`; any Vera backend can
enable the nested `rerank` block. Formal hybrid configs set
`allow_dense_fallback: false`: missing embeddings or dense dependencies abort
the run rather than silently producing mislabeled BM25 results. Set it to true
only for a diagnostic run and report the degradation.

Recommended: run one complete suite for a config. This executes FAR, selected
baselines, selected ablations, evaluation, result validation, and table/figure
artifact generation:

```bash
uv run falsirag-suite \
  --config experiments/configs/deepseek.yaml \
  --output-dir outputs/suites/deepseek_dev \
  --split dev \
  --baseline vanilla_rag \
  --baseline multi_query_rag \
  --ablation minus_typed_conflict \
  --ablation minus_refutation_query
```

Omit the repeated `--baseline` and `--ablation` flags to run all six baselines
and all four FAR ablations. Use `--limit` only for diagnostic smoke runs; suite
manifests and built artifacts then remain marked `diagnostic_only`.
Full-length runs are also forced to `diagnostic_only` while
`bench/manifest.json` has `publication_ready: false` or any scored row is not
`adjudicated`. Completing all 60 dev predictions therefore does not silently
promote machine-seeded labels into paper evidence.
Each `suite_manifest.json` stores a `suite_request` binding the config,
benchmark input, corpus, split, limit, test-access flag, baseline set, and
ablation set. Reusing the same `--output-dir` with a different request fails
before inference; choose a new directory for a different method matrix.

To rebuild reports after evaluation or publication gates change without
calling any model again, rerun the same suite command with `--reports-only`.
It requires every selected run to be complete and verifies method, split,
limit, config, benchmark, corpus, signature, and prediction fingerprints before
overwriting reports and artifacts.

If a standalone Qwen FAR dev run is already active on the Windows GPU, queue the
remaining matched suite without repeating those 60 FAR predictions:

```bash
tmux new -d -s far-qwen-suite \
  'bash /mnt/d/FAR-workspace/FAR/scripts/queue_qwen_dev_suite.sh \
  > /mnt/d/FAR-outputs/qwen_open_dev_suite.log 2>&1'
```

The queue waits for `far-qwen-dev`, requires its complete non-partial dev
manifest, links that immutable run into the suite, and then executes all four
ablations, all six baselines, evaluation, validation, and artifact generation.
Both the suite and its log stay on D:. Override `WAIT_FOR_SESSION`, `FAR_ROOT`,
`UPSTREAM_FAR_RUN`, or `SUITE_ROOT` only when intentionally using different
paths.

If a five-baseline Qwen suite was already frozen before the closest-neighbor
CounterRefine control was added, queue only that sixth baseline and the final
reports-only merge:

```bash
tmux new -d -s far-qwen-counterrefine \
  'bash /mnt/d/FAR-workspace/FAR/scripts/queue_qwen_counterrefine.sh \
  > /mnt/d/FAR-outputs/qwen_counterrefine_queue.log 2>&1'
```

The queue waits for `far-qwen-suite-v3` by default. It then requires complete
60/60 manifests for FAR, four ablations, and the original five baselines before
running `counterrefine_style_reproduction` under the same Qwen config. It
finally invokes the suite's fingerprint-checking `--reports-only` path, which
rebuilds evaluations and artifacts for all six baselines without another model
call for any existing run. Override `WAIT_FOR_SESSION`, `SUITE_ROOT`, or
`POLL_SECONDS` only when intentionally recovering a differently named suite.

If the remote workspace was temporarily rolled back to the legacy suite's
implementation fingerprint to resume old checkpoints, do not rsync current
`main` over it while the suite is still active. From the Mac, stage a clean
current archive and queue the safe post-suite finalizer instead:

```bash
bash scripts/queue_qwen_legacy_finalize.sh
```

The finalizer writes the current clean revision to D:, waits for
`far-qwen-suite-v3` to exit, verifies FAR + four ablations + the original five
baselines are all complete 60/60 and non-partial, then replaces the remote
workspace with the staged archive and runs `queue_qwen_counterrefine.sh`. This
preserves the legacy run signatures and still ends with the current six-baseline
reports-only merge.

## Externally held blind test

Do not run the ordinary scored suite against local test gold. Before the one
authorized final test, create, audit, and package a fresh gold-free handoff:

```bash
uv run falsirag-build-blind-bundle \
  --data-dir outputs/annotations/falsirag_adjudicated_v1 \
  --output-dir outputs/handoff/falsirag_blind_test

uv run falsirag-build-blind-bundle audit \
  --bundle-dir outputs/handoff/falsirag_blind_test

uv run falsirag-build-blind-bundle package \
  --bundle-dir outputs/handoff/falsirag_blind_test \
  --output-dir outputs/handoff/custodian_deepseek_handoff \
  --config experiments/configs/deepseek.yaml \
  --frozen-commit "$(git rev-parse HEAD)" \
  --overwrite
```

The command writes only a sanitized corpus, the five-field test inputs, and a
fingerprint manifest. It strips construction metadata and dependency IDs and
refuses a non-empty output directory, preventing stale gold files from being
left in the handoff. The audit/package step recursively rejects forbidden
gold/provenance keys, extra files, fingerprint mismatches, and accidental
`technical` dry-run handoffs. Transfer the resulting custodian ZIP, frozen code
commit/release, and environment lock to the external custodian. The custodian
runs predictions once, without receiving `falsirag_bench.jsonl`:

```bash
falsirag-suite \
  --config experiments/configs/deepseek.yaml \
  --data-dir /path/to/falsirag_blind_test \
  --output-dir /path/to/returned/deepseek_test \
  --split test --allow-test \
  --ablation full
```

In test mode the suite never evaluates or builds figures. It emits
`far-blind-suite-manifest-v1` with `unscored: true`, `gold_loaded: false`, the
input/corpus hashes, and prediction hashes. The trusted scorer then evaluates
the returned `predictions.jsonl` files against the frozen adjudicated benchmark
using `falsirag-eval`; run Vanilla first and pass its `scores.jsonl` as
`--baseline-scores` for paired reports. The external custodian and genuine
one-shot execution remain human governance gates even though the data path is
now technically separated.

For targeted debugging, run individual components:

```bash
uv run falsirag-run --config experiments/configs/deepseek.yaml \
  --output-dir outputs/runs/deepseek_far
uv run falsirag-baselines --config experiments/configs/deepseek.yaml \
  --output-dir outputs/runs/deepseek_baselines
```

Run every ablation with `--ablation minus_typed_conflict`,
`minus_refutation_query`, `minus_boundary_query`, and `minus_typed_revision`.

To rebuild only the paper-facing tables and figures from already validated
reports, install the `eval` extra and call the artifact builder directly:

```bash
uv sync --extra eval
uv run falsirag-build-artifacts \
  --report far=outputs/evaluations/far/report.json \
  --report vanilla=outputs/evaluations/vanilla_rag/report.json \
  --report minus_typed_conflict=outputs/evaluations/minus_typed_conflict/report.json \
  --prediction far=outputs/runs/far/predictions.jsonl \
  --output-dir outputs/artifacts \
  --overwrite
```

For final submission figures, use only reports produced by
`falsirag-score-blind-return` and require strict provenance:

```bash
uv run falsirag-build-artifacts \
  --report far=outputs/final/qwen_open_test_scored/evaluations/far/report.json \
  --report vanilla=outputs/final/qwen_open_test_scored/evaluations/vanilla/report.json \
  --report minus_typed_conflict=outputs/final/qwen_open_test_scored/evaluations/minus_typed_conflict/report.json \
  --prediction far=outputs/returned/qwen_open_test_suite/runs/far/predictions.jsonl \
  --output-dir outputs/final/qwen_open_test_scored/artifacts \
  --require-publication-ready \
  --require-test-only \
  --overwrite
```

The trusted scorer already uses these strict requirements. The generated
`artifact_manifest.json` records `publication_ready`, `test_only`, phases,
scored splits, and per-report publication summaries; the final submission gate
rejects artifacts that were not built in strict test-only mode.
Without `--overwrite`, the artifact builder refuses a non-empty output
directory. With `--overwrite`, it replaces only the known FAR-generated artifact
files and still rejects unexpected leftovers, which prevents stale tables or
figures from being silently carried into the manifest.

## Paper

```bash
cd paper
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

The repository vendors unmodified `aaai2027.sty` and `aaai2027.bst` from the
official Author Kit. Replace pending empirical tables only with validated,
complete reports. Before the final `falsirag-submission-readiness` run, record
the exact reviewed paper source hashes:

```bash
uv run falsirag-submission-readiness --print-paper-fingerprints
```

Copy that map into `human_review.paper_source_sha256` in the real ignored
submission evidence file. Any later paper edit invalidates the review and must
be rechecked by a human. The final readiness gate also requires the paper
reviewer to be independent from the annotators, adjudicator, external blind
custodian, and trusted scorer recorded elsewhere in the same evidence file. The
tracked `submission/evidence.template.json` is only for `--allow-incomplete`
status snapshots; final readiness rejects `*.template.json` evidence paths.
Source releases include only the two submission templates, not the ignored real
`submission/evidence.json` or `submission/blind_test_attestation.json` files.
paper draft deliberately contains no fabricated score or IAA value.
