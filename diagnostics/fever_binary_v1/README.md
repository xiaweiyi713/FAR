# FEVER binary transfer diagnostic

This frozen diagnostic evaluates binary conflict detection on 100 visible
FEVER claim-to-gold-evidence pairs: 40 inherited REFUTES positives and 60
inherited SUPPORTS negatives.

The SUPPORTS/REFUTES reference comes from human-annotated FEVER labels.
The temporal/numeric/source/definition buckets were generated heuristically
and are used only for descriptive slices; they are not typed gold.

## Results

| Detector | Accuracy | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| heuristic | 0.720 | 1.000 | 0.300 | 0.462 |
| vera_nli | 0.720 | 0.800 | 0.400 | 0.533 |

The paired accuracy difference is +0.000 (95% bootstrap [-0.050, +0.050]); exact McNemar p=1.000.

## Interpretation boundary

This is a visible external-slice binary transfer diagnostic. It is not a
full FAR pipeline result, typed-conflict gold, an externally held blind test,
or a publication-ready main result. The frozen result is intentionally not
tuned after inspection.

- FEVER dataset: https://fever.ai/dataset/fever.html
- Pinned gold-evidence derivative: https://huggingface.co/datasets/copenlu/fever_gold_evidence
