from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.build.common import read_jsonl, sha256_file, write_jsonl
from bench.build.ramdocs import UPSTREAM_SHA256, build_ramdocs, verify_ramdocs
from eval.ramdocs import (
    compare_ramdocs,
    evaluate_ramdocs,
    score_ramdocs_answer,
    unsupported_sentence_rate,
)


def _source(path: Path) -> None:
    rows = []
    for index in range(500):
        rows.append(
            {
                "question": f"Question {index}?",
                "documents": [
                    {
                        "text": f"Correct context {index}",
                        "type": "correct",
                        "answer": f"Gold {index}",
                    },
                    {
                        "text": f"Wrong context {index}",
                        "type": "misinfo",
                        "answer": f"Wrong {index}",
                    },
                ],
                "gold_answers": [f"Gold {index}"],
                "wrong_answers": [f"Wrong {index}"],
                "disambig_entity": [f"Entity {index}"],
            }
        )
    write_jsonl(path, rows)


def test_ramdocs_strict_match_requires_all_gold_and_no_wrong() -> None:
    assert score_ramdocs_answer("The Alpha; BETA.", ["alpha", "beta"], ["gamma"])[
        "ramdocs_exact_match"
    ] == 1.0
    assert score_ramdocs_answer("alpha", ["alpha", "beta"], ["gamma"])[
        "ramdocs_exact_match"
    ] == 0.0
    assert score_ramdocs_answer("alpha beta gamma", ["alpha", "beta"], ["gamma"])[
        "ramdocs_exact_match"
    ] == 0.0
    assert score_ramdocs_answer("notable", ["notable"], ["no"])["wrong_answer_exclusion"] == 1.0
    assert unsupported_sentence_rate("alpha beta", ["alpha beta gamma"]) == 0.0
    assert unsupported_sentence_rate("unrelated words", ["alpha beta gamma"]) == 1.0


def test_ramdocs_builder_is_pinned_and_hides_test_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.jsonl"
    _source(source)
    monkeypatch.setattr("bench.build.ramdocs.UPSTREAM_SHA256", sha256_file(source))
    output = tmp_path / "ramdocs"
    manifest = build_ramdocs(output, source_file=source)
    assert manifest["counts"]["dev"] == 350
    assert manifest["counts"]["test"] == 150
    assert manifest["publication_gold"] is False
    assert all(
        set(row) == {"id", "question", "split"}
        for row in read_jsonl(output / "splits" / "test_inputs.jsonl")
    )
    monkeypatch.setattr("bench.build.ramdocs.UPSTREAM_SHA256", manifest["upstream_sha256"])
    assert verify_ramdocs(output)["valid"] is True


def test_ramdocs_builder_rejects_wrong_upstream_hash(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    _source(source)
    assert sha256_file(source) != UPSTREAM_SHA256
    with pytest.raises(ValueError, match="fingerprint"):
        build_ramdocs(tmp_path / "output", source_file=source)


def test_ramdocs_evaluation_and_paired_gate(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.jsonl"
    corpus = tmp_path / "corpus.jsonl"
    write_jsonl(
        corpus,
        [
            {
                "doc_id": "D1",
                "content": "alpha",
                "metadata": {"document_type": "correct"},
            },
            {
                "doc_id": "D2",
                "content": "beta",
                "metadata": {"document_type": "correct"},
            },
        ],
    )
    write_jsonl(
        tasks,
        [
            {
                "id": "R1",
                "split": "dev",
                "category": "ambiguity_misinformation",
                "gold_answers": ["alpha"],
                "wrong_answers": ["omega"],
                "document_ids": ["D1"],
            },
            {
                "id": "R2",
                "split": "dev",
                "category": "ambiguity_noise",
                "gold_answers": ["beta"],
                "wrong_answers": [],
                "document_ids": ["D2"],
            },
        ],
    )
    baseline_predictions = tmp_path / "baseline.jsonl"
    candidate_predictions = tmp_path / "candidate.jsonl"
    write_jsonl(
        baseline_predictions,
        [
            {"sample_id": "R1", "method": "baseline", "answer": "wrong"},
            {"sample_id": "R2", "method": "baseline", "answer": "wrong"},
        ],
    )
    write_jsonl(
        candidate_predictions,
        [
            {"sample_id": "R1", "method": "far", "answer": "alpha"},
            {"sample_id": "R2", "method": "far", "answer": "beta"},
        ],
    )
    baseline_report = evaluate_ramdocs(tasks, baseline_predictions, corpus, tmp_path / "base")
    candidate_report = evaluate_ramdocs(
        tasks, candidate_predictions, corpus, tmp_path / "candidate"
    )
    assert baseline_report["metrics"]["ramdocs_exact_match"] == 0.0
    assert candidate_report["metrics"]["ramdocs_exact_match"] == 1.0
    comparison = compare_ramdocs(
        tmp_path / "base" / "scores.jsonl",
        tmp_path / "candidate" / "scores.jsonl",
        tmp_path / "comparison.json",
        resamples=50,
    )
    assert comparison["gate_a_passed"] is True
    assert json.loads((tmp_path / "comparison.json").read_text())["schema_version"].endswith("v1")
