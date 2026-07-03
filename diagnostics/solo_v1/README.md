# FAR single-author diagnostic evidence

This directory is a fingerprinted evidence bundle for the
`single_author_machine_audited_diagnostic` study profile.

It contains the complete 60-sample development predictions, evaluation scores,
reports, tables, figures, and the 300-row machine-label audit used by the public
diagnostic. Run `uv run falsirag-solo-release verify diagnostics/solo_v1` from
the repository root to verify every file and recompute all result-bundle checks.

Rebuild it from the ignored local evidence with:

```bash
uv run falsirag-solo-release build \
  --data-dir bench \
  --machine-report outputs/machine_consensus_v1/machine_consensus_report.json \
  --suite-dir outputs/remote_qwen_six_baseline_suite \
  --blind-bundle-dir outputs/handoff/falsirag_blind_test_technical_v1 \
  --output-dir diagnostics/solo_v1 \
  --overwrite
```

## Interpretation boundary

- These are development-set diagnostics over construction-derived labels.
- The benchmark has machine signals, not independent human gold.
- The test-bundle entry is only a gold-free local technical audit.
- This bundle is not an externally held blind test, human IAA, a multi-model
  result, or publication-ready evidence.
- Nothing here changes or satisfies the strict submission readiness gate.

The machine audit deliberately retains all 122 disputed rows and never rewrites
the construction-derived reference labels from machine agreement.
