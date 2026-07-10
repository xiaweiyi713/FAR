"""Stable paths for source checkouts and installed FAR distributions."""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent


def repository_root() -> Path:
    """Return the FAR checkout root, or the installed package root as a fallback."""

    override = os.environ.get("FAR_REPO_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    candidate = PACKAGE_ROOT.parent
    if (candidate / "pyproject.toml").is_file():
        return candidate
    return PACKAGE_ROOT


def experiment_config_dir() -> Path:
    """Return the packaged experiment configuration directory."""

    return PACKAGE_ROOT / "experiments" / "configs"


def benchmark_data_dir() -> Path:
    """Prefer checkout benchmark data and fall back to the packaged snapshot."""

    checkout = repository_root() / "bench"
    if (checkout / "manifest.json").is_file():
        return checkout
    return PACKAGE_ROOT / "bench" / "data"


def resolve_project_path(path: str | Path) -> Path:
    """Resolve current and frozen pre-P10 paths without restoring old packages."""

    value = Path(path)
    if value.is_absolute():
        return value
    legacy_config = Path("experiments") / "configs"
    try:
        suffix = value.relative_to(legacy_config)
    except ValueError:
        return repository_root() / value
    return experiment_config_dir() / suffix
