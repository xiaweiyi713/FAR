from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.generate_sbom import build_sbom, main, validate_sbom, write_sbom


def _component(sbom: dict[str, object], name: str) -> dict[str, object]:
    components = sbom["components"]
    assert isinstance(components, list)
    return next(item for item in components if isinstance(item, dict) and item["name"] == name)


def test_project_sbom_includes_required_and_grouped_optional_dependencies() -> None:
    sbom = build_sbom(Path(__file__).parents[1])

    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"
    assert sbom["metadata"]["component"]["name"] == "falsification-augmented-retrieval"
    assert _component(sbom, "pyyaml")["scope"] == "required"
    faiss = _component(sbom, "faiss-cpu")
    assert faiss["scope"] == "optional"
    properties = faiss["properties"]
    assert isinstance(properties, list)
    assert {"name": "far:dependency-groups", "value": "experiment,models"} in properties


def test_sbom_validation_rejects_stale_components(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    sbom = build_sbom(root)
    sbom["components"] = sbom["components"][:-1]
    output = write_sbom(sbom, tmp_path / "sbom.json")

    audit = validate_sbom(output, root)

    assert audit.valid is False
    assert "SBOM dependency components are stale or incomplete" in audit.errors


def test_sbom_cli_writes_valid_audit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = Path(__file__).parents[1]
    output = tmp_path / "far.cdx.json"

    main(["--project-root", str(root), "--output", str(output), "--check", "--json"])

    captured = capsys.readouterr()
    audit = json.loads(captured.out)
    assert audit["valid"] is True
    assert audit["component_count"] >= 2
