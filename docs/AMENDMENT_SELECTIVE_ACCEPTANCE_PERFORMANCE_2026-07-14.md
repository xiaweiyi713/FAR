# P14 Amendment: Result-Blind Runtime Lifecycle Repair

Status: frozen after pausing the incomplete v1 run and before any v2 model
output is generated or inspected.

This document amends only the runtime lifecycle in
`PREREG_SELECTIVE_ACCEPTANCE_2026-07-14.md`. The research question, source
rows, deterministic split, operational fields, model and digest, FAR method,
policy features, candidate grid, calibration gate, evaluation gate, bootstrap,
claim limits, and prohibition on test access remain unchanged.

## Why an amendment is necessary

The first formal attempt used the exact v1 preregistration commit
`bfee386a0d44b9ab9a8ac8dacd373d2c680b725a` and configuration
`far/experiments/configs/qwen_open.yaml`. That configuration set
`unload_after_sample: true`. Each of the first ten complete rows therefore
unloaded and reloaded the 9B model, while one FAR row issued roughly ten
sequential generation requests interleaved with CPU retrieval and NLI. The
observed elapsed-time logs were used only to diagnose throughput. No generated
answer, trace, construction outcome, policy feature, calibration label, or
evaluation label was inspected or scored.

The user requested a pause so the GPU could be reassigned. The experiment was
stopped at an append-only checkpoint boundary and its dedicated Ollama process
was terminated. The stop exposed a second lifecycle defect: the experiment
unit synchronously stopped its ordered dependency from `ExecStopPost`, which
could leave systemd waiting until timeout.

## Retired v1 evidence

The incomplete directory `/mnt/d/FAR-outputs/selective_acceptance_v1` is
retained as operational evidence and is permanently ineligible for P14
analysis, completion, cache reuse, or combination with v2.

- complete checkpoint rows: `10`;
- protocol-manifest SHA-256:
  `3096823ee8e4029273deaf1581280c24faa670211ff7e134a2630190c155ed68`;
- run-identity SHA-256:
  `4bd9a9325e09ddcac3299ae82eca0be8393cd1dd15c2bde6581587d55f57ecce`;
- checkpoint SHA-256:
  `f968b98b52aece126d5adfc7b6771e920cf508a896a22766a82ee9613713e123`;
- operational-input SHA-256:
  `ad3e4d3f08b41d3d7457dd240c923beb90a8dcea1a972ddf704bb96b1fd57fe6`;
- finalized predictions, run manifest, JSON report, and Markdown report: absent;
- service restart count: zero before the requested pause;
- construction outcomes and generated row contents inspected: no.

The v1 cache path and namespace are forbidden for v2. A verifier must reject a
v1 source revision, v1 tag, v1 configuration, v1 output root, partial v1
checkpoint, or mixed prediction set.

## Frozen v2 lifecycle

The complete v2 run restarts from zero over all 120 registered operational
rows. It uses `far/experiments/configs/qwen_selective_acceptance.yaml`, whose
SHA-256 is
`e0a825fbac36c21ce7dc08f73f30f6bf75e7ed5da7dac561bf964d5388bd75d9`.
Relative to the v1 configuration, exactly these LLM lifecycle fields change:

- `unload_after_sample: false`;
- `keep_alive: 24h`;
- cache path: `outputs/cache/qwen_selective_acceptance_v2.sqlite3`;
- cache namespace: `far-qwen3.5-9b-selective-acceptance-v2`.

The new output root is `/mnt/d/FAR-outputs/selective_acceptance_v2`. It must not
exist before guarded preparation, and preparation must fail closed rather than
adopt an unknown pre-existing directory. The dedicated Ollama server remains
single-run infrastructure and is stopped after successful completion or an
explicit operator pause. `ExecStopPost` may enqueue that stop without blocking
the experiment unit's own shutdown ordering.

Model residence and provider prompt-cache behavior are part of the v2 runtime,
so this amendment does not claim the ten v1 outputs would have been identical.
Only a fresh, complete v2 run is eligible. Temperature remains zero, thinking
remains disabled, maximum generation remains 1200 tokens, and the exact model
digest remains
`6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`.

## Execution and stopping rules

- No v2 model output may be generated before the clean v2 preregistration tag
  is pushed.
- No model may be run or downloaded on the local Mac.
- `windows-gpu` must pass the same idle-state preflight; if another task is
  present, P14 waits.
- v2 cannot reuse v1 predictions, checkpoint rows, provider cache, or output
  paths. It must produce 120 fresh checkpoint rows and finalized predictions.
- Any v2 interruption resumes only after an exact run-identity match. A source,
  configuration, packet, model, or cache-namespace mismatch is a hard failure.
- Calibration and evaluation remain unscored until the complete v2 run passes
  the original deterministic run verifier.

The amended preregistration tag is `prereg-selective-acceptance-v2`. It must
point to the exact clean source commit used for all eligible P14 v2 rows.
