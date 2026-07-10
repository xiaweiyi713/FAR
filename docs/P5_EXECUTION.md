# P5 registered RAMDocs ablation execution

This runbook operationalizes the frozen
[`PREREG_ORACLE_ATTRIBUTION_AMENDMENT_2026-07-10_P5_ABLATIONS.md`](PREREG_ORACLE_ATTRIBUTION_AMENDMENT_2026-07-10_P5_ABLATIONS.md).
It does not change H3/H5, the ±0.02 equivalence bounds, or the registered 90%
sample-cluster bootstrap.

## Frozen inputs

The fail-closed workflow in `far.experiments.p5_ablations` requires:

- the amendment at SHA-256
  `59207d5e4bd51e448d41c465b2789149e6f26516847757287fbedc039b91d937`;
- tag `prereg-p5-ablations-v1`, commit
  `f135766bbe90deb42f55b420a211516b55c46f65` as an ancestor of the run commit;
- `far/experiments/configs/ramdocs_qwen.yaml` at SHA-256
  `a5e63643acab84ae26fc190d42931ac95b0fa4f84f9bec4aa7c3a70b18c9f6cb`;
- the frozen Round 1 initial answers at SHA-256
  `5fbcea9b6b2a6cc1136e87d8bb7a2335feebe8b5e2f5b1f54afcd78a7abbbc6b`;
- the complete 350-item RAMDocs dev-label split and its corpus/manifest fingerprints;
- Ollama `qwen3.5:9b` digest
  `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`;
- the pinned local NLI snapshot
  `cross-encoder/nli-distilroberta-base@b14d131f9d32668a5e6a982729b57ff6ed5dfcbd`;
- one clean post-preregistration Git commit shared by all three runs.

## Commands

Preflight does not open the combined dev/test label file or the test-input file.
It checks the frozen dev/corpus fingerprints, local NLI snapshot, clean source
identity, Ollama service, and immutable model digest:

```bash
uv run falsirag diag p5-ablations status
```

The registered runner resumes each arm by checkpoint and then finalizes the
results:

```bash
uv run falsirag diag p5-ablations run-all
```

The exact arms are `far`, `far_minus_typed_revision_aggressive`, and
`far_flat_claims`. They must all contain the same implementation SHA, source
commit, configuration, initial-answer SHA, and Ollama runtime identity.
`outputs/p5_ramdocs_v1` is intentionally ignored so the first arm does not make
the source dirty before the other two identities are recorded.

After a completed or transferred run, finalization and independent verification
can be repeated without model calls:

```bash
uv run falsirag diag p5-ablations finalize
uv run falsirag diag p5-ablations verify
```

The scorer reads `splits/dev.jsonl` directly and never opens the combined
dev/test task-label file. The verifier independently rescans all 3×350 sample
IDs, run identities, prediction fingerprints, RAMDocs scores, and both
2,000-resample comparisons.
It rejects mixed commits, old implementations, the wrong model digest, partial
runs, any test access, stale reports, or tampered scores.

## Interpretation

For each hypothesis the recorded contrast is `full - ablation` in RAMDocs exact
match. The verdict is:

- `equivalent` only when the whole 90% interval is inside `[-0.02, +0.02]`;
- `not_equivalent` only when the whole interval lies below −0.02 or above +0.02;
- `uncertain` otherwise.

The result is a registered upstream-labelled development enhancement. It is not
held-out/test evidence, publication-grade human gold, or human IAA.
