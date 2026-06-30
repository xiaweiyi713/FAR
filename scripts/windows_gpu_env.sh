#!/usr/bin/env bash
# Source this file inside WSL before FAR GPU runs. It keeps large artifacts on D:.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "source scripts/windows_gpu_env.sh instead of executing it" >&2
  exit 2
fi

export FAR_WINDOWS_DRIVE_ROOT="${FAR_WINDOWS_DRIVE_ROOT:-/mnt/d}"
export FAR_REMOTE_WORKSPACE="${FAR_REMOTE_WORKSPACE:-${FAR_WINDOWS_DRIVE_ROOT}/FAR-workspace}"
export FAR_MODEL_ROOT="${FAR_MODEL_ROOT:-${FAR_WINDOWS_DRIVE_ROOT}/FAR-models}"
export FAR_RUNTIME_ROOT="${FAR_RUNTIME_ROOT:-${FAR_WINDOWS_DRIVE_ROOT}/FAR-runtime}"
export FAR_OUTPUT_ROOT="${FAR_OUTPUT_ROOT:-${FAR_WINDOWS_DRIVE_ROOT}/FAR-outputs}"

export HF_HOME="${HF_HOME:-${FAR_MODEL_ROOT}/huggingface}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-${HF_HOME}/hub}"
export SENTENCE_TRANSFORMERS_HOME="${SENTENCE_TRANSFORMERS_HOME:-${HF_HOME}/sentence_transformers}"
export OLLAMA_MODELS="${OLLAMA_MODELS:-${FAR_MODEL_ROOT}/ollama}"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-1}"
export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-1}"
export FAR_PYTHON_SITE="${FAR_PYTHON_SITE:-${FAR_RUNTIME_ROOT}/python/site-packages}"

export PATH="${FAR_RUNTIME_ROOT}/ollama/bin:${PATH}"
export LD_LIBRARY_PATH="${FAR_RUNTIME_ROOT}/ollama/lib/ollama:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="${FAR_PYTHON_SITE}${PYTHONPATH:+:${PYTHONPATH}}"

mkdir -p \
  "${FAR_REMOTE_WORKSPACE}" \
  "${HF_HOME}" \
  "${OLLAMA_MODELS}" \
  "${FAR_RUNTIME_ROOT}/ollama" \
  "${FAR_PYTHON_SITE}" \
  "${FAR_OUTPUT_ROOT}"
