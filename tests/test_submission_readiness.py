from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from bench.build.build_blind_bundle import build as build_blind_bundle
from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from experiments.run_suite import run_suite
from experiments.score_blind_return import score
from experiments.submission_readiness import audit

ROOT = Path(__file__).resolve().parents[1]


def _adjudicated_fixture(path: Path) -> None:
    shutil.copytree(ROOT / "bench", path)
    rows = read_jsonl(path / "falsirag_bench.jsonl")
    for row in rows:
        row["annotation_status"] = "adjudicated"
    write_jsonl(path / "falsirag_bench.jsonl", rows)
    for split in ("train", "dev"):
        write_jsonl(
            path / "splits" / f"{split}.jsonl", (row for row in rows if row["split"] == split)
        )
    report = {
        "schema_version": "falsirag-annotation-report-v1",
        "samples": len(rows),
        "annotators": ["alice", "bob"],
        "pairwise": [],
        "mean_kappas": {
            "conflict_presence_kappa": 1.0,
            "conflict_type_kappa": 1.0,
            "revision_action_kappa": 1.0,
        },
        "minimum_required_kappa": 0.6,
        "agreement_gate_passed": True,
        "adjudicated": True,
    }
    write_json(path / "annotation_report.json", report)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    manifest["annotation"] = {
        "status": "adjudicated",
        "machine_seed_is_gold": False,
        "required_annotators": 2,
        "required_adjudication": True,
        "report": "annotation_report.json",
        "agreement_gate_passed": True,
        "mean_kappas": report["mean_kappas"],
    }
    manifest["fingerprints"] = {
        "benchmark_sha256": sha256_file(path / "falsirag_bench.jsonl"),
        "corpus_sha256": sha256_file(path / "corpus.jsonl"),
        "split_manifest_sha256": sha256_file(path / "split_manifest.json"),
    }
    write_json(path / "manifest.json", manifest)


def _freeze_run_identities(suite: Path, commit: str, config_sha256: str) -> None:
    suite_manifest = json.loads((suite / "suite_manifest.json").read_text(encoding="utf-8"))
    for label, summary in suite_manifest["run_manifests"].items():
        run_dir = (
            suite / "runs" / "baselines" / label
            if label
            in {
                "vanilla_rag",
                "multi_query_rag",
                "reflective_rag",
                "crag_style_reproduction",
                "self_rag_style_reproduction",
                "counterrefine_style_reproduction",
            }
            else suite / "runs" / label
        )
        identity = json.loads((run_dir / "run_identity.json").read_text(encoding="utf-8"))
        identity["source_revision"] = {"git_commit": commit, "git_dirty": False}
        identity["config_sha256"] = config_sha256
        stable = {
            key: value
            for key, value in identity.items()
            if key not in {"run_signature", "created_at", "environment"}
        }
        signature = hashlib.sha256(
            json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        identity["run_signature"] = signature
        write_json(run_dir / "run_identity.json", identity)
        run_manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
        run_manifest["run_signature"] = signature
        write_json(run_dir / "run_manifest.json", run_manifest)
        summary["run_signature"] = signature
    suite_manifest["config_sha256"] = config_sha256
    write_json(suite / "suite_manifest.json", suite_manifest)


def test_submission_audit_fails_closed_on_template() -> None:
    evidence = json.loads((ROOT / "submission/evidence.template.json").read_text(encoding="utf-8"))
    report = audit(ROOT, evidence)
    assert report["ready"] is False
    assert report["gates"][0]["name"] == "candidate_benchmark"
    assert report["gates"][0]["passed"] is True
    assert "human_annotation" in report["blockers"]
    assert "trusted_test_scoring" in report["blockers"]


def test_external_blind_return_can_be_scored_with_bound_attestation(tmp_path: Path) -> None:
    data_dir = tmp_path / "adjudicated"
    _adjudicated_fixture(data_dir)
    bundle = tmp_path / "bundle"
    build_blind_bundle(data_dir, bundle)
    returned = tmp_path / "returned"
    run_suite(
        ROOT / "experiments/configs/offline_smoke.yaml",
        bundle,
        returned,
        split="test",
        allow_test=True,
        resamples=10,
    )
    commit = "a" * 40
    model_id = "deepseek_v4_flash"
    _freeze_run_identities(
        returned, commit, sha256_file(ROOT / "experiments/configs/deepseek.yaml")
    )
    attestation = {
        "schema_version": "far-blind-test-attestation-v1",
        "custodian_id": "external-custodian",
        "scorer_id": "trusted-scorer",
        "completed_at": "2026-07-02T12:00:00Z",
        "frozen_commit": commit,
        "bundle_manifest_sha256": sha256_file(bundle / "blind_bundle_manifest.json"),
        "return_manifest_sha256": {model_id: sha256_file(returned / "suite_manifest.json")},
        "one_shot": True,
        "externally_held": True,
        "gold_loaded_by_custodian": False,
        "all_failures_reported": True,
    }
    attestation_path = tmp_path / "attestation.json"
    write_json(attestation_path, attestation)
    output = tmp_path / "scored"
    manifest = score(
        data_dir,
        bundle,
        returned,
        attestation_path,
        output,
        model_id=model_id,
        resamples=10,
    )
    assert manifest["publication_ready"] is True
    assert set(manifest["methods"]) == {
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
    far_report = json.loads((output / "evaluations/far/report.json").read_text(encoding="utf-8"))
    assert far_report["publication_ready"] is True
    assert far_report["publication"]["phase"] == "test"
    assert far_report["comparison"]["baseline_method"] == "vanilla_rag"
