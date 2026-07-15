from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
FULL_SHA_ACTION = re.compile(r"^[a-z0-9_.-]+/[a-z0-9_.-]+@[0-9a-f]{40}$", re.IGNORECASE)


def _workflow() -> dict[str, Any]:
    value = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(value, dict)
    return value


def test_ci_has_read_only_permissions_and_declared_triggers() -> None:
    workflow = _workflow()

    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["on"]) == {"push", "pull_request", "workflow_dispatch"}
    assert workflow["on"]["push"]["branches"] == ["main"]


def test_ci_covers_supported_python_versions_without_private_dependencies() -> None:
    workflow = _workflow()
    jobs = workflow["jobs"]
    versions = jobs["tests"]["strategy"]["matrix"]["python-version"]
    install = jobs["tests"]["steps"][2]["run"]
    text = WORKFLOW.read_text(encoding="utf-8")

    assert versions == ["3.10", "3.11", "3.12", "3.13"]
    assert install == "uv sync --locked --extra dev --extra eval"
    assert "VeraRAG" not in text
    assert "secrets." not in text


def test_ci_actions_are_pinned_and_public_gate_is_complete() -> None:
    workflow = _workflow()
    jobs = workflow["jobs"]
    action_refs = [step["uses"] for job in jobs.values() for step in job["steps"] if "uses" in step]
    public_commands = "\n".join(step.get("run", "") for step in jobs["public-diagnostic"]["steps"])

    assert action_refs
    assert all(FULL_SHA_ACTION.fullmatch(action) for action in action_refs)
    assert "ruff format --check" in public_commands
    assert "mypy far tests scripts/package_smoke.py" in public_commands
    assert "falsirag ops repository-maintenance --verify" in public_commands
    assert "falsirag ops longterm-status --check" in public_commands
    assert "falsirag release scan-secrets --json" in public_commands
    assert "falsirag bench validate --data-dir bench" in public_commands
    assert "bash scripts/solo_diagnostic_check.sh" in public_commands
    assert "uv build" in public_commands
    assert "bash scripts/check_release_packages.sh" in public_commands
