# Reproduction Guide

## Build the active TMLR manuscript

The active mechanism-and-boundary paper shares one scientific body with the
retained AAAI draft, but is built through the official anonymous TMLR shell:

```bash
bash scripts/build_tmlr_paper.sh
```

The builder fetches the official `JmlrOrg/tmlr-style-file` repository at the
pinned commit recorded in the script, verifies that commit, and writes the
generated source, style files, source lock, and PDF under
`paper/build/tmlr/`. Use `--prepare-only` on a machine without `latexmk`.
This command performs no model calls, experiments, scoring, or held-out/test
access. The generated lock binds both `paper/main.tex` and the active
content-only `paper/appendix.tex`. Do not edit the generated source; edit those
tracked sources and rebuild.

On a clean commit, build and fingerprint the complete accepted no-human paper
release with:

```bash
bash scripts/solo_paper_release_check.sh
```

This gate reruns the public evidence checks, tests, benchmark validation,
redacting secret scan, SBOM and package builds, then builds the TMLR PDF and
fails on layout overflow or unresolved references. Its nine-artifact
`solo-paper` checksum profile binds the wheel, sdist, SBOM, two audit reports,
both tracked readiness reports, the active TMLR PDF, and `SOURCE.lock`. It does
not read submission evidence or claim human review, adjudication, IAA, external
blindness, or publication gold.

The same command also creates
`build/solo-paper-release/far-solo-paper-release.tar.gz`, repacks it a second
time and requires byte identity, then verifies the archive without reading its
original worktree artifact paths. The paired standard-library-only
`verify_solo_paper_release.py` is itself embedded and fingerprinted; the final
audit runs it with `python3 -I`, without a FAR checkout or installation. The
sidecars `bundle-build.json` and `bundle-audit.json` record the archive and
verifier SHA-256 values plus the independent result. See
[`SOLO_PAPER_RELEASE.md`](SOLO_PAPER_RELEASE.md) for the exact layout, transfer
verification command, and claim boundaries.

For the role-by-role path from completed annotation through external blind
custody, trusted scoring, and final acceptance, use
`docs/EXTERNAL_ACTION_PACKET.md`.

## Environment contract

FAR declares Python 3.10+ support in `pyproject.toml`. The checked-in
`.python-version` pins the local development environment to Python 3.12, but
the static type/lint contract targets Python 3.10 so the artifact does not
silently drift beyond the proposal's compatibility claim. A fresh checkout
does not track the 42.0 MiB diagnostic tree; install the immutable v2 release
before running evidence-dependent tests or verifiers:

```bash
uv run falsirag ops diagnostic-data install
```

The installer verifies the archive SHA-256 and all 336 files before moving the
tree into the ignored `diagnostics/` directory. Then use:

```bash
uv run ruff check .
uv run mypy far tests scripts/package_smoke.py
uv run python -m pytest
```

before publishing or replacing paper numbers.

The same public-dependency contract runs in `.github/workflows/ci.yml` on
Python 3.10--3.13. CI installs the same verified release before tests. Its
diagnostic job additionally runs lint, type checking,
benchmark validation, the redacting secret scan, and
`scripts/solo_diagnostic_check.sh`. It needs neither API secrets nor a sibling
VeraRAG checkout; integration tests requiring that optional package are skipped
when it is absent.

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

For the lighter single-author diagnostic profile, which needs only tracked
public evidence and no human labels, cloud credentials, ignored local outputs,
or external custodian, run:

```bash
bash scripts/solo_diagnostic_check.sh
```

This verifies the solo evidence bundle, the frozen FEVER binary diagnostic, the
reader-facing report's numeric/source consistency, the generated JSON/Markdown
project-status ledger's freshness, and inclusion of the reports in the source
distribution. The ledger-only read-only check is
`uv run falsirag ops project-status --verify`.

For the user-authorized paper profile with no human annotators, run:

```bash
uv run falsirag release solo-paper-readiness
```

This validates the fingerprinted solo evidence and checks that the paper uses
only the supported typed-versus-untyped mechanism claim. It also requires the
post-hoc P11 revision-delta profile, the higher raw baseline/no-refutation
deltas, and the explicit warning that delta F1 is lexical rather than semantic
correctness. It fails if pending cells return or if the refutation, boundary,
typed-revision, FEVER, non-human, non-blind, or single-model limitations are
removed. A passing result certifies
only `single_author_machine_audited_paper`; it does not satisfy strict AAAI
readiness.

Generate and validate the declared-dependency CycloneDX 1.5 SBOM before a
release build:

```bash
uv run falsirag release sbom \
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
bash scripts/check_release_packages.sh
uv run falsirag release checksums \
  --profile base \
  --sbom build/sbom/far-sbom.cdx.json \
  --artifact paper_main_pdf=paper/build/release/main.pdf \
  --output build/release-checksums.json --check --json
```

The package smoke script installs the wheel and sdist separately with `uv` in
isolated environments and runs `scripts/package_smoke.py` with Python isolated
mode. It validates imports, console entry points, the packaged offline config,
the installed portable-paper-bundle verifier, and the full packaged benchmark
including its frozen 0.91 counter-evidence
recall, so a green source checkout cannot hide a broken distribution.

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
uv run falsirag release scan-secrets --json
```

The scanner recognizes high-confidence OpenAI/DeepSeek, Anthropic, GitHub, AWS,
private-key, and literal secret-assignment patterns, skips documented
placeholders, and prints only redacted findings. Use `--include-ignored` for a
local workstation audit that also covers ignored `.env` files.

## Build and validate data

```bash
uv run python -m far.bench.build.extend_from_verabench \
  --source-dir ../VeraRAG/data/verabench --output-dir bench
uv run falsirag bench validate --output outputs/benchmark_validation.json
uv run python -m far.bench.build.import_fever_slice
```

The build is deterministic. Any data change requires regenerated fingerprints.

## Human annotation

```bash
uv run python -m far.bench.build.annotate_packet build \
  --data-dir bench --output-dir outputs/annotations \
  --annotator annotator_a --annotator annotator_b
# Freeze both completed files, then complete adjudications.jsonl.
uv run python -m far.bench.build.annotate_packet compile \
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
  --config far/experiments/configs/deepseek.yaml \
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

Use `far/experiments/configs/{deepseek,qwen_plus,qwen_open}.yaml`. API configs name
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
CONFIG=far/experiments/configs/deepseek.yaml \
  bash scripts/start_windows_cloud_suite.sh
```

For Qwen Plus, export `DASHSCOPE_API_KEY` and set
`CONFIG=far/experiments/configs/qwen_plus.yaml`. The starter writes outputs under
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
  --config far/experiments/configs/formal_stack_smoke.yaml \
  --output-dir outputs/formal_stack_smoke \
  --limit 5
```

This diagnostic uses the formal retriever and conflict stack with LLM calls
disabled. It is a systems check, not a paper result.

On the Windows host, use the CUDA variant before a cloud-backed formal run:

```bash
falsirag-run \
  --config far/experiments/configs/formal_stack_cuda_smoke.yaml \
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
  --config far/experiments/configs/qwen_open.yaml \
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
  --config far/experiments/configs/deepseek.yaml \
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

P11 used this exact model-free path on the frozen Qwen suite:

```bash
uv run falsirag suite \
  --config far/experiments/configs/qwen_open.yaml \
  --data-dir bench \
  --output-dir outputs/remote_qwen_six_baseline_suite \
  --reports-only
```

The reports bind metric profile
`falsirag-evaluation-metrics-v2-revision-delta`. The public diagnostic verifier
rejects a missing profile or incomplete raw/action-conditioned delta metrics;
the command must retain `allow_test:false` and `reports_only:true`.

The WS2 refresh command below applies the same profile to the three already
frozen typed/untyped family pairs. Its raw combined difference is `+0.0398`
with 3/3 positive directions and family-cluster 95% interval
`[+0.0133,+0.0536]`; this is explicitly post-hoc sensitivity rather than the
registered G-F primary outcome.

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
  --config far/experiments/configs/deepseek.yaml \
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
  --config far/experiments/configs/deepseek.yaml \
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
uv run falsirag-run --config far/experiments/configs/deepseek.yaml \
  --output-dir outputs/runs/deepseek_far
uv run falsirag-baselines --config far/experiments/configs/deepseek.yaml \
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

## Frozen FEVER binary transfer diagnostic

The external FEVER slice supports binary scoring from inherited human-annotated
SUPPORTS/REFUTES labels, but its typed sampling buckets remain machine-generated
and non-gold. Reproduce the frozen detector-only comparison with the pinned
local NLI snapshot:

```bash
uv run falsirag-eval-fever-binary run \
  --data-dir bench/external/fever_pair_candidates_v1 \
  --output-dir diagnostics/fever_binary_v1 \
  --detector heuristic \
  --detector vera_nli \
  --config far/experiments/configs/fever_binary_nli.yaml \
  --resamples 2000 \
  --overwrite

uv run falsirag-eval-fever-binary verify \
  --data-dir bench/external/fever_pair_candidates_v1 \
  diagnostics/fever_binary_v1
```

Verification recomputes source transformations, every prediction row, metrics,
confidence intervals, paired bootstrap, McNemar, and file fingerprints. Do not
tune on this visible frozen slice and then report it as independent external
validation.

## Frozen WS1 mechanism attribution

WS1 is a deterministic, dev-only reanalysis of already frozen predictions. It
makes zero model calls, does not access either held-out test split, does not
produce human IAA or publication-grade gold, and cannot reopen RAMDocs G-A.
The analysis-before-look rule is enforced in two stages:

1. Commit and push the registered roadmap, classifier, evidence verifier, and
   synthetic unit tests without reading the 226 formal both-incorrect cases.
2. Pass that exact commit to the one-shot builder. The builder requires it to
   be an ancestor of `origin/main` and byte-compares all frozen analysis files
   against the commit before reading the dev inputs.

After the freeze commit has been pushed, build and independently verify the
release with:

```bash
uv run falsirag-attribution-evidence build \
  --analysis-freeze-commit <pushed-freeze-commit>

uv run falsirag-attribution-evidence verify
```

The build writes the exact six-file release to
`diagnostics/attribution_v1/` and the paper-facing copy to
`reports/mechanism_attribution.md`. The verifier independently recomputes all
failure buckets, retrieval/conflict strata, set-F1 diagnostics, dev component
flips, hypothesis dispositions, fingerprints, and G-R1. A nonempty or partial
release is rejected rather than overwritten; any post-freeze implementation
change must be registered and pushed as a `deviation:` commit before rebuilding.

## G-P power gate

Build and independently recompute the historical power review and the frozen
WS2 three-family design:

```bash
uv run falsirag-power build
uv run falsirag-power verify
```

For a proposed paired binary design, inspect a standalone scenario with:

```bash
uv run falsirag-power simulate \
  --n 180 --discordance-rate 0.316667 --effect 0.078
```

Every new preregistration must bind its design to a G-P result. Power below
0.60 does not silently authorize a confirmatory null claim: it forces the
study to be labelled directional/descriptive before any formal run.

## WS2 cross-family dev reproduction

WS2 is independently preregistered in `docs/PLAN_FAMILY_DEV.md`. It uses a
dev-only view and refuses dirty/unpushed source, mutable model identities, or a
config/digest that differs from the registration. Before resuming any
interrupted Windows GPU run, first read `docs/CURRENT_OPERATIONAL_STATE.md` and
honor any active user pause window.

From the Mac side, prepare the D:-backed Windows worktree before any WS2/WS3
starter. The target mode is mandatory because the two workstreams require
different source identities. `--family-dev` checks out the preregistered WS2
commit `bd57585716b4c046db97311209a0d9f7ec340e6d` in detached mode; `--latest`
fast-forwards main to the current local commit for WS3. The preparer is dry-run
by default and refuses active FAR GPU services or a dirty remote worktree. It
does not start training, delete checkpoints, or inspect held-out/test inputs.

For WS2, always use the frozen family-dev target:

```bash
scripts/prepare_windows_longterm_worktree.sh --family-dev
FAR_WINDOWS_PREP_ALLOWED=1 scripts/prepare_windows_longterm_worktree.sh \
  --family-dev --execute
```

Only after WS2 has completed and released the GPU, prepare latest main for WS3.
Boundary-unit installation is accepted only with `--latest`:

```bash
scripts/prepare_windows_longterm_worktree.sh --latest
FAR_WINDOWS_PREP_ALLOWED=1 scripts/prepare_windows_longterm_worktree.sh \
  --latest --execute --install-boundary-units
```

On the Windows GPU host, prepare the input
once and run families in the frozen order:

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate train
cd /mnt/d/FAR-workspace/FAR-longterm
source scripts/windows_gpu_env.sh

uv run falsirag-family-dev prepare-input \
  --output-dir /mnt/d/FAR-outputs/family_dev_input_v1

uv run falsirag-family-dev run-family --family mistral \
  --input-dir /mnt/d/FAR-outputs/family_dev_input_v1 \
  --output-dir /mnt/d/FAR-outputs/family_dev_v1
uv run falsirag-family-dev run-family --family google \
  --input-dir /mnt/d/FAR-outputs/family_dev_input_v1 \
  --output-dir /mnt/d/FAR-outputs/family_dev_v1
uv run falsirag-family-dev run-family --family meta \
  --input-dir /mnt/d/FAR-outputs/family_dev_input_v1 \
  --output-dir /mnt/d/FAR-outputs/family_dev_v1
```

Each family first runs the frozen five-sample calibration for both arms and
then the full 60 paired dev samples. After rsyncing the raw directory to
`diagnostics/family_dev_v1`, finalize once and independently verify:

```bash
uv run falsirag-family-dev finalize \
  --output-dir diagnostics/family_dev_v1
uv run falsirag-family-dev-evidence \
  --output-dir diagnostics/family_dev_v1
```

After an evaluator-only metric-profile upgrade, refresh the six derived WS2
reports from the frozen predictions without calling any model, then rerun the
independent verifier:

```bash
uv run falsirag-family-dev refresh-evaluations \
  --output-dir diagnostics/family_dev_v1
uv run falsirag-family-dev-evidence \
  --output-dir diagnostics/family_dev_v1
```

G-P fixes this study at `directional_reproduction`: a nonsignificant G-F does
not establish absence. No command above reads train, FalsiRAG held-out/test, or
RAMDocs test.

During a remote run, monitor progress from the Mac side with the read-only
watcher:

```bash
scripts/watch_windows_family_dev.sh
```

To pause or stop WS2 family-dev runners from the Mac side, first use the
guarded stopper in dry-run mode. It prints current service/process state and
the exact `systemctl stop` commands without stopping anything:

```bash
scripts/stop_windows_family_dev.sh
```

Only when an active WS2 runner must actually be stopped, rerun with
`--execute`. Add `--stop-ollama` only if the D:-backed WS2 Ollama service should
also be stopped. The stopper does not delete checkpoints, inspect
held-out/test, or stop WS3 boundary units:

```bash
scripts/stop_windows_family_dev.sh --execute
scripts/stop_windows_family_dev.sh --execute --stop-ollama
```

Windows/WSL 长时运行应优先安装单家族模板 unit，避免三家族 shell 串联掩盖中间失败：

```bash
cp scripts/systemd/far-family-dev@.service ~/.config/systemd/user/
cp scripts/systemd/far-ollama-family-dev.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

Before starting the next family from the Mac side, use the guarded starter in
dry-run mode. It runs the read-only preflight and prints the remote systemd
actions without starting services:

```bash
scripts/start_windows_family_dev_next.sh google
```

Only when training is allowed, rerun with both `--execute` and the explicit
`FAR_FAMILY_DEV_TRAINING_ALLOWED=1` confirmation. Without that environment
variable, the guarded starter exits before any SSH action. The execute path
starts the D:-backed Ollama service, reruns preflight with
`FAR_FAMILY_DEV_REQUIRE_OLLAMA=1` to verify the frozen `gemma2:9b` digest, and
only then starts `far-family-dev@google.service`:

```bash
FAR_FAMILY_DEV_TRAINING_ALLOWED=1 scripts/start_windows_family_dev_next.sh google --execute
```

Mistral 的 `family_manifests/mistral.json` 完整生成后才可执行 Google；Google 完整后才可
执行 Meta：

```bash
scripts/start_windows_family_dev_next.sh meta
FAR_FAMILY_DEV_TRAINING_ALLOWED=1 scripts/start_windows_family_dev_next.sh meta --execute
```

The runner and preflight both independently verify predecessor manifests, so an
incorrect family order fails closed. During any formal run, do not switch the
worktree, config, digest, input view, or output directory.

The watcher only prints service state, checkpoint counts, manifests, recent
logs, active processes, and GPU status from `windows-gpu`. It does not start or
stop services, write marker files, inspect held-out/test inputs, or finalize a
release.

## WS3 external boundary mapping

WS3 is independently preregistered in `docs/PLAN_BOUNDARY_MAPPING.md` and is
fixed at `directional_boundary_mapping`. The two public dev imports are frozen
under `bench/external/wikicontradict_v1` and
`bench/external/rag_conflicts_v1`; they are not FAR human IAA, publication gold,
or held-out/test evidence.

Windows/WSL 长时运行可安装 D: 盘持久化 units；只能在 WS2 已释放 GPU、Qwen digest
复核通过且正式工作树干净并位于当前 `origin/main` 时启动。WS2 运行期间工作树故意
detached 在冻结 family-dev commit，不能就地切换。WS2 完成并停止服务后，先使用上文
preparer 的显式 `--latest` dry-run/authorized fast-forward 流程，再安装 units。启动前再
dry-run guarded starter；它只做只读 preflight，不启动服务：

```bash
scripts/start_windows_boundary.sh
```

如果 dry-run 通过，并且处于允许训练窗口，才显式授权启动：

```bash
FAR_BOUNDARY_TRAINING_ALLOWED=1 scripts/start_windows_boundary.sh --execute
```

The starter runs offline preflight, starts the D:-backed WS3 Ollama unit, reruns
preflight with `FAR_BOUNDARY_REQUIRE_OLLAMA=1` to verify the frozen Qwen digest,
and only then starts `far-boundary.service`. It refuses dirty/stale worktrees,
missing public dev imports, active WS2 family-dev jobs, finalized boundary
releases, missing systemd units, or Qwen digest drift.

The underlying units can be installed with:

```bash
cp scripts/systemd/far-ollama-boundary.service ~/.config/systemd/user/
cp scripts/systemd/far-boundary.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

`far-boundary.service` 仅调用注册的 `run-all` 入口，输出固定为
`/mnt/d/FAR-outputs/boundary_v1`；runner 自身强制 Wiki→Google、calibration→formal、
两臂和 checkpoint 身份。不得与 family-dev 或其他 GPU 作业并行启动。

Stopping WS3 boundary services is also guarded and dry-run by default:

```bash
scripts/stop_windows_boundary.sh
scripts/stop_windows_boundary.sh --execute
scripts/stop_windows_boundary.sh --execute --stop-ollama
```

The stopper only targets `far-boundary.service` unless `--stop-ollama` is
passed. It deliberately does not stop WS2 family-dev units, does not delete
checkpoints, and does not inspect held-out/test inputs.

To rebuild an import from the pinned public source and verify byte-for-byte
equivalence:

```bash
uv run falsirag-build-boundary verify \
  --kind wiki \
  --output-dir bench/external/wikicontradict_v1
uv run falsirag-build-boundary verify \
  --kind conflicts \
  --output-dir bench/external/rag_conflicts_v1
```

The formal runner refuses unregistered protocol fingerprints, dirty/unpushed
source, model digest drift, skipped calibration, or starting Google CONFLICTS
before WikiContradict completes. On the Windows GPU host, use D:-backed outputs:

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate train
cd /mnt/d/FAR-workspace/FAR-longterm
source scripts/windows_gpu_env.sh

uv run falsirag-boundary run-all \
  --output-dir /mnt/d/FAR-outputs/boundary_v1
```

After rsyncing `/mnt/d/FAR-outputs/boundary_v1` to
`diagnostics/boundary_v1`, finalize once and independently verify:

```bash
uv run falsirag-boundary finalize \
  --output-dir diagnostics/boundary_v1 \
  --report reports/boundary_matrix.md
uv run falsirag-boundary-evidence \
  --output-dir diagnostics/boundary_v1 \
  --report reports/boundary_matrix.md
```

G-B is only a completeness/recomputability gate. It deliberately has no global
pass/fail result: the output is a boundary matrix across Wiki explicit/implicit
and Google outdated/misinformation/no-conflict strata. Power is below 0.60, so
nulls cannot be interpreted as evidence of absence and positives remain scoped
to the public dev distribution and the fixed Qwen runtime.

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
