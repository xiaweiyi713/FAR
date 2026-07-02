"""Fail-closed audit of the external evidence required for FAR submission."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bench.annotations import validate_annotation_evidence
from bench.build.common import read_jsonl, sha256_file, write_json
from bench.build.validate_bench import validate as validate_benchmark
from experiments.generate_release_checksums import validate_checksum_manifest
from experiments.runner import _implementation_sha256
from experiments.validate_results import validate_result_bundle

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_SCHEMA = "far-submission-evidence-v1"
MODEL_SPECS = {
    "deepseek_v4_flash": "experiments/configs/deepseek.yaml",
    "qwen_3_7_plus": "experiments/configs/qwen_plus.yaml",
    "qwen_3_5_9b": "experiments/configs/qwen_open.yaml",
}
REPORT_METHODS = {
    "far",
    "vanilla",
    "multi_query_rag",
    "reflective_rag",
    "crag_style_reproduction",
    "self_rag_style_reproduction",
    "counterrefine_style_reproduction",
    "minus_typed_conflict",
    "minus_refutation_query",
    "minus_boundary_query",
    "minus_typed_revision",
}
BLIND_METHODS = (REPORT_METHODS - {"vanilla"}) | {"vanilla_rag"}


@dataclass(frozen=True)
class Gate:
    name: str
    passed: bool
    detail: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "evidence": self.evidence,
        }


def _resolve(root: Path, raw: Any) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("evidence path is missing")
    path = Path(raw)
    return path if path.is_absolute() else root / path


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON evidence must be an object: {path}")
    return value


def _reject_template_path(path: Path, label: str) -> None:
    if path.name.endswith(".template.json"):
        raise ValueError(f"{label} must be copied to a real ignored JSON file before use: {path}")


def _reject_template_evidence_path(path: Path, *, allow_incomplete: bool) -> None:
    if path.name.endswith(".template.json") and not allow_incomplete:
        raise ValueError(
            "submission evidence template may only be used with --allow-incomplete; "
            f"copy it to a real ignored JSON file before final readiness: {path}"
        )


def _run_dir(suite: Path, label: str) -> Path:
    if label in REPORT_METHODS - {"far", "vanilla"} and not label.startswith("minus_"):
        return suite / "runs" / "baselines" / label
    if label in {"vanilla", "vanilla_rag"}:
        return suite / "runs" / "baselines" / "vanilla_rag"
    return suite / "runs" / label


def _source_commit(run_dir: Path) -> str:
    revision = _json(run_dir / "run_identity.json").get("source_revision")
    if not isinstance(revision, dict):
        raise ValueError(f"run has no source revision: {run_dir}")
    commit = revision.get("git_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(f"run has no exact Git commit: {run_dir}")
    if revision.get("git_dirty") is not False:
        raise ValueError(f"run was produced from a dirty worktree: {run_dir}")
    return commit


def _validate_identity_binding(
    run_dir: Path,
    *,
    config_sha256: str,
    benchmark_sha256: str,
    corpus_sha256: str,
    split: str,
) -> dict[str, Any]:
    identity = _json(run_dir / "run_identity.json")
    checks = {
        "schema": identity.get("schema_version") == "far-run-signature-v2",
        "config": identity.get("config_sha256") == config_sha256,
        "benchmark": identity.get("benchmark_input_sha256") == benchmark_sha256,
        "corpus": identity.get("corpus_sha256") == corpus_sha256,
        "split": identity.get("split") == split,
        "limit": identity.get("limit") is None,
    }
    failed = sorted(key for key, passed in checks.items() if not passed)
    if failed:
        raise ValueError(f"run identity binding failed for {run_dir}: {failed}")
    return identity


def _gate(name: str, check: Callable[[], dict[str, Any]]) -> Gate:
    try:
        evidence = check()
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return Gate(name, False, str(exc), {})
    return Gate(name, True, "passed", evidence)


def _candidate_gate(root: Path) -> dict[str, Any]:
    report = validate_benchmark(root / "bench")
    if not report["candidate_ready"] or report["counter_evidence_retrieval"]["recall"] < 0.8:
        raise ValueError(f"candidate benchmark validation failed: {report['errors']}")
    return {
        "samples": report["counts"]["samples"],
        "documents": report["counts"]["documents"],
        "counter_evidence_recall": report["counter_evidence_retrieval"]["recall"],
        "fingerprints": report["fingerprints"],
    }


def _annotation_gate(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    data_dir = _resolve(root, config.get("adjudicated_data_dir"))
    report = _json(data_dir / "annotation_report.json")
    manifest = _json(data_dir / "manifest.json")
    validation = validate_benchmark(data_dir)
    evidence_validation = validate_annotation_evidence(data_dir)
    rows = read_jsonl(data_dir / "falsirag_bench.jsonl")
    annotators = report.get("annotators")
    kappas = report.get("mean_kappas")
    if report.get("schema_version") != "falsirag-annotation-report-v1":
        raise ValueError("unsupported annotation report schema")
    if not isinstance(annotators, list) or len(set(map(str, annotators))) < 2:
        raise ValueError("fewer than two distinct annotators are recorded")
    if report.get("adjudicated") is not True or report.get("agreement_gate_passed") is not True:
        raise ValueError("annotation/adjudication agreement gate did not pass")
    adjudicator_id = str(report.get("adjudicator_id", "")).strip()
    if not adjudicator_id:
        raise ValueError("annotation report has no adjudicator ID")
    if not isinstance(kappas, dict) or not kappas or min(map(float, kappas.values())) < 0.6:
        raise ValueError("one or more mean Cohen kappa values are below 0.60")
    if not rows or any(row.get("annotation_status") != "adjudicated" for row in rows):
        raise ValueError("compiled benchmark contains non-adjudicated rows")
    annotation = manifest.get("annotation", {})
    if not isinstance(annotation, dict) or annotation.get("machine_seed_is_gold") is not False:
        raise ValueError("adjudicated manifest does not preserve the non-gold machine-seed flag")
    if annotation.get("adjudicator_id") != adjudicator_id:
        raise ValueError("annotation manifest and report disagree on adjudicator ID")
    if not validation["candidate_ready"]:
        raise ValueError(f"adjudicated benchmark validation failed: {validation['errors']}")
    return {
        "data_dir": str(data_dir),
        "samples": len(rows),
        "annotators": sorted(map(str, annotators)),
        "adjudicator_id": adjudicator_id,
        "mean_kappas": kappas,
        "benchmark_sha256": sha256_file(data_dir / "falsirag_bench.jsonl"),
        "corpus_sha256": sha256_file(data_dir / "corpus.jsonl"),
        "annotation_evidence_manifest_sha256": evidence_validation["evidence_manifest_sha256"],
    }


def _dev_suites_gate(root: Path, config: dict[str, Any], annotation: Gate) -> dict[str, Any]:
    if not annotation.passed:
        raise ValueError("annotation gate must pass before formal dev suites can pass")
    suites = config.get("dev_suites")
    if not isinstance(suites, dict) or set(suites) != set(MODEL_SPECS):
        raise ValueError(f"dev_suites must name exactly: {sorted(MODEL_SPECS)}")
    benchmark_sha = str(annotation.evidence["benchmark_sha256"])
    corpus_sha = str(annotation.evidence["corpus_sha256"])
    commits: set[str] = set()
    implementations: set[str] = set()
    summaries: dict[str, Any] = {}
    for model, relative_config in MODEL_SPECS.items():
        suite = _resolve(root, suites[model])
        manifest = _json(suite / "suite_manifest.json")
        if manifest.get("schema_version") != "far-suite-manifest-v1":
            raise ValueError(f"{model}: not a scored suite")
        if manifest.get("split") != "dev" or manifest.get("limit") is not None:
            raise ValueError(f"{model}: formal dev suite must be complete and untruncated")
        if manifest.get("diagnostic_only") is not False:
            raise ValueError(f"{model}: suite is still marked diagnostic-only")
        if set(manifest.get("methods", [])) != REPORT_METHODS:
            raise ValueError(f"{model}: suite does not contain the preregistered 11 methods")
        if manifest.get("benchmark_sha256") != benchmark_sha:
            raise ValueError(f"{model}: suite is not bound to the adjudicated benchmark")
        if manifest.get("config_sha256") != sha256_file(root / relative_config):
            raise ValueError(f"{model}: config fingerprint mismatch")
        config_sha = sha256_file(root / relative_config)
        reports = manifest.get("reports")
        if not isinstance(reports, dict):
            raise ValueError(f"{model}: report fingerprints are missing")
        for label in sorted(REPORT_METHODS):
            run_dir = _run_dir(suite, label)
            evaluation_dir = (
                suite / "evaluations" / ("vanilla_rag" if label == "vanilla" else label)
            )
            validation = validate_result_bundle(run_dir, evaluation_dir)
            if not validation["valid"]:
                raise ValueError(f"{model}/{label}: {validation['errors']}")
            report_path = evaluation_dir / "report.json"
            if reports.get(label) != sha256_file(report_path):
                raise ValueError(f"{model}/{label}: report fingerprint mismatch")
            if _json(report_path).get("publication_ready") is not True:
                raise ValueError(f"{model}/{label}: report is not adjudicated-publication-ready")
            identity = _validate_identity_binding(
                run_dir,
                config_sha256=config_sha,
                benchmark_sha256=benchmark_sha,
                corpus_sha256=corpus_sha,
                split="dev",
            )
            implementation = identity.get("implementation_sha256")
            if not isinstance(implementation, str) or not re.fullmatch(
                r"[0-9a-f]{64}", implementation
            ):
                raise ValueError(f"{model}/{label}: implementation fingerprint is missing")
            implementations.add(implementation)
            commits.add(_source_commit(run_dir))
        summaries[model] = {
            "suite": str(suite),
            "manifest_sha256": sha256_file(suite / "suite_manifest.json"),
        }
    if len(commits) != 1:
        raise ValueError("formal dev suites were not produced from one frozen commit")
    if len(implementations) != 1:
        raise ValueError("formal dev suites do not share one implementation fingerprint")
    return {
        "frozen_commit": next(iter(commits)),
        "implementation_sha256": next(iter(implementations)),
        "models": summaries,
    }


def _blind_bundle_gate(root: Path, config: dict[str, Any], annotation: Gate) -> dict[str, Any]:
    if not annotation.passed:
        raise ValueError("annotation gate must pass before the final blind bundle can pass")
    bundle = _resolve(root, config.get("blind_bundle_dir"))
    manifest = _json(bundle / "blind_bundle_manifest.json")
    if manifest.get("schema_version") != "falsirag-blind-bundle-v1":
        raise ValueError("unsupported blind bundle schema")
    if manifest.get("gold_included") is not False:
        raise ValueError("blind bundle reports that gold is included")
    test_inputs = bundle / "splits" / "test_inputs.jsonl"
    corpus = bundle / "corpus.jsonl"
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("blind bundle file fingerprints are missing")
    if files.get("splits/test_inputs.jsonl") != sha256_file(test_inputs):
        raise ValueError("blind test input fingerprint mismatch")
    if files.get("corpus.jsonl") != sha256_file(corpus):
        raise ValueError("blind corpus fingerprint mismatch")
    if manifest.get("source_corpus_sha256") != annotation.evidence["corpus_sha256"]:
        raise ValueError("blind bundle was not built from the adjudicated corpus")
    return {
        "bundle": str(bundle),
        "manifest_sha256": sha256_file(bundle / "blind_bundle_manifest.json"),
        "input_sha256": sha256_file(test_inputs),
        "corpus_sha256": sha256_file(corpus),
        "samples": len(read_jsonl(test_inputs)),
    }


def _blind_returns_gate(
    root: Path,
    config: dict[str, Any],
    bundle: Gate,
    dev_suites: Gate,
) -> dict[str, Any]:
    if not bundle.passed or not dev_suites.passed:
        raise ValueError("blind bundle and frozen dev-suite gates must pass first")
    returns = config.get("blind_returns")
    if not isinstance(returns, dict) or set(returns) != set(MODEL_SPECS):
        raise ValueError(f"blind_returns must name exactly: {sorted(MODEL_SPECS)}")
    frozen_commit = dev_suites.evidence["frozen_commit"]
    output: dict[str, Any] = {}
    for model, relative_config in MODEL_SPECS.items():
        suite = _resolve(root, returns[model])
        manifest = _json(suite / "suite_manifest.json")
        checks = {
            "schema": manifest.get("schema_version") == "far-blind-suite-manifest-v1",
            "split": manifest.get("split") == "test",
            "unscored": manifest.get("unscored") is True,
            "gold": manifest.get("gold_loaded") is False,
            "complete": manifest.get("limit") is None and manifest.get("diagnostic_only") is False,
            "input": manifest.get("blind_input_sha256") == bundle.evidence["input_sha256"],
            "corpus": manifest.get("corpus_sha256") == bundle.evidence["corpus_sha256"],
            "config": manifest.get("config_sha256") == sha256_file(root / relative_config),
            "methods": set(manifest.get("methods", [])) == BLIND_METHODS,
        }
        failed = sorted(key for key, passed in checks.items() if not passed)
        if failed:
            raise ValueError(f"{model}: blind return failed checks: {failed}")
        for label in sorted(BLIND_METHODS):
            run_dir = _run_dir(suite, label)
            validation = validate_result_bundle(run_dir)
            if not validation["valid"]:
                raise ValueError(f"{model}/{label}: {validation['errors']}")
            _validate_identity_binding(
                run_dir,
                config_sha256=sha256_file(root / relative_config),
                benchmark_sha256=str(bundle.evidence["input_sha256"]),
                corpus_sha256=str(bundle.evidence["corpus_sha256"]),
                split="test",
            )
            if _source_commit(run_dir) != frozen_commit:
                raise ValueError(f"{model}/{label}: return does not match frozen commit")
        output[model] = {
            "suite": str(suite),
            "manifest_sha256": sha256_file(suite / "suite_manifest.json"),
        }
    return {"frozen_commit": frozen_commit, "models": output}


def _attestation_gate(
    root: Path, config: dict[str, Any], returns: Gate, bundle: Gate
) -> dict[str, Any]:
    if not returns.passed or not bundle.passed:
        raise ValueError("complete blind returns are required before attestation can pass")
    attestation = config.get("blind_test")
    if not isinstance(attestation, dict):
        raise ValueError("blind_test attestation is missing")
    attestation_path = _resolve(root, config.get("blind_test_attestation"))
    _reject_template_path(attestation_path, "blind-test attestation")
    if _json(attestation_path) != attestation:
        raise ValueError("inline blind_test evidence differs from the frozen attestation file")
    if attestation.get("schema_version") != "far-blind-test-attestation-v1":
        raise ValueError("unsupported blind-test attestation schema")
    custodian = str(attestation.get("custodian_id", "")).strip()
    scorer = str(attestation.get("scorer_id", "")).strip()
    if not custodian or not scorer or custodian == scorer:
        raise ValueError("custodian and trusted scorer must be distinct named roles")
    required = {
        "one_shot": True,
        "externally_held": True,
        "gold_loaded_by_custodian": False,
        "all_failures_reported": True,
    }
    failed = [key for key, expected in required.items() if attestation.get(key) is not expected]
    if failed:
        raise ValueError(f"blind-test attestation is incomplete: {failed}")
    if attestation.get("frozen_commit") != returns.evidence["frozen_commit"]:
        raise ValueError("attested frozen commit differs from returned runs")
    if attestation.get("bundle_manifest_sha256") != bundle.evidence["manifest_sha256"]:
        raise ValueError("attestation does not bind the final handoff bundle")
    expected_return_hashes = {
        model: item["manifest_sha256"] for model, item in returns.evidence["models"].items()
    }
    if attestation.get("return_manifest_sha256") != expected_return_hashes:
        raise ValueError("attestation does not bind every model return manifest")
    if not str(attestation.get("completed_at", "")).strip():
        raise ValueError("blind-test completion timestamp is missing")
    return {
        "custodian_id": custodian,
        "scorer_id": scorer,
        "completed_at": attestation["completed_at"],
        "frozen_commit": attestation["frozen_commit"],
        "attestation_sha256": sha256_file(attestation_path),
    }


def _scored_tests_gate(
    root: Path,
    config: dict[str, Any],
    annotation: Gate,
    returns: Gate,
    attestation: Gate,
) -> dict[str, Any]:
    if not annotation.passed or not returns.passed or not attestation.passed:
        raise ValueError("annotation, blind returns, and attestation must pass before scoring")
    suites = config.get("scored_test_suites")
    if not isinstance(suites, dict) or set(suites) != set(MODEL_SPECS):
        raise ValueError(f"scored_test_suites must name exactly: {sorted(MODEL_SPECS)}")
    output: dict[str, Any] = {}
    for model in MODEL_SPECS:
        suite = _resolve(root, suites[model])
        manifest_path = suite / "scored_suite_manifest.json"
        manifest = _json(manifest_path)
        checks = {
            "schema": manifest.get("schema_version") == "far-scored-blind-suite-manifest-v1",
            "model": manifest.get("model_id") == model,
            "split": manifest.get("split") == "test",
            "ready": manifest.get("publication_ready") is True,
            "annotation": manifest.get("annotation_gate_passed") is True,
            "annotation_evidence": manifest.get("annotation_evidence_manifest_sha256")
            == annotation.evidence["annotation_evidence_manifest_sha256"],
            "benchmark": manifest.get("benchmark_sha256")
            == annotation.evidence["benchmark_sha256"],
            "commit": manifest.get("frozen_commit") == returns.evidence["frozen_commit"],
            "return": manifest.get("return_suite_manifest_sha256")
            == returns.evidence["models"][model]["manifest_sha256"],
            "attestation": manifest.get("attestation_sha256")
            == attestation.evidence["attestation_sha256"],
            "methods": set(manifest.get("methods", [])) == REPORT_METHODS,
        }
        failed = sorted(key for key, passed in checks.items() if not passed)
        if failed:
            raise ValueError(f"{model}: scored suite failed checks: {failed}")
        reports = manifest.get("reports")
        if not isinstance(reports, dict):
            raise ValueError(f"{model}: scored report map is missing")
        for label in REPORT_METHODS:
            report_path = suite / "evaluations" / label / "report.json"
            report = _json(report_path)
            if reports.get(label) != sha256_file(report_path):
                raise ValueError(f"{model}/{label}: scored report fingerprint mismatch")
            if report.get("publication_ready") is not True:
                raise ValueError(f"{model}/{label}: scored report is not publication-ready")
            if set(report.get("publication", {}).get("scored_splits", [])) != {"test"}:
                raise ValueError(f"{model}/{label}: report is not test-only")
        artifact_path = suite / "artifacts" / "artifact_manifest.json"
        if manifest.get("artifact_manifest_sha256") != sha256_file(artifact_path):
            raise ValueError(f"{model}: artifact manifest fingerprint mismatch")
        artifact = _json(artifact_path)
        if artifact.get("publication_ready") is not True:
            raise ValueError(f"{model}: final artifacts are not publication-ready")
        if artifact.get("test_only") is not True or set(artifact.get("scored_splits", [])) != {
            "test"
        }:
            raise ValueError(f"{model}: final artifacts are not bound to test-only reports")
        if artifact.get("strict_requirements") != {
            "publication_ready": True,
            "test_only": True,
        }:
            raise ValueError(f"{model}: final artifacts were not built in strict mode")
        if artifact.get("reports") != reports:
            raise ValueError(f"{model}: final artifact report fingerprints do not match scoring")
        if artifact.get("benchmark_sha256") != annotation.evidence["benchmark_sha256"]:
            raise ValueError(f"{model}: final artifacts are bound to the wrong benchmark")
        output[model] = {
            "suite": str(suite),
            "manifest_sha256": sha256_file(manifest_path),
        }
    return {"frozen_commit": returns.evidence["frozen_commit"], "models": output}


def _release_gate(root: Path, config: dict[str, Any], dev_suites: Gate) -> dict[str, Any]:
    path = _resolve(root, config.get("release_checksums"))
    audit = validate_checksum_manifest(path, project_root=root)
    if not audit.valid:
        raise ValueError(f"release checksum audit failed: {list(audit.errors)}")
    if not dev_suites.passed:
        raise ValueError("formal dev suites must pass before the release archive")
    if _implementation_sha256() != dev_suites.evidence["implementation_sha256"]:
        raise ValueError("release implementation differs from the frozen experiment code")
    return {"manifest": str(path), "sha256": sha256_file(path), "artifacts": audit.artifact_count}


def _role_key(raw: Any) -> str:
    if raw is None:
        return ""
    return str(raw).strip().casefold()


def _critical_experiment_roles(annotation: Gate, attestation: Gate) -> dict[str, list[str]]:
    roles: dict[str, list[str]] = {}
    if annotation.passed:
        for annotator in annotation.evidence.get("annotators", []):
            key = _role_key(annotator)
            if key:
                roles.setdefault(key, []).append(f"annotator:{annotator}")
        adjudicator = annotation.evidence.get("adjudicator_id")
        key = _role_key(adjudicator)
        if key:
            roles.setdefault(key, []).append(f"adjudicator:{adjudicator}")
    if attestation.passed:
        for field, label in (
            ("custodian_id", "blind_custodian"),
            ("scorer_id", "trusted_scorer"),
        ):
            value = attestation.evidence.get(field)
            key = _role_key(value)
            if key:
                roles.setdefault(key, []).append(f"{label}:{value}")
    return roles


def _paper_gate(
    root: Path,
    config: dict[str, Any],
    annotation: Gate,
    attestation: Gate,
) -> dict[str, Any]:
    review = config.get("human_review")
    if not isinstance(review, dict):
        raise ValueError("human_review attestation is missing")
    required = ("aaai_policy_checked", "authorship_checked", "claims_checked")
    failed = [field for field in required if review.get(field) is not True]
    reviewer_id = str(review.get("reviewer_id", "")).strip()
    if not reviewer_id:
        failed.append("reviewer_id")
    if not str(review.get("completed_at", "")).strip():
        failed.append("completed_at")
    if failed:
        raise ValueError(f"human paper review is incomplete: {failed}")
    overlapping_roles = _critical_experiment_roles(annotation, attestation).get(
        _role_key(reviewer_id),
        [],
    )
    if overlapping_roles:
        raise ValueError(
            "human paper reviewer must be independent from experiment roles: "
            f"{reviewer_id} overlaps with {sorted(overlapping_roles)}"
        )
    source_fingerprints = paper_source_fingerprints(root)
    claimed_fingerprints = review.get("paper_source_sha256")
    if not isinstance(claimed_fingerprints, dict):
        raise ValueError("human paper review must bind paper_source_sha256 fingerprints")
    expected_keys = set(source_fingerprints)
    claimed_keys = set(map(str, claimed_fingerprints))
    if claimed_keys != expected_keys:
        missing = sorted(expected_keys - claimed_keys)
        extra = sorted(claimed_keys - expected_keys)
        raise ValueError(
            f"human paper review source fingerprint set mismatch: missing={missing}, extra={extra}"
        )
    mismatched = sorted(
        path
        for path, expected in source_fingerprints.items()
        if claimed_fingerprints.get(path) != expected
    )
    if mismatched:
        raise ValueError(f"human paper review is stale for sources: {mismatched}")
    sources = [root / relative for relative in source_fingerprints]
    placeholders = []
    for path in sources:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "PENDING-EMPIRICAL-RUN" in line:
                placeholders.append(f"{path.relative_to(root)}:{line_number}")
    if placeholders:
        raise ValueError(f"paper still contains empirical placeholders: {placeholders}")
    return {
        "reviewer_id": reviewer_id,
        "completed_at": review.get("completed_at"),
        "tex_files": len(sources),
        "paper_source_sha256": source_fingerprints,
    }


def paper_source_fingerprints(root: Path) -> dict[str, str]:
    """Fingerprint every paper source that must be covered by human review."""

    paper_root = root / "paper"
    patterns = ("*.tex", "*.bib", "*.txt", "*.md")
    sources: list[Path] = []
    for pattern in patterns:
        sources.extend(paper_root.glob(pattern))
        sources.extend((paper_root / "aaai27").glob(pattern))
    return {
        str(path.relative_to(root)): sha256_file(path)
        for path in sorted(set(sources), key=lambda candidate: str(candidate.relative_to(root)))
    }


def audit(root: Path, evidence: dict[str, Any]) -> dict[str, Any]:
    if evidence.get("schema_version") != EVIDENCE_SCHEMA:
        raise ValueError(f"evidence file must use {EVIDENCE_SCHEMA}")
    gates: list[Gate] = []
    candidate = _gate("candidate_benchmark", lambda: _candidate_gate(root))
    gates.append(candidate)
    annotation = _gate("human_annotation", lambda: _annotation_gate(root, evidence))
    gates.append(annotation)
    dev_suites = _gate(
        "adjudicated_dev_matrix", lambda: _dev_suites_gate(root, evidence, annotation)
    )
    gates.append(dev_suites)
    bundle = _gate("final_blind_bundle", lambda: _blind_bundle_gate(root, evidence, annotation))
    gates.append(bundle)
    returns = _gate(
        "external_blind_returns",
        lambda: _blind_returns_gate(root, evidence, bundle, dev_suites),
    )
    gates.append(returns)
    attestation = _gate(
        "blind_test_attestation", lambda: _attestation_gate(root, evidence, returns, bundle)
    )
    gates.append(attestation)
    gates.append(
        _gate(
            "trusted_test_scoring",
            lambda: _scored_tests_gate(root, evidence, annotation, returns, attestation),
        )
    )
    gates.append(_gate("release_archive", lambda: _release_gate(root, evidence, dev_suites)))
    gates.append(
        _gate(
            "human_paper_review",
            lambda: _paper_gate(root, evidence, annotation, attestation),
        )
    )
    blockers = [gate.name for gate in gates if not gate.passed]
    return {
        "schema_version": "far-submission-readiness-report-v1",
        "ready": not blockers,
        "gates": [gate.to_dict() for gate in gates],
        "blockers": blockers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument(
        "--print-paper-fingerprints",
        action="store_true",
        help="print the current paper_source_sha256 map for human_review evidence",
    )
    args = parser.parse_args()
    if args.print_paper_fingerprints:
        print(
            json.dumps(
                paper_source_fingerprints(args.project_root.resolve()),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    if args.evidence is None:
        parser.error("--evidence is required unless --print-paper-fingerprints is used")
    try:
        _reject_template_evidence_path(args.evidence, allow_incomplete=args.allow_incomplete)
    except ValueError as exc:
        parser.error(str(exc))
    report = audit(args.project_root.resolve(), _json(args.evidence))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        write_json(args.output, report)
    if not report["ready"] and not args.allow_incomplete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
