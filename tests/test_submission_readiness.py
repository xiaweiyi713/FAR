from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bench.annotations import build_annotation_packet, compile_annotations
from bench.build.build_blind_bundle import build as build_blind_bundle
from bench.build.common import sha256_file, write_json
from experiments.run_suite import run_suite
from experiments.score_blind_return import score
from experiments.submission_readiness import audit, paper_source_fingerprints

ROOT = Path(__file__).resolve().parents[1]


def _adjudicated_fixture(path: Path) -> None:
    packet = path.parent / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    samples = {
        row["id"]: row
        for row in map(
            json.loads,
            (ROOT / "bench/falsirag_bench.jsonl").read_text().splitlines(),
        )
    }
    for filename in ("annotations_alice.jsonl", "annotations_bob.jsonl"):
        rows = [json.loads(line) for line in (packet / filename).read_text().splitlines()]
        for row in rows:
            sample = samples[row["sample_id"]]
            row["annotation"] = {
                "conflict_present": True,
                "conflict_type": sample["conflict_type"],
                "revision_action": sample["expected_revision"]["action"],
                "revised_answer_acceptable": True,
                "rationale": "Test-only completed annotation.",
            }
        (packet / filename).write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
    adjudications = [
        json.loads(line) for line in (packet / "adjudications.jsonl").read_text().splitlines()
    ]
    for row in adjudications:
        sample = samples[row["sample_id"]]
        row["adjudicator_id"] = "adjudicator_1"
        row["gold_annotation"] = {
            "conflict_present": True,
            "conflict_type": sample["conflict_type"],
            "revision_action": sample["expected_revision"]["action"],
            "revised_answer_acceptable": True,
            "revised_answer": sample["expected_revision"]["revised_answer"],
            "rationale": "Test-only adjudication.",
        }
    (packet / "adjudications.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in adjudications),
        encoding="utf-8",
    )
    compile_annotations(ROOT / "bench", packet, path)


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


def test_paper_source_fingerprints_cover_submission_sources() -> None:
    fingerprints = paper_source_fingerprints(ROOT)
    assert "paper/main.tex" in fingerprints
    assert "paper/supplement.tex" in fingerprints
    assert "paper/references.bib" in fingerprints
    assert "paper/aaai27/ReproducibilityChecklist.tex" in fingerprints
    assert all(len(value) == 64 for value in fingerprints.values())


def test_paper_gate_rejects_stale_human_review_source_hashes() -> None:
    evidence = json.loads((ROOT / "submission/evidence.template.json").read_text(encoding="utf-8"))
    fingerprints = paper_source_fingerprints(ROOT)
    fingerprints["paper/main.tex"] = "0" * 64
    evidence["human_review"] = {
        "reviewer_id": "paper-reviewer",
        "completed_at": "2026-07-02T12:00:00Z",
        "aaai_policy_checked": True,
        "authorship_checked": True,
        "claims_checked": True,
        "paper_source_sha256": fingerprints,
    }
    report = audit(ROOT, evidence)
    paper_gate = next(gate for gate in report["gates"] if gate["name"] == "human_paper_review")
    assert paper_gate["passed"] is False
    assert "stale" in paper_gate["detail"]


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
    assert manifest["annotation_evidence_manifest_sha256"] == sha256_file(
        data_dir / "annotation_evidence/evidence_manifest.json"
    )
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
    artifact_manifest = json.loads(
        (output / "artifacts/artifact_manifest.json").read_text(encoding="utf-8")
    )
    assert artifact_manifest["publication_ready"] is True
    assert artifact_manifest["test_only"] is True
    assert artifact_manifest["scored_splits"] == ["test"]
    assert artifact_manifest["strict_requirements"] == {
        "publication_ready": True,
        "test_only": True,
    }
    assert artifact_manifest["reports"] == manifest["reports"]
    assert artifact_manifest["benchmark_sha256"] == manifest["benchmark_sha256"]
