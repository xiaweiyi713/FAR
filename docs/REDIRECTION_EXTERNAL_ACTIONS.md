# Redirection external-action ledger

This ledger records the external actions for
[`PLAN_REDIRECTION.md`](PLAN_REDIRECTION.md), including completed mutations and
the optional inactive human-only branch. External steps mutate GitHub, the remote GPU
host, or human evidence and therefore must not be inferred from an ordinary
build/test request.

## Invariants

- Do not install, download, or run Ollama/model weights on the developer Mac.
- `windows-gpu` is the only model-execution host for P5, P6, and P6-M.
- P5, P6, and P6-M are sequential; never run their model services concurrently.
- Every remote starter is default-deny and checks a clean exact commit, idle
  GPU, immutable model digest, frozen inputs, and dedicated output root.
- P5/P6/P6-M use development evidence only. They never authorize held-out/test use.
- P6 remains retrospective and cannot confirm H4 even after human completion.
- `artifacts-v1` is immutable. Future accepted P6 human results must be
  preserved in a new versioned archive and independently read back before the
  packaged manifest is switched.

## 1. Publish the reviewed source commit (complete)

The reviewed source and subsequent P10-B/CI repairs are on `origin/main`.
Future source pushes still require explicit GitHub push authorization:

```bash
git status --short
git push origin main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
```

Do not prepare the remote host if local `HEAD` and `origin/main` differ.

## 2. P5 registered remote ablations (complete)

The three registered 350-row runs completed, were returned, and passed the
independent verifier. The commands below remain the historical runbook;
re-running them would require new authorization:

```bash
scripts/prepare_windows_p5_ablations.sh
FAR_P5_PREP_ALLOWED=1 scripts/prepare_windows_p5_ablations.sh --execute

scripts/start_windows_p5_ablations.sh
FAR_P5_TRAINING_ALLOWED=1 scripts/start_windows_p5_ablations.sh --execute
scripts/check_windows_p5_ablations.sh
```

After all three 350-row manifests complete, stop the dedicated services and
return the bundle:

```bash
scripts/stop_windows_p5_ablations.sh --execute --stop-ollama
FAR_P5_FETCH_ALLOWED=1 scripts/fetch_windows_p5_ablations.sh --execute
```

The fetch command ends with the independent zero-model verifier. H3/H5 remain
unset until it returns `valid:true` from the complete remote bundle.

## 3. P6 machine prelabels (complete)

The authorized run completed 217 rows in 221 attempts, returned the native
provenance bundle, and stopped its dedicated model service. The commands below
are retained as the historical runbook and are not authorization to rerun it:

```bash
scripts/prepare_windows_p6_prelabels.sh
FAR_P6_PREP_ALLOWED=1 scripts/prepare_windows_p6_prelabels.sh --execute

scripts/start_windows_p6_prelabels.sh
FAR_P6_PRELABEL_ALLOWED=1 scripts/start_windows_p6_prelabels.sh --execute
scripts/check_windows_p6_prelabels.sh
```

After 217 rows complete:

```bash
scripts/stop_windows_p6_prelabels.sh --execute --stop-ollama
FAR_P6_FETCH_ALLOWED=1 scripts/fetch_windows_p6_prelabels.sh --execute
```

The installer preserves and checks every native prompt/raw-response hash. The
accepted result is present in the published `artifacts-v1` diagnostic release.

## 4. P6-M machine-only stability audit (complete)

The separately authorized non-human substitute audit completed three distinct
remote families, two views per item, and 1,302 accepted rows with zero failed
attempts. Returned raw outputs and the deterministic report verify. Consensus
covered only 15/217 samples and 202 remained contested, so P6-M did not provide
a broad human substitute and did not modify any P6 reviewer/adjudicator slot.
Both dedicated remote services are inactive. Re-running P6-M would require new
authorization and a new explicit protocol decision.
The minimal 1.7 MiB juror evidence tree is tracked with the report so a fresh
clone can rerun prompt/raw-response and identity verification after installing
the published diagnostic packet; no model weights or caches are included.

## 5. Optional future P6 human branch (inactive)

No real reviewers or adjudicator are available. This branch is outside the
accepted no-human profile, has no active owner or deadline, and is not a current
project blocker. It reopens only if real people become available and the project
explicitly chooses to pursue strict human-mappability, human-IAA, or
adjudicated-gold claims. It cannot be automated or substituted with more models.

If it is ever reopened:

1. Give two distinct reviewers only their respective blank 217-row templates
   and visible contexts; hide machine labels, scores, analysis strata, and the
   other reviewer.
2. Freeze and install both complete reviewer files.
3. Give a third distinct adjudicator the two frozen reviews and machine labels.
4. Install all 217 adjudications, analyze, and run the independent verifier as
   described in [`P6_EXECUTION.md`](P6_EXECUTION.md).

Low agreement is a result, not permission to remove rows or change the ontology.

## 6. P10-B completion record

P10-B received separate authorization and completed on 2026-07-12. The exact
archive was published as
[`artifacts-v1`](https://github.com/xiaweiyi713/FAR/releases/tag/artifacts-v1):

- bytes: `5,639,635`;
- SHA-256: `5e3f28dcd81d2af3170f740611b9f59b8bbe1ee6e869379d5794730db4ecf96e`;
- files: `336`;
- tree SHA-256: `8f620af737f3b04f5b3813b06c7183743a3ae14f7c8fd869f43a83b9a821dbff`.

The asset was downloaded from GitHub through the installer into an empty
directory and compared against the complete source tree before tracked
`diagnostics/` removal. Fresh checkouts and CI now install the ignored local
tree from the immutable manifest:

```bash
uv run falsirag ops diagnostic-data install
```

This authorization did not include a Git-history rewrite or LFS migration;
historical blobs remain reachable from older commits and the immutable tag.

## Authorization boundaries

The following are deliberately separate approvals:

- push the reviewed source commit;
- modify the remote worktree/install units;
- start P5 model execution;
- fetch P5 artifacts;
- start P6 model execution;
- fetch/install P6 artifacts;
- start/fetch P6-M machine-only audit artifacts;
- publish the diagnostic GitHub release and remove tracked diagnostics;
- supply real reviewer/adjudicator work.

The final item is an optional future authorization, not an active dependency.

An approval for one item does not imply any later item.
