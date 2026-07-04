#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 {mistral|google} OUTPUT_DIR" >&2
  exit 2
fi

family="$1"
output_dir="$2"
case "$family" in
  mistral) config="experiments/configs/mistral_open.yaml" ;;
  google) config="experiments/configs/gemma_open.yaml" ;;
  *) echo "family must be mistral or google" >&2; exit 2 ;;
esac

if [[ -f scripts/windows_gpu_env.sh ]]; then
  # shellcheck source=/dev/null
  source scripts/windows_gpu_env.sh
fi

python -m experiments.run_suite \
  --config "$config" \
  --data-dir bench \
  --output-dir "$output_dir" \
  --split dev \
  --baseline crag_style_reproduction \
  --baseline counterrefine_style_reproduction \
  --ablation minus_typed_conflict \
  --resamples 2000 \
  --seed 1729
