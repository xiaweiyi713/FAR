"""Smoke-test an installed FAR distribution without importing the source tree."""

from __future__ import annotations

import json
from importlib.metadata import entry_points, version
from importlib.util import find_spec
from pathlib import Path

import far
from far.adapters import BM25Retriever
from far.artifacts import DEFAULT_MANIFEST
from far.bench.build.validate_bench import validate
from far.experiments.type_mappability import ADJUDICATOR_FORM_TEMPLATE, REVIEWER_FORM_TEMPLATE
from far.models import EvidenceDocument
from far.paths import benchmark_data_dir, experiment_config_dir

EXPECTED_ENTRY_POINTS = {
    "falsirag",
    "falsirag-attribution-evidence",
    "falsirag-boundary-evidence",
    "falsirag-build-boundary",
    "falsirag-power",
    "falsirag-family-dev-evidence",
    "falsirag-build-ramdocs",
    "falsirag-jury-paper-readiness",
    "falsirag-jury-sensitivity",
    "falsirag-project-status",
    "falsirag-round2-failure-readiness",
    "falsirag-run",
    "falsirag-scan-secrets",
    "falsirag-solo-paper-readiness",
    "falsirag-type-mappability-machine",
    "falsirag-validate-bench",
    "falsirag-verify-2plus4-smoke",
}


def main() -> None:
    bench_dir = benchmark_data_dir()
    config = experiment_config_dir() / "offline_smoke.yaml"
    report = validate(bench_dir)
    installed_commands = {item.name for item in entry_points(group="console_scripts")}
    missing_commands = sorted(EXPECTED_ENTRY_POINTS - installed_commands)
    bm25_results = BM25Retriever(
        [
            EvidenceDocument("bm25-relevant", "Audited revenue was 18 million."),
            EvidenceDocument("bm25-noise", "Rain is expected tomorrow."),
        ]
    ).retrieve("audited revenue", top_k=1)

    checks = {
        "candidate_benchmark": bool(report.get("candidate_ready")),
        "counter_evidence_recall": report.get("counter_evidence_retrieval", {}).get("recall"),
        "diagnostic_manifest": DEFAULT_MANIFEST.is_file(),
        "offline_config": config.is_file(),
        "offline_reviewer_form": REVIEWER_FORM_TEMPLATE.is_file(),
        "offline_adjudicator_form": ADJUDICATOR_FORM_TEMPLATE.is_file(),
        "entry_points": not missing_commands,
        "far_import": Path(far.__file__).is_file(),
        "generic_namespaces_absent": all(
            find_spec(name) is None for name in ("baselines", "bench", "eval", "experiments")
        ),
        "self_contained_bm25": bool(
            bm25_results and bm25_results[0].evidence_id == "bm25-relevant"
        ),
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
