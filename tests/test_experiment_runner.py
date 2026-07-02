from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bench.build.build_blind_bundle import build as build_blind_bundle
from bench.build.common import sha256_file
from eval.run_eval import evaluate
from experiments.build_artifacts import _load_plotting_backend
from experiments.run_far import _primary_trace, run
from experiments.run_suite import run_suite
from experiments.runner import (
    ROOT,
    _ollama_model_identity,
    load_benchmark,
    load_config,
    select_samples,
)
from experiments.validate_results import validate_result_bundle
from far.evidence_types import EvidenceType
from far.revision import RevisionAction, RevisionTrace


def test_sample_limit_is_category_balanced_and_test_is_guarded() -> None:
    samples, documents = load_benchmark(ROOT / "bench")
    assert any(document.metadata.get("entities") for document in documents)
    selected = select_samples(samples, "dev", limit=10, allow_test=False)
    assert {row["category"] for row in selected} == {
        "temporal_shift",
        "numerical_conflict",
        "entity_confusion",
        "causal_overclaim",
        "multi_source_conflict",
    }
    with pytest.raises(ValueError, match="allow-test"):
        select_samples(samples, "test", limit=1, allow_test=False)


def test_formal_configs_pin_one_shared_retrieval_and_conflict_stack() -> None:
    configs = [
        load_config(ROOT / f"experiments/configs/{name}.yaml")
        for name in (
            "deepseek",
            "qwen_plus",
            "qwen_open",
            "formal_stack_smoke",
            "formal_stack_cuda_smoke",
        )
    ]
    assert all(config["conflict_graph"] == configs[0]["conflict_graph"] for config in configs)
    retrieval = configs[0]["retrieval"]
    semantic_retrievals = [json.loads(json.dumps(config["retrieval"])) for config in configs]
    for stack in semantic_retrievals:
        stack["dense"].pop("device")
        stack["rerank"].pop("device")
    assert all(stack == semantic_retrievals[0] for stack in semantic_retrievals)
    conflict = configs[0]["conflict_graph"]
    assert retrieval["backend"] == "vera_hybrid"
    assert retrieval["allow_dense_fallback"] is False
    assert retrieval["dense"]["local_files_only"] is True
    assert retrieval["dense"]["device"] == "cuda"
    assert configs[1]["retrieval"]["dense"]["device"] == "cuda"
    assert configs[2]["retrieval"]["dense"]["device"] == "cpu"
    assert configs[3]["retrieval"]["dense"]["device"] == "cpu"
    assert configs[4]["retrieval"]["dense"]["device"] == "cuda"
    assert len(retrieval["dense"]["revision"]) == 40
    assert retrieval["rerank"]["local_files_only"] is True
    assert retrieval["rerank"]["device"] == "cuda"
    assert configs[1]["retrieval"]["rerank"]["device"] == "cuda"
    assert configs[2]["retrieval"]["rerank"]["device"] == "cpu"
    assert configs[3]["retrieval"]["rerank"]["device"] == "cpu"
    assert configs[4]["retrieval"]["rerank"]["device"] == "cuda"
    assert len(retrieval["rerank"]["revision"]) == 40
    assert configs[2]["llm"]["think"] is False
    assert configs[2]["llm"]["unload_after_sample"] is True
    assert conflict["enable_nli"] is True
    assert conflict["require_nli"] is True
    assert conflict["nli_local_files_only"] is True
    assert conflict["enable_nli_candidate_filter"] is True
    assert len(conflict["nli_revision"]) == 40
    assert conflict["enable_source_reliability_conflict"] is True
    assert conflict["enable_scope_conflict"] is True
    assert conflict["enable_granularity_conflict"] is True
    assert conflict["enable_entity_lexicon_conflict"] is True
    assert conflict["entity_lexicon_similarity"] == 0.55


def test_ollama_identity_resolves_the_tag_to_a_digest() -> None:
    response = MagicMock()
    response.read.return_value = json.dumps(
        {
            "models": [
                {
                    "name": "qwen3.5:9b",
                    "digest": "sha256:fixed-model",
                    "size": 123,
                    "modified_at": "2026-06-01T00:00:00Z",
                    "details": {"parameter_size": "9B", "quantization_level": "Q4_K_M"},
                }
            ]
        }
    ).encode()
    response.__enter__.return_value = response
    with patch("experiments.runner.urlopen", return_value=response):
        identity = _ollama_model_identity("http://localhost:11434", "qwen3.5:9b")
    assert identity["digest"] == "sha256:fixed-model"
    assert identity["details"]["quantization_level"] == "Q4_K_M"


def test_ollama_identity_fails_closed_for_a_missing_model() -> None:
    response = MagicMock()
    response.read.return_value = b'{"models": []}'
    response.__enter__.return_value = response
    with (
        patch("experiments.runner.urlopen", return_value=response),
        pytest.raises(RuntimeError, match="is not installed"),
    ):
        _ollama_model_identity("http://localhost:11434", "qwen3.5:9b")


def test_primary_trace_uses_confidence_then_specific_action_tiebreak() -> None:
    numeric = RevisionTrace(
        claim_id="C1",
        before="Revenue was 20 million",
        after="The reported value conflicts with retrieved measurements: Revenue was 20 million",
        action=RevisionAction.REPLACE_NUMERICAL,
        conflict_types=(EvidenceType.NUMERICAL,),
        evidence_ids=("E1",),
        rationale="values differ",
        confidence=0.8,
    )
    source = RevisionTrace(
        claim_id="C2",
        before="A low reliability claim",
        after=(
            "Lower-reliability sources disagree with authoritative evidence: "
            "A low reliability claim"
        ),
        action=RevisionAction.PREFER_RELIABLE_SOURCE,
        conflict_types=(EvidenceType.SOURCE_RELIABILITY, EvidenceType.NUMERICAL),
        evidence_ids=("E2",),
        rationale="low source conflicts with official evidence",
        confidence=0.9,
    )
    causal = RevisionTrace(
        claim_id="C3",
        before="这一结果完全由该因素导致",
        after="这一结果与该因素相关，但现有证据不足以确认因果关系",
        action=RevisionAction.DOWNGRADE_CAUSAL,
        conflict_types=(EvidenceType.CAUSAL,),
        evidence_ids=("E3",),
        rationale="association only",
        confidence=0.9,
    )
    assert _primary_trace((numeric, source)) is source
    assert _primary_trace((source, causal)) is source


def test_runner_resumes_without_duplicates_and_evaluation_is_bound(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config = ROOT / "experiments/configs/offline_smoke.yaml"
    first = run(config, ROOT / "bench", run_dir, limit=5)
    second = run(config, ROOT / "bench", run_dir, limit=5)
    assert first["predictions_sha256"] == second["predictions_sha256"]
    assert first["completed"] == 5
    prediction = json.loads(
        (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert set(prediction["metadata"]["primary_conflict_types"]) <= set(
        prediction["predicted_conflict_types"]
    )
    identity = json.loads((run_dir / "run_identity.json").read_text(encoding="utf-8"))
    assert set(identity["source_revision"]) == {"git_commit", "git_dirty"}
    assert {
        "faiss-cpu",
        "huggingface-hub",
        "sentence-transformers",
        "torch",
        "transformers",
        "verarag",
    } <= set(identity["environment"]["packages"])
    evaluation_dir = tmp_path / "evaluation"
    evaluation = evaluate(
        ROOT / "bench/falsirag_bench.jsonl",
        run_dir / "predictions.jsonl",
        evaluation_dir,
        resamples=20,
    )
    assert evaluation["publication_ready"] is False
    assert evaluation["publication"]["annotation_status_counts"] == {"machine_seeded": 5}
    assert (
        "benchmark annotation/adjudication gate is not ready"
        in evaluation["publication"]["reasons"]
    )
    assert validate_result_bundle(run_dir, evaluation_dir)["valid"] is True

    identity_path = run_dir / "run_identity.json"
    original_identity = identity_path.read_text(encoding="utf-8")
    tampered_identity = json.loads(original_identity)
    tampered_identity["source_revision"] = {"git_commit": "0" * 40, "git_dirty": False}
    identity_path.write_text(json.dumps(tampered_identity), encoding="utf-8")
    assert (
        "run identity signature is invalid"
        in validate_result_bundle(run_dir, evaluation_dir)["errors"]
    )
    identity_path.write_text(original_identity, encoding="utf-8")

    prediction_rows = [
        json.loads(line)
        for line in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    prediction_rows[0]["answer"] += " Thinking Process: hidden reasoning"
    (run_dir / "predictions.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in prediction_rows),
        encoding="utf-8",
    )
    invalid = validate_result_bundle(run_dir, evaluation_dir)
    assert any("leaked model reasoning" in error for error in invalid["errors"])


def test_suite_runs_far_baseline_ablation_and_artifacts(tmp_path: Path) -> None:
    manifest = run_suite(
        ROOT / "experiments/configs/offline_smoke.yaml",
        ROOT / "bench",
        tmp_path / "suite",
        limit=5,
        baselines=("vanilla_rag",),
        ablations=("minus_typed_conflict",),
        resamples=20,
    )
    assert manifest["diagnostic_only"] is True
    assert manifest["methods"] == ["far", "minus_typed_conflict", "vanilla"]
    assert (tmp_path / "suite" / "suite_manifest.json").exists()
    assert (tmp_path / "suite" / "artifacts" / "main_results.csv").exists()
    assert (tmp_path / "suite" / "artifacts" / "ablation_results.csv").exists()
    artifact_manifest = json.loads(
        (tmp_path / "suite/artifacts/artifact_manifest.json").read_text(encoding="utf-8")
    )
    assert artifact_manifest["publication_ready"] is False
    far_report = json.loads(
        (tmp_path / "suite/evaluations/far/report.json").read_text(encoding="utf-8")
    )
    ablation_report = json.loads(
        (tmp_path / "suite/evaluations/minus_typed_conflict/report.json").read_text(
            encoding="utf-8"
        )
    )
    assert far_report["comparison"]["baseline_method"] == "vanilla_rag"
    assert far_report["comparison"]["candidate_method"] == "far"
    assert ablation_report["comparison"]["baseline_method"] == "far"
    assert ablation_report["comparison"]["candidate_method"] == "far_minus_typed_conflict"
    assert "typed_conflict_f1" in ablation_report["comparison"]["metrics"]
    assert "typed_conflict_f1" in ablation_report["confidence_intervals"]

    far_predictions = tmp_path / "suite/runs/far/predictions.jsonl"
    prediction_fingerprint = sha256_file(far_predictions)
    rebuilt = run_suite(
        ROOT / "experiments/configs/offline_smoke.yaml",
        ROOT / "bench",
        tmp_path / "suite",
        limit=5,
        baselines=("vanilla_rag",),
        ablations=("minus_typed_conflict",),
        resamples=20,
        reports_only=True,
    )
    assert rebuilt["reports_only"] is True
    assert rebuilt["diagnostic_only"] is True
    assert sha256_file(far_predictions) == prediction_fingerprint


def test_blind_test_suite_runs_without_loading_or_scoring_gold(tmp_path: Path) -> None:
    data_dir = tmp_path / "blind-data"
    build_blind_bundle(ROOT / "bench", data_dir)
    output_dir = tmp_path / "blind-suite"
    manifest = run_suite(
        ROOT / "experiments/configs/offline_smoke.yaml",
        data_dir,
        output_dir,
        split="test",
        limit=5,
        allow_test=True,
        baselines=("vanilla_rag",),
        ablations=(),
        resamples=20,
    )
    assert manifest["schema_version"] == "far-blind-suite-manifest-v1"
    assert manifest["unscored"] is True
    assert manifest["gold_loaded"] is False
    assert manifest["methods"] == ["far", "vanilla_rag"]
    assert not (data_dir / "falsirag_bench.jsonl").exists()
    assert not (output_dir / "evaluations").exists()
    assert not (output_dir / "artifacts").exists()
    identity = json.loads((output_dir / "runs/far/run_identity.json").read_text(encoding="utf-8"))
    assert identity["benchmark_input"] == "splits/test_inputs.jsonl"
    assert identity["schema_version"] == "far-run-signature-v2"


def test_artifact_builder_explains_missing_eval_extra() -> None:
    with (
        patch(
            "experiments.build_artifacts.importlib.import_module",
            side_effect=ModuleNotFoundError("No module named 'matplotlib'"),
        ),
        pytest.raises(RuntimeError, match="optional eval dependencies"),
    ):
        _load_plotting_backend()
