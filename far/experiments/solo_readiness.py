"""Audit the honest, fully automated single-author FAR study profile.

This profile is intentionally separate from submission_readiness.py.  It can
certify a reproducible machine-audited diagnostic artifact, but it cannot
certify human annotation, external custody, human policy review, or
publication-ready gold.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from far.bench.build.build_blind_bundle import audit_bundle
from far.bench.build.common import sha256_file, write_json
from far.bench.build.machine_consensus import REPORT_VERSION
from far.bench.build.validate_bench import validate
from far.experiments.validate_results import validate_result_bundle

EXPECTED_METHODS = {
    "far",
    "minus_boundary_query",
    "minus_refutation_query",
    "minus_typed_conflict",
    "minus_typed_revision",
    "vanilla",
    "multi_query_rag",
    "reflective_rag",
    "crag_style_reproduction",
    "self_rag_style_reproduction",
    "counterrefine_style_reproduction",
}
BASELINES = {
    "vanilla",
    "multi_query_rag",
    "reflective_rag",
    "crag_style_reproduction",
    "self_rag_style_reproduction",
    "counterrefine_style_reproduction",
}
ARTIFACT_LABELS = {"vanilla": "vanilla_rag"}


@dataclass(frozen=True)
class Gate:
    name: str
    passed: bool
    detail: str
    evidence: dict[str, Any]


def _gate(name: str, check: Callable[[], dict[str, Any]]) -> Gate:
    try:
        evidence = check()
        return Gate(name, True, "passed", evidence)
    except Exception as exc:
        return Gate(name, False, str(exc), {})


def _machine_gate(data_dir: Path, report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema_version") != REPORT_VERSION:
        raise ValueError("unsupported machine-consensus report")
    if report.get("ready_for_solo_machine_audited_study") is not True:
        raise ValueError("machine-consensus report did not pass its checks")
    if report.get("publication_gold") is not False:
        raise ValueError("machine-consensus report must remain non-gold")
    if report.get("human_annotation_replaced") is not False:
        raise ValueError("machine-consensus report falsely claims to replace humans")
    expected = {
        "benchmark_sha256": sha256_file(data_dir / "falsirag_bench.jsonl"),
        "corpus_sha256": sha256_file(data_dir / "corpus.jsonl"),
    }
    if report.get("source_fingerprints") != expected:
        raise ValueError("machine-consensus report is stale for the benchmark")
    rows_path = report_path.parent / str(report["machine_consensus_rows"])
    if sha256_file(rows_path) != report.get("machine_consensus_rows_sha256"):
        raise ValueError("machine-consensus row fingerprint mismatch")
    return {
        "report_sha256": sha256_file(report_path),
        "rows_sha256": sha256_file(rows_path),
        "samples": report.get("samples"),
        "dispositions": report.get("dispositions"),
        "sources": sorted(report.get("sources", {})),
    }


def _candidate_gate(data_dir: Path) -> dict[str, Any]:
    report = validate(data_dir)
    if not report["valid"]:
        raise ValueError(f"candidate benchmark validation failed: {report['errors']}")
    return report


def _suite_gate(data_dir: Path, suite_dir: Path) -> dict[str, Any]:
    manifest_path = suite_dir / "suite_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "far-suite-manifest-v1":
        raise ValueError("unsupported suite manifest")
    if manifest.get("diagnostic_only") is not True or manifest.get("allow_test") is not False:
        raise ValueError("solo profile accepts only a clearly marked dev diagnostic suite")
    if manifest.get("split") != "dev":
        raise ValueError("solo profile suite must use the development split")
    if set(manifest.get("methods", [])) != EXPECTED_METHODS:
        raise ValueError("solo profile requires FAR, four ablations, and six baselines")
    benchmark_sha = sha256_file(data_dir / "falsirag_bench.jsonl")
    if manifest.get("benchmark_sha256") != benchmark_sha:
        raise ValueError("suite was run against a different benchmark")
    summaries = manifest.get("run_manifests", {})
    expected_summary_keys = {ARTIFACT_LABELS.get(label, label) for label in EXPECTED_METHODS}
    if set(summaries) != expected_summary_keys:
        raise ValueError("suite run summaries are incomplete")
    validations: dict[str, dict[str, Any]] = {}
    for label in sorted(EXPECTED_METHODS):
        artifact_label = ARTIFACT_LABELS.get(label, label)
        summary = summaries[artifact_label]
        if summary.get("partial") is not False or int(summary.get("completed", 0)) < 1:
            raise ValueError(f"{label}: incomplete run summary")
        run_root = suite_dir / "runs"
        run_dir = (
            run_root / "baselines" / artifact_label
            if label in BASELINES
            else run_root / artifact_label
        )
        evaluation_dir = suite_dir / "evaluations" / artifact_label
        validation = validate_result_bundle(run_dir, evaluation_dir)
        if not validation["valid"]:
            raise ValueError(f"{label}: invalid result bundle: {validation['errors']}")
        report_path = evaluation_dir / "report.json"
        if sha256_file(report_path) != manifest.get("reports", {}).get(label):
            raise ValueError(f"{label}: evaluation report fingerprint mismatch")
        validations[label] = {
            "samples": validation["run"]["samples"],
            "predictions_sha256": summary.get("predictions_sha256"),
            "report_sha256": sha256_file(report_path),
        }
    return {
        "suite_manifest_sha256": sha256_file(manifest_path),
        "split": "dev",
        "diagnostic_only": True,
        "methods": validations,
    }


def _blind_gate(data_dir: Path, bundle_dir: Path) -> dict[str, Any]:
    audit = audit_bundle(bundle_dir, allow_technical=True)
    manifest = json.loads((bundle_dir / "blind_bundle_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("source_corpus_sha256") != sha256_file(data_dir / "corpus.jsonl"):
        raise ValueError("technical blind bundle was built from a different corpus")
    return audit


def audit(
    data_dir: Path,
    machine_report: Path,
    suite_dir: Path,
    blind_bundle_dir: Path,
) -> dict[str, Any]:
    gates = [
        _gate("candidate_benchmark", lambda: _candidate_gate(data_dir)),
        _gate("machine_annotation_audit", lambda: _machine_gate(data_dir, machine_report)),
        _gate("complete_local_dev_suite", lambda: _suite_gate(data_dir, suite_dir)),
        _gate("gold_free_local_test_bundle", lambda: _blind_gate(data_dir, blind_bundle_dir)),
    ]
    complete = all(gate.passed for gate in gates)
    return {
        "schema_version": "far-solo-readiness-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "study_profile": "single_author_machine_audited_diagnostic",
        "complete": complete,
        "gates": [asdict(gate) for gate in gates],
        "blockers": [gate.name for gate in gates if not gate.passed],
        "claims": {
            "allowed": [
                "machine-audited synthetic benchmark",
                "complete local development comparison",
                "reproducible diagnostic evidence",
            ],
            "forbidden": [
                "human-validated gold",
                "human inter-annotator agreement",
                "externally held blind test",
                "publication-ready final evidence",
                "multi-model generality from a single local model",
            ],
        },
        "strict_submission_gate_affected": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("bench"))
    parser.add_argument("--machine-report", type=Path, required=True)
    parser.add_argument("--suite-dir", type=Path, required=True)
    parser.add_argument("--blind-bundle-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(
        args.data_dir,
        args.machine_report,
        args.suite_dir,
        args.blind_bundle_dir,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        write_json(args.output, report)
    if not report["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
