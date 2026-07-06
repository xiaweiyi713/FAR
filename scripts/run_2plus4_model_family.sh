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

ramdocs_data_dir="${RAMDOCS_DATA_DIR:-bench/external/ramdocs_v1}"
ramdocs_round1_dir="${RAMDOCS_ROUND1_DIR:-diagnostics/ramdocs_v2/round1}"
ramdocs_round2_dir="${RAMDOCS_ROUND2_DIR:-diagnostics/ramdocs_v2/round2}"
ramdocs_config="${RAMDOCS_ROUND2_CONFIG:-diagnostics/ramdocs_v2/round2/config.yaml}"
python -m experiments.phase_b_gate \
  --data-dir "${ramdocs_data_dir}" \
  --round1-dir "${ramdocs_round1_dir}" \
  --round2-dir "${ramdocs_round2_dir}" \
  --config "${ramdocs_config}"

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
