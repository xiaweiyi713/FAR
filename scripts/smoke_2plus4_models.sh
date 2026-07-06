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
command -v python >/dev/null
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
    compute_apps="$(
      "${nvidia_smi}" \
        --query-compute-apps=pid,process_name,used_memory \
        --format=csv,noheader,nounits 2>/dev/null || true
    )"
    if [[ -n "${compute_apps//[[:space:]]/}" ]] || (( utilization > 20 )); then
      echo "GPU is occupied; model smoke deferred" >&2
      if [[ -n "${compute_apps//[[:space:]]/}" ]]; then
        echo "${compute_apps}" >&2
      fi
      exit 75
    fi
    echo "GPU memory is above the idle threshold but no compute app is active; continuing smoke." >&2
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
  if ! python - "${tags}" "${model}" <<'PY'
import json
import sys

tags = json.loads(sys.argv[1])
model = sys.argv[2]
for item in tags.get("models", []):
    if item.get("name") == model or item.get("model") == model:
        raise SystemExit(0)
raise SystemExit(1)
PY
  then
    if [[ "${pull_missing}" != true ]]; then
      echo "missing ${model}; rerun with --pull after the GPU is idle" >&2
      missing=1
      continue
    fi
    "${ollama_bin}" pull "${model}"
    tags="$(curl -fsS http://127.0.0.1:11434/api/tags)"
  fi

  request="$(
    python - "${model}" <<'PY'
import json
import sys

print(json.dumps({
    "model": sys.argv[1],
    "prompt": "Reply with exactly SMOKE_OK.",
    "stream": False,
    "keep_alive": 0,
    "options": {"temperature": 0, "num_predict": 16},
}))
PY
  )"
  response="$(curl -fsS --max-time 300 \
    -H 'Content-Type: application/json' \
    -d "${request}" \
    http://127.0.0.1:11434/api/generate)"
  if ! python - "${response}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("error") is not None or "SMOKE_OK" not in str(payload.get("response", "")):
    raise SystemExit(1)
PY
  then
    echo "${model}: smoke response failed validation" >&2
    exit 1
  fi
  python - \
    "${tags}" \
    "${response}" \
    "${family}" \
    "${model}" \
    "${config_path}" \
    "${config_sha256}" \
    "${protocol_fingerprint}" \
    "$(date --iso-8601=seconds)" \
    >"${output_dir}/${family}.json" <<'PY'
import json
import sys

tags = json.loads(sys.argv[1])
response = json.loads(sys.argv[2])
family = sys.argv[3]
model = sys.argv[4]
config_path = sys.argv[5]
config_sha256 = sys.argv[6]
protocol_fingerprint = sys.argv[7]
created_at = sys.argv[8]
model_record = None
for item in tags.get("models", []):
    if item.get("name") == model or item.get("model") == model:
        model_record = item
        break
if model_record is None:
    raise SystemExit(f"model record disappeared before smoke record write: {model}")
print(json.dumps(
    {
        "schema_version": "far-2plus4-local-model-smoke-v1",
        "created_at": created_at,
        "protocol_fingerprint": protocol_fingerprint,
        "model_family": family,
        "model": model,
        "config_path": config_path,
        "config_sha256": config_sha256,
        "model_record": model_record,
        "response": response.get("response", ""),
        "smoke_passed": True,
        "benchmark_data_accessed": False,
        "publication_gold": False,
        "human_iaa": False,
    },
    ensure_ascii=False,
    indent=2,
    sort_keys=True,
))
PY
  echo "${family}/${model}: smoke passed"
done

if (( missing != 0 )); then
  exit 3
fi
python -m experiments.model_smoke_2plus4 --output-dir "${output_dir}"
echo "2+4 local model smoke records: ${output_dir}"
