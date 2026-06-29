from __future__ import annotations

from baselines import (
    CRAGStyleBaseline,
    MultiQueryRAG,
    ReflectiveRAG,
    SelfRAGStyleBaseline,
    VanillaRAG,
)
from eval.metrics import PredictionRecord, aggregate_scores, score_sample, soft_f1
from eval.stats import (
    dependency_cluster_bootstrap_ci,
    dependency_cluster_typed_conflict_f1_ci,
    mcnemar_exact,
    paired_bootstrap_comparison,
    paired_typed_conflict_f1_comparison,
    stratified_bootstrap_ci,
    stratified_typed_conflict_f1_ci,
)
from experiments.ablations import build_ablation
from far.adapters import HeuristicConflictDetector, InMemoryRetriever
from far.models import EvidenceDocument


def _retriever() -> InMemoryRetriever:
    return InMemoryRetriever(
        [
            EvidenceDocument("D1", "Revenue was 18 million in the audited report."),
            EvidenceDocument("D2", "Unrelated weather report."),
        ]
    )


def test_all_baselines_run_offline_and_style_reproductions_are_labeled() -> None:
    predictions = [
        VanillaRAG(_retriever()).run("F1", "What was revenue?", "Revenue was 20 million."),
        MultiQueryRAG(_retriever()).run("F1", "What was revenue?", "Revenue was 20 million."),
        ReflectiveRAG(_retriever()).run("F1", "What was revenue?", "Revenue was 20 million."),
        CRAGStyleBaseline(_retriever()).run("F1", "What was revenue?", "Revenue was 20 million."),
        SelfRAGStyleBaseline(_retriever()).run(
            "F1", "What was revenue?", "Revenue was 20 million."
        ),
    ]
    assert {prediction.method for prediction in predictions} == {
        "vanilla_rag",
        "multi_query_rag",
        "reflective_rag",
        "crag_style_reproduction",
        "self_rag_style_reproduction",
    }
    styled = predictions[-2:]
    assert all(prediction.metadata["official_implementation"] is False for prediction in styled)


def test_metrics_cover_revision_conflict_evidence_and_overclaim() -> None:
    sample = {
        "id": "F1",
        "category": "numerical_conflict",
        "split": "dev",
        "initial_answer": "Revenue was 20 million.",
        "gold_evidence": [{"doc_id": "D1"}],
        "counter_evidence": [{"doc_id": "D1"}],
        "conflict_type": "numerical",
        "expected_revision": {
            "action": "replace_numerical",
            "revised_answer": "Revenue was 18 million.",
        },
        "source_metadata": {"dependency_group": "D1"},
    }
    prediction = PredictionRecord(
        sample_id="F1",
        answer="Revenue was 18 million.",
        evidence_ids=("D1",),
        predicted_conflict_types=("numerical",),
        revision_action="replace_numerical",
        method="far",
    )
    row = score_sample(sample, prediction)
    assert row["answer_correctness"] == 1.0
    assert row["revision_accuracy"] == 1.0
    assert row["overclaim_reduction"] == 1.0
    assert aggregate_scores([row])["metrics"]["typed_conflict_f1"] == 1.0
    assert soft_f1("18 million", "Revenue was 18 million.") > 0.5


def test_causal_overclaim_reduction_requires_causal_marker_removal() -> None:
    sample = {
        "id": "F2",
        "category": "causal_overclaim",
        "split": "dev",
        "initial_answer": "这一结果完全由该因素导致",
        "gold_evidence": [{"doc_id": "D1"}],
        "counter_evidence": [{"doc_id": "D1"}],
        "conflict_type": "causal",
        "expected_revision": {
            "action": "downgrade_causal_to_correlation",
            "revised_answer": "这一结果与该因素相关，但不能确认因果关系",
        },
        "source_metadata": {"dependency_group": "D1"},
    }
    prediction = PredictionRecord(
        sample_id="F2",
        answer="这一结果与该因素相关，但现有证据不足以确认因果关系",
        evidence_ids=("D1",),
        predicted_conflict_types=("causal",),
        revision_action="downgrade_causal_to_correlation",
        method="far",
    )
    assert score_sample(sample, prediction)["overclaim_reduction"] == 1.0


def test_statistics_are_deterministic_and_paired() -> None:
    baseline = [
        {"sample_id": f"F{i}", "category": "a" if i < 3 else "b", "score": 0.0} for i in range(6)
    ]
    candidate = [{**row, "score": 1.0} for row in baseline]
    first = stratified_bootstrap_ci(candidate, "score", resamples=100, seed=7)
    second = stratified_bootstrap_ci(candidate, "score", resamples=100, seed=7)
    assert first == second
    comparison = paired_bootstrap_comparison(
        baseline,
        candidate,
        "score",
        resamples=100,
        seed=7,
    )
    assert comparison["candidate_minus_baseline"] == 1.0
    assert comparison["probability_candidate_better"] == 1.0
    lower_is_better = paired_bootstrap_comparison(
        baseline,
        candidate,
        "score",
        resamples=100,
        seed=7,
        higher_is_better=False,
    )
    assert lower_is_better["probability_candidate_better"] == 0.0
    exact = mcnemar_exact([False] * 6, [True] * 6)
    assert exact["candidate_only"] == 6
    assert exact["p_value"] == 0.03125
    clustered = dependency_cluster_bootstrap_ci(
        [
            {**row, "dependency_group": "g1" if index < 3 else "g2"}
            for index, row in enumerate(candidate)
        ],
        "score",
        resamples=50,
        seed=7,
    )
    assert clustered["clusters"] == 2


def test_typed_conflict_f1_is_recomputed_within_resamples() -> None:
    baseline = [
        {
            "sample_id": f"F{index}",
            "category": "a" if index < 2 else "b",
            "dependency_group": f"g{index // 2}",
            "typed_conflict_correct": 0.0,
            "predicted_conflict_count": 1,
        }
        for index in range(4)
    ]
    candidate = [{**row, "typed_conflict_correct": 1.0} for row in baseline]
    interval = stratified_typed_conflict_f1_ci(candidate, resamples=30, seed=9)
    assert interval["estimate"] == 1.0
    paired = paired_typed_conflict_f1_comparison(
        baseline,
        candidate,
        resamples=30,
        seed=9,
    )
    assert paired["candidate_minus_baseline"] == 1.0
    clustered = dependency_cluster_typed_conflict_f1_ci(
        candidate,
        resamples=30,
        seed=9,
    )
    assert clustered["estimate"] == 1.0
    assert clustered["clusters"] == 2


def test_ablation_removes_query_families_and_typed_control() -> None:
    detector = HeuristicConflictDetector(allow_oracle_metadata=True)
    document = EvidenceDocument(
        "D1",
        "Revenue was 18 million.",
        metadata={
            "conflict_type": "numerical",
            "refutes_claim": "C1",
            "suggested_revision": "Revenue was 18 million.",
        },
    )
    no_refute = build_ablation(
        "minus_refutation_query",
        InMemoryRetriever([document]),
        conflict_detector=detector,
    ).run("What was revenue?", "Revenue was 20 million.")
    assert {item.query.kind.value for item in no_refute.retrieval_trace} == {
        "support",
        "boundary",
    }
    untyped = build_ablation(
        "minus_typed_conflict",
        InMemoryRetriever([document]),
        conflict_detector=detector,
    ).run("What was revenue?", "Revenue was 20 million.")
    assert untyped.conflicts["C1"][0].conflict_type.value == "counter_evidence"
