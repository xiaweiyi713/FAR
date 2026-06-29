"""Resolve immutable optional model assets used by VeraRAG adapters."""

from __future__ import annotations

from pathlib import Path

_UNUSED_MODEL_FORMATS = (
    "*.h5",
    "*.msgpack",
    "*.onnx",
    "*.tflite",
    "flax_model.*",
    "onnx/*",
    "openvino/*",
    "tf_model.*",
)


def resolve_huggingface_snapshot(
    model_name: str,
    revision: str | None,
    *,
    local_files_only: bool,
) -> str:
    """Return a local path pinned to one Hugging Face commit when requested."""

    if not revision:
        return model_name
    if Path(model_name).expanduser().exists():
        raise ValueError("a local model path cannot also declare a Hugging Face revision")
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "Pinned Hugging Face models require huggingface-hub; install FAR's "
            "`experiment` extra and the local VeraRAG package."
        ) from exc
    try:
        return str(
            snapshot_download(
                repo_id=model_name,
                revision=revision,
                local_files_only=local_files_only,
                ignore_patterns=_UNUSED_MODEL_FORMATS,
            )
        )
    except Exception as exc:
        mode = "local cache" if local_files_only else "cache or network"
        raise RuntimeError(
            f"Could not resolve pinned model {model_name}@{revision} from the {mode}."
        ) from exc
