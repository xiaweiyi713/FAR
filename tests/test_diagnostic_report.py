from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/single_author_diagnostic_report.md"
MAIN_RESULTS = ROOT / "diagnostics/solo_v1/experiments/artifacts/main_results.csv"
ABLATION_RESULTS = ROOT / "diagnostics/solo_v1/experiments/artifacts/ablation_results.csv"
MACHINE_CONSENSUS = ROOT / "diagnostics/solo_v1/machine_annotation/machine_consensus_report.json"
FEVER_REPORT = ROOT / "diagnostics/fever_binary_v1/report.json"


def _csv_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["method"]: row for row in csv.DictReader(handle)}


def _fmt3(value: str | float) -> str:
    return f"{float(value):.3f}"


def _fmt2_points(value: float) -> str:
    return f"{value * 100:.2f}"


def test_single_author_report_key_metrics_match_tracked_artifacts() -> None:
    text = REPORT.read_text(encoding="utf-8")
    main = _csv_rows(MAIN_RESULTS)
    ablations = _csv_rows(ABLATION_RESULTS)
    fever = json.loads(FEVER_REPORT.read_text(encoding="utf-8"))

    far = main["far"]
    untyped = ablations["minus_typed_conflict"]
    counterrefine = main["counterrefine_style_reproduction"]
    answer_gain = float(far["answer_correctness"]) - float(untyped["answer_correctness"])
    revision_gain = float(far["revision_accuracy"]) - float(untyped["revision_accuracy"])

    assert _fmt3(far["answer_correctness"]) in text
    assert _fmt3(far["counter_evidence_recall"]) in text
    assert _fmt3(counterrefine["counter_evidence_recall"]) in text
    assert f"{_fmt2_points(answer_gain)} points" in text
    assert f"{_fmt2_points(revision_gain)} points" in text

    for method in (
        "far",
        "vanilla",
        "multi_query_rag",
        "reflective_rag",
        "crag_style_reproduction",
        "self_rag_style_reproduction",
        "counterrefine_style_reproduction",
    ):
        row = main[method]
        expected_values = [
            str(row["samples"]),
            _fmt3(row["answer_correctness"]),
            _fmt3(row["typed_conflict_f1"]),
            _fmt3(row["revision_accuracy"]),
            _fmt3(row["counter_evidence_recall"]),
            _fmt3(row["unsupported_claim_rate"]),
        ]
        for value in expected_values:
            assert value in text

    for method in (
        "far",
        "minus_typed_conflict",
        "minus_refutation_query",
        "minus_boundary_query",
        "minus_typed_revision",
    ):
        row = ablations[method]
        expected_values = [
            str(row["samples"]),
            _fmt3(row["answer_correctness"]),
            _fmt3(row["typed_conflict_f1"]),
            _fmt3(row["revision_accuracy"]),
            _fmt3(row["counter_evidence_recall"]),
        ]
        for value in expected_values:
            assert value in text

    heuristic = fever["methods"]["heuristic"]["metrics"]
    nli = fever["methods"]["vera_nli"]["metrics"]
    paired = fever["paired_comparisons"]["vera_nli_vs_heuristic"]
    for metrics in (heuristic, nli):
        for key in ("accuracy", "precision", "recall", "f1"):
            assert _fmt3(metrics[key]) in text
    assert _fmt3(paired["accuracy"]["candidate_minus_baseline"]) in text
    assert _fmt3(paired["mcnemar"]["p_value"]) in text
    assert "12 / 0 / 28 / 60" in text
    assert "16 / 4 / 24 / 56" in text


def test_single_author_report_machine_audit_counts_match_tracked_artifacts() -> None:
    text = REPORT.read_text(encoding="utf-8")
    consensus = json.loads(MACHINE_CONSENSUS.read_text(encoding="utf-8"))
    qwen = consensus["sources"]["qwen25_7b_ollama_machine_weak"]
    rules = consensus["sources"]["rules_weak_supervision_v1"]

    assert str(qwen["non_abstained"]) in text
    assert _fmt3(consensus["observed"]["llm_fallback_rate"]) in text
    assert str(qwen["exact_joint_matches"]) in text
    assert str(rules["non_abstained"]) in text
    assert str(rules["exact_joint_matches"]) in text
    assert str(consensus["dispositions"]["machine_confirmed"]) in text
    assert str(consensus["dispositions"]["machine_disputed"]) in text
    assert "not as human gold" in text
    assert "They are not silently relabeled, filtered, or upgraded to gold." in text


def test_single_author_report_keeps_claim_boundaries_and_source_links() -> None:
    text = REPORT.read_text(encoding="utf-8")

    required_phrases = [
        "This report does not complete the strict AAAI submission path.",
        "Independent human gold labels.",
        "Human inter-annotator agreement.",
        "Externally held blind test scores.",
        "Final multi-model generality.",
        "Publication-ready AAAI empirical claims.",
        "No full FAR pipeline, typed revision, or blind-test protocol is evaluated on FEVER",
        "Do not tune on the frozen FEVER 100-pair diagnostic.",
        "https://fever.ai/dataset/fever.html",
        "https://huggingface.co/datasets/copenlu/fever_gold_evidence",
    ]
    for phrase in required_phrases:
        assert phrase in text


def test_single_author_report_image_links_use_the_immutable_artifact_tag() -> None:
    text = REPORT.read_text(encoding="utf-8")
    image_targets = re.findall(r"!\[[^\]]+\]\(([^)]+)\)", text)

    assert image_targets == [
        (
            "https://raw.githubusercontent.com/xiaweiyi713/FAR/artifacts-v1/diagnostics/"
            "solo_v1/experiments/artifacts/counter_evidence_recall.png"
        ),
        (
            "https://raw.githubusercontent.com/xiaweiyi713/FAR/artifacts-v1/diagnostics/"
            "solo_v1/experiments/artifacts/typed_conflict_breakdown.png"
        ),
        (
            "https://raw.githubusercontent.com/xiaweiyi713/FAR/artifacts-v1/diagnostics/"
            "solo_v1/experiments/artifacts/revision_trace_case.png"
        ),
    ]
