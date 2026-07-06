#!/usr/bin/env bash
# Verify the three local 2+4 model families without touching benchmark data.

set -euo pipefail

pull_missing=false
if [[ "${1:-}" == "--pull" ]]; then
  pull_missing=true
elif [[ $# -ne 0 ]]; then
  echo "usage: $0 [--pull]" >&2
  exit 2
fi

if [[ ! -f scripts/windows_gpu_env.sh ]]; then
  echo "run this script from the FAR repository root on the Windows WSL host" >&2
  exit 2
fi
# shellcheck source=/dev/null
source scripts/windows_gpu_env.sh

command -v curl >/dev/null
command -v jq >/dev/null
ollama_bin="${OLLAMA_BIN:-/mnt/d/FAR-runtime/ollama/bin/ollama}"
if [[ ! -x "${ollama_bin}" ]]; then
  ollama_bin="$(command -v ollama)"
fi

for unit in far-ramdocs-round2.service far-ramdocs-phase-a.service; do
  if [[ "$(systemctl --user is-active "${unit}" 2>/dev/null || true)" == "active" ]]; then
    echo "GPU experiment is active (${unit}); model smoke deferred" >&2
    exit 75
  fi
done

nvidia_smi="/usr/lib/wsl/lib/nvidia-smi"
if [[ -x "${nvidia_smi}" ]]; then
  IFS=, read -r memory_used utilization < <(
    "${nvidia_smi}" \
      --query-gpu=memory.used,utilization.gpu \
      --format=csv,noheader,nounits | head -n 1
  )
  memory_used="${memory_used//[[:space:]]/}"
  utilization="${utilization//[[:space:]]/}"
  if (( memory_used > 1500 || utilization > 20 )); then
    echo "GPU is occupied; model smoke deferred" >&2
    exit 75
  fi
fi

if [[ "${pull_missing}" == true ]]; then
  available_kb="$(df -Pk /mnt/d | awk 'NR==2 {print $4}')"
  if ! [[ "${available_kb}" =~ ^[0-9]+$ ]] || (( available_kb < 20 * 1024 * 1024 )); then
    echo "D: needs at least 20 GiB free before pulling all smoke models" >&2
    exit 1
  fi
fi

output_dir="${MODEL_SMOKE_OUTPUT_DIR:-/mnt/d/FAR-outputs/model_smoke_2plus4}"
mkdir -p "${output_dir}"
protocol_fingerprint="$(python - <<'PY'
from experiments.protocol_2plus4 import verify_active_protocol
print(verify_active_protocol())
PY
)"

ollama_was_active=false
if [[ "$(systemctl --user is-active far-ollama-2plus4.service 2>/dev/null || true)" == "active" ]]; then
  ollama_was_active=true
else
  systemctl --user start far-ollama-2plus4.service
fi
cleanup() {
  if [[ "${ollama_was_active}" == false ]]; then
    systemctl --user stop far-ollama-2plus4.service >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

for _ in $(seq 1 30); do
  curl -fsS --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null && break
  sleep 2
done
curl -fsS --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null

models=(
  "mistral|mistral:7b-instruct|experiments/configs/mistral_open.yaml"
  "google|gemma2:9b-instruct|experiments/configs/gemma_open.yaml"
  "meta|llama3.1:8b|experiments/configs/jury_llama.yaml"
)
missing=0
for entry in "${models[@]}"; do
  IFS='|' read -r family model config_path <<<"${entry}"
  config_sha256="$(sha256sum "${config_path}" | awk '{print $1}')"
  tags="$(curl -fsS http://127.0.0.1:11434/api/tags)"
  if ! jq -e --arg model "${model}" '.models[]? | select(.name == $model or .model == $model)' \
    <<<"${tags}" >/dev/null; then
    if [[ "${pull_missing}" != true ]]; then
      echo "missing ${model}; rerun with --pull after the GPU is idle" >&2
      missing=1
      continue
    fi
    "${ollama_bin}" pull "${model}"
    tags="$(curl -fsS http://127.0.0.1:11434/api/tags)"
  fi

  request="$(jq -nc --arg model "${model}" '{
    model: $model,
    prompt: "Reply with exactly SMOKE_OK.",
    stream: false,
    keep_alive: 0,
    options: {temperature: 0, num_predict: 16}
  }')"
  response="$(curl -fsS --max-time 300 \
    -H 'Content-Type: application/json' \
    -d "${request}" \
    http://127.0.0.1:11434/api/generate)"
  if ! jq -e '.error == null and (.response | contains("SMOKE_OK"))' \
    <<<"${response}" >/dev/null; then
    echo "${model}: smoke response failed validation" >&2
    exit 1
  fi
  model_row="$(jq -c --arg model "${model}" \
    '.models[] | select(.name == $model or .model == $model)' <<<"${tags}" | head -n 1)"
  jq -n \
    --arg schema_version "far-2plus4-local-model-smoke-v1" \
    --arg created_at "$(date --iso-8601=seconds)" \
    --arg protocol_fingerprint "${protocol_fingerprint}" \
    --arg family "${family}" \
    --arg model "${model}" \
    --arg config_path "${config_path}" \
    --arg config_sha256 "${config_sha256}" \
    --argjson model_record "${model_row}" \
    --arg response "$(jq -r '.response' <<<"${response}")" \
    '{
      schema_version: $schema_version,
      created_at: $created_at,
      protocol_fingerprint: $protocol_fingerprint,
      model_family: $family,
      model: $model,
      config_path: $config_path,
      config_sha256: $config_sha256,
      model_record: $model_record,
      response: $response,
      smoke_passed: true,
      benchmark_data_accessed: false,
      publication_gold: false,
      human_iaa: false
    }' >"${output_dir}/${family}.json"
  echo "${family}/${model}: smoke passed"
done

if (( missing != 0 )); then
  exit 3
fi
python -m experiments.model_smoke_2plus4 --output-dir "${output_dir}"
echo "2+4 local model smoke records: ${output_dir}"
