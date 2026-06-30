"""Generate and validate FAR's declared-dependency CycloneDX SBOM.

Adapted from VeraRAG's MIT-licensed release generator so the FAR artifact can
remain self-contained at submission time.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

CYCLONEDX_SPEC_VERSION = "1.5"
DEFAULT_OUTPUT = Path("build/sbom/far-sbom.cdx.json")


@dataclass(frozen=True)
class SbomAudit:
    valid: bool
    errors: tuple[str, ...]
    output_path: str
    component_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "output_path": self.output_path,
            "component_count": self.component_count,
        }


def _component(
    name: str,
    requirement: str,
    scope: str,
    groups: set[str],
) -> dict[str, Any]:
    return {
        "type": "library",
        "bom-ref": f"pkg:pypi/{name}",
        "name": name,
        "scope": scope,
        "purl": f"pkg:pypi/{name}",
        "properties": [
            {"name": "far:requirement", "value": requirement},
            {"name": "far:dependency-groups", "value": ",".join(sorted(groups))},
        ],
    }


def build_sbom(project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root)
    metadata = _parse_pyproject(root / "pyproject.toml")
    project = metadata["project"]
    name = str(project["name"])
    version = str(project["version"])
    identity = f"pkg:pypi/{name}@{version}"
    properties = [
        {"name": "far:sbom-generator", "value": "experiments.generate_sbom"},
    ]
    repository = str(metadata.get("repository-url", ""))
    if repository:
        properties.append({"name": "far:repository", "value": repository})
    return {
        "bomFormat": "CycloneDX",
        "specVersion": CYCLONEDX_SPEC_VERSION,
        "serialNumber": f"urn:uuid:{uuid5(NAMESPACE_URL, identity)}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": identity,
                "name": name,
                "version": version,
                "purl": identity,
            },
            "properties": properties,
        },
        "components": _dependency_components(
            project.get("dependencies", []),
            metadata.get("optional-dependencies", {}),
        ),
    }


def write_sbom(sbom: dict[str, Any], output_path: str | Path = DEFAULT_OUTPUT) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def validate_sbom(
    output_path: str | Path = DEFAULT_OUTPUT,
    project_root: str | Path = ".",
) -> SbomAudit:
    path = Path(output_path)
    errors: list[str] = []
    try:
        observed = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return SbomAudit(False, (f"SBOM file does not exist: {path}",), str(path), 0)
    except json.JSONDecodeError as exc:
        return SbomAudit(False, (f"SBOM file is not valid JSON: {exc}",), str(path), 0)
    expected = build_sbom(project_root)
    components = observed.get("components", []) if isinstance(observed, dict) else []
    if not isinstance(observed, dict):
        errors.append("SBOM must be a JSON object")
    elif observed.get("bomFormat") != "CycloneDX":
        errors.append("SBOM bomFormat must be CycloneDX")
    if not isinstance(observed, dict) or observed.get("specVersion") != CYCLONEDX_SPEC_VERSION:
        errors.append(f"SBOM specVersion must be {CYCLONEDX_SPEC_VERSION}")
    if not isinstance(observed, dict) or observed.get("metadata") != expected["metadata"]:
        errors.append("SBOM metadata does not match pyproject project identity")
    if not isinstance(components, list) or not components:
        errors.append("SBOM must include dependency components")
        components = []
    elif components != expected["components"]:
        errors.append("SBOM dependency components are stale or incomplete")
    refs = [str(item.get("bom-ref", "")) for item in components if isinstance(item, dict)]
    if len(refs) != len(set(refs)):
        errors.append("SBOM dependency components must have unique bom-ref values")
    return SbomAudit(not errors, tuple(errors), str(path), len(components))


def _dependency_components(
    required: Any,
    optional: Any,
) -> list[dict[str, Any]]:
    values: dict[str, tuple[str, set[str], str]] = {}
    if isinstance(required, list):
        for requirement in required:
            _add_requirement(values, str(requirement), "required", "default")
    if isinstance(optional, dict):
        for group, requirements in optional.items():
            if group == "all" or not isinstance(requirements, list):
                continue
            for requirement in requirements:
                _add_requirement(values, str(requirement), "optional", str(group))
    return [
        _component(name, requirement, scope, groups)
        for name, (requirement, groups, scope) in sorted(values.items())
    ]


def _add_requirement(
    values: dict[str, tuple[str, set[str], str]],
    requirement: str,
    scope: str,
    group: str,
) -> None:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", requirement)
    if not match:
        return
    name = match.group(1).lower().replace("_", "-")
    if name not in values:
        values[name] = (requirement, {group}, scope)
        return
    existing, groups, existing_scope = values[name]
    groups.add(group)
    merged_scope = "required" if "required" in {scope, existing_scope} else "optional"
    values[name] = (existing, groups, merged_scope)


def _parse_pyproject(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "project": {},
        "optional-dependencies": {},
        "repository-url": "",
    }
    lines = path.read_text(encoding="utf-8").splitlines()
    section = ""
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line or line.startswith("#"):
            index += 1
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.strip("[]")
            index += 1
            continue
        if section == "project" and "=" in line:
            key, value = (part.strip() for part in line.split("=", 1))
            if key in {"name", "version"}:
                result["project"][key] = _toml_string(value)
            elif key == "dependencies":
                value, index = _collect_array(lines, index)
                result["project"][key] = _string_list(value)
                continue
        elif section == "project.optional-dependencies" and "=" in line:
            key = line.split("=", 1)[0].strip()
            value, index = _collect_array(lines, index)
            result["optional-dependencies"][key] = _string_list(value)
            continue
        elif section == "project.urls" and "=" in line:
            key, value = (part.strip() for part in line.split("=", 1))
            if key.strip("\"'").lower() == "repository":
                result["repository-url"] = _toml_string(value)
        index += 1
    project = result["project"]
    if not project.get("name") or not project.get("version"):
        raise ValueError("pyproject [project] must define name and version")
    return result


def _collect_array(lines: list[str], start: int) -> tuple[str, int]:
    collected = [lines[start].split("=", 1)[1].strip()]
    index = start + 1
    while not _array_complete("\n".join(collected)) and index < len(lines):
        collected.append(lines[index].strip())
        index += 1
    return "\n".join(collected), index


def _array_complete(value: str) -> bool:
    depth = 0
    quote: str | None = None
    escaped = False
    saw_array = False
    for char in value:
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "[":
            saw_array = True
            depth += 1
        elif char == "]":
            depth -= 1
    return saw_array and depth == 0 and quote is None


def _string_list(value: str) -> list[str]:
    parsed = ast.literal_eval(value)
    if not isinstance(parsed, list):
        raise ValueError("dependency value must be a TOML string array")
    return [str(item) for item in parsed]


def _toml_string(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    path = write_sbom(build_sbom(args.project_root), args.output)
    audit = validate_sbom(path, args.project_root)
    if args.json:
        print(json.dumps(audit.to_dict(), indent=2, sort_keys=True))
    elif audit.valid:
        print(f"SBOM validated: {audit.component_count} components at {audit.output_path}.")
    else:
        for error in audit.errors:
            print(f"- {error}")
    if args.check and not audit.valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
