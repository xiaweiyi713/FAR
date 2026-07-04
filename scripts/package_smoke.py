"""Smoke-test an installed FAR distribution without importing the source tree."""

from __future__ import annotations

import json
from importlib.metadata import entry_points, version
from pathlib import Path

import bench
import experiments
import far
from bench.build.validate_bench import validate

EXPECTED_ENTRY_POINTS = {
    "falsirag-build-ramdocs",
    "falsirag-jury-paper-readiness",
    "falsirag-jury-sensitivity",
    "falsirag-project-status",
    "falsirag-run",
    "falsirag-scan-secrets",
    "falsirag-solo-paper-readiness",
    "falsirag-validate-bench",
}


def main() -> None:
    bench_dir = Path(bench.__file__).resolve().parent
    config = Path(experiments.__file__).resolve().parent / "configs/offline_smoke.yaml"
    report = validate(bench_dir)
    installed_commands = {item.name for item in entry_points(group="console_scripts")}
    missing_commands = sorted(EXPECTED_ENTRY_POINTS - installed_commands)

    checks = {
        "candidate_benchmark": bool(report.get("candidate_ready")),
        "counter_evidence_recall": report.get("counter_evidence_retrieval", {}).get("recall"),
        "offline_config": config.is_file(),
        "entry_points": not missing_commands,
        "far_import": Path(far.__file__).is_file(),
    }
    errors = sorted(name for name, passed in checks.items() if passed is False)
    if checks["counter_evidence_recall"] != 0.91:
        errors.append("counter_evidence_recall")
    if missing_commands:
        errors.append(f"missing_entry_points:{','.join(missing_commands)}")
    result = {
        "schema_version": "far-installed-package-smoke-v1",
        "valid": not errors,
        "distribution_version": version("falsification-augmented-retrieval"),
        "checks": checks,
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
