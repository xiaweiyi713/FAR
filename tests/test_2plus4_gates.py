from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.build.common import write_json, write_jsonl
from experiments.evidence_2plus4 import _files, verify_jury_release
from experiments.jury_rescore import _prediction_source
from experiments.model_matrix import _fallback_rate, build_matrix
from experiments.one_shot import prepare_intent
from experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256


def _family_bundle(root: Path, family: str, gain: float = 0.1) -> Path:
    directory = root / family
    evaluation = directory / "minus_typed_conflict" / "evaluation"
    evaluation.mkdir(parents=True)
    write_json(
        evaluation / "report.json",
        {
            "comparison": {
                "metrics": {
                    "answer_correctness": {
                        "candidate_minus_baseline": -gain,
                        "lower": -gain - 0.02,
                        "upper": -gain + 0.02,
                    },
                    "typed_conflict_f1": {
                        "candidate_minus_baseline": -0.2,
                        "lower": -0.25,
                        "upper": -0.15,
                    },
                }
            }
        },
    )
    write_json(
        directory / "matrix_family_manifest.json",
        {
            "schema_version": "far-jury-family-rescore-v1",
            "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
            "family": family,
            "split": "dev",
            "model_identity": {"model": f"{family}-model"},
            "structured_fallback": {
                "samples": 60,
                "fallback_samples": 0,
                "fallback_rate": 0.0,
                "fallback_sample_ids": [],
            },
            "jury_gold": True,
            "publication_gold": False,
        },
    )
    return directory


def test_model_matrix_requires_three_included_families_and_same_direction(
    tmp_path: Path,
) -> None:
    suites = {family: _family_bundle(tmp_path, family) for family in ("qwen", "mistral", "google")}
    report = build_matrix(suites, tmp_path / "matrix.json")
    assert report["minimum_matrix_passed"] is True
    assert report["three_family_claim_ready"] is True
    assert report["typed_answer_gain_same_direction"] is True


def test_model_matrix_exposes_direction_failure(tmp_path: Path) -> None:
    suites = {
        "qwen": _family_bundle(tmp_path, "qwen"),
        "mistral": _family_bundle(tmp_path, "mistral", gain=-0.05),
    }
    report = build_matrix(suites, tmp_path / "matrix.json")
    assert report["minimum_matrix_passed"] is True
    assert report["three_family_claim_ready"] is False
    assert report["typed_answer_gain_same_direction"] is False


def test_trace_fallback_rate_uses_frozen_markers(tmp_path: Path) -> None:
    predictions = tmp_path / "predictions.jsonl"
    write_jsonl(
        predictions,
        [
            {
                "sample_id": "S1",
                "metadata": {
                    "retrieval_trace": [{"query": {"tactic": "llm:entity identity"}}],
                    "revision_trace": [
                        {
                            "changed": True,
                            "rationale": "typed policy realized by the configured LLM",
                        }
                    ],
                },
            },
            {
                "sample_id": "S2",
                "metadata": {
                    "retrieval_trace": [{"query": {"tactic": "entity identity"}}],
                    "revision_trace": [],
                },
            },
        ],
    )
    report = _fallback_rate(predictions)
    assert report["fallback_rate"] == 0.5
    assert report["fallback_sample_ids"] == ["S2"]


def test_jury_rescore_maps_all_suite_layout_variants(tmp_path: Path) -> None:
    assert _prediction_source(tmp_path, "vanilla") == (
        tmp_path / "runs/baselines/vanilla_rag/predictions.jsonl"
    )
    assert _prediction_source(tmp_path, "crag_style_reproduction") == (
        tmp_path / "runs/baselines/crag_style_reproduction/predictions.jsonl"
    )
    assert _prediction_source(tmp_path, "minus_typed_conflict") == (
        tmp_path / "runs/minus_typed_conflict/predictions.jsonl"
    )


def test_jury_release_verifier_detects_fingerprint_tampering(tmp_path: Path) -> None:
    write_json(
        tmp_path / "consensus/jury_consensus_report.json",
        {"gate_k_passed": True, "zero_fallbacks": True},
    )
    write_json(
        tmp_path / "labels/manifest.json",
        {
            "gate_s_passed": True,
            "jury_gold": True,
            "publication_gold": False,
            "human_iaa": False,
        },
    )
    write_json(
        tmp_path / "qwen_sensitivity/sensitivity_report.json",
        {
            "schema_version": "far-jury-label-sensitivity-v1",
            "publication_gold": False,
            "human_iaa": False,
        },
    )
    write_json(tmp_path / "model_matrix.json", {"three_family_claim_ready": True})
    write_json(
        tmp_path / "bundle_manifest.json",
        {
            "schema_version": "far-jury-evidence-release-v1",
            "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
            "publication_gold": False,
            "human_iaa": False,
            "files": _files(tmp_path),
        },
    )
    assert verify_jury_release(tmp_path)["valid"] is True

    (tmp_path / "model_matrix.json").write_text("{}\n", encoding="utf-8")
    audit = verify_jury_release(tmp_path)
    assert audit["valid"] is False
    assert "fingerprints differ" in " ".join(audit["errors"])


def test_one_shot_intent_binds_clean_commit_and_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    benchmark = tmp_path / "test_inputs.jsonl"
    manifest = tmp_path / "manifest.json"
    benchmark.write_text("{}\n", encoding="utf-8")
    manifest.write_text("{}\n", encoding="utf-8")

    def fake_git(*args: str) -> str:
        if args[:2] == ("status", "--porcelain"):
            return ""
        if args == ("rev-parse", "HEAD"):
            return "a" * 40
        raise AssertionError(args)

    monkeypatch.setattr("experiments.one_shot._git", fake_git)
    output = tmp_path / "intent.json"
    intent = prepare_intent("ramdocs", benchmark, manifest, ["far", "baseline"], output)
    assert intent["one_shot"] is True
    assert intent["externally_held"] is False
    assert intent["expected_samples"] == 1
    assert intent["prepared_from_git_commit"] == "a" * 40
    assert json.loads(output.read_text(encoding="utf-8"))["intent_id"] == intent["intent_id"]
