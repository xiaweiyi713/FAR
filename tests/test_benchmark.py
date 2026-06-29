from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.annotations import build_annotation_packet, cohen_kappa, compile_annotations
from bench.build.audit_contamination import audit
from bench.build.extend_from_verabench import build
from bench.build.import_fever_slice import import_slice
from bench.build.validate_bench import validate

ROOT = Path(__file__).resolve().parents[1]
VERA_BENCH = Path("/Users/xuwenyao/VeraRAG/data/verabench")
FEVER = Path("/Users/xuwenyao/VeraRAG/data/external/fever_pair_candidates_v1")


def test_tracked_benchmark_is_balanced_traceable_and_retrievable() -> None:
    report = validate(ROOT / "bench")
    assert report["valid"] is True
    assert report["publication_ready"] is False
    assert report["counts"]["categories"] == {
        "temporal_shift": 60,
        "numerical_conflict": 60,
        "entity_confusion": 60,
        "causal_overclaim": 60,
        "multi_source_conflict": 60,
    }
    assert report["counter_evidence_retrieval"]["recall"] >= 0.8


@pytest.mark.skipif(not VERA_BENCH.exists(), reason="local VeraRAG fixture unavailable")
def test_benchmark_build_is_reproducible(tmp_path: Path) -> None:
    first = build(VERA_BENCH, tmp_path / "first")
    second = build(VERA_BENCH, tmp_path / "second")
    assert first["fingerprints"] == second["fingerprints"]


def test_annotation_packet_hides_machine_labels_and_requires_completion(
    tmp_path: Path,
) -> None:
    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    first = json.loads((packet / "annotations_alice.jsonl").read_text().splitlines()[0])
    serialized = json.dumps(first)
    assert "expected_revision" not in serialized
    assert 'conflict_type"' in serialized  # blank annotation field is present
    assert all(item["evidence_id"].startswith("EVIDENCE_") for item in first["evidence"])
    with pytest.raises(ValueError, match="conflict_present"):
        compile_annotations(ROOT / "bench", packet, tmp_path / "compiled")


def test_cohen_kappa_handles_perfect_and_chance_adjusted_agreement() -> None:
    assert cohen_kappa(["a", "b", "a"], ["a", "b", "a"]) == 1.0
    assert cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0


def test_completed_annotations_compile_with_kappa_report(tmp_path: Path) -> None:
    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    samples = {
        row["id"]: row
        for row in map(
            json.loads,
            (ROOT / "bench/falsirag_bench.jsonl").read_text().splitlines(),
        )
    }
    for name in ("annotations_alice.jsonl", "annotations_bob.jsonl"):
        rows = list(map(json.loads, (packet / name).read_text().splitlines()))
        for row in rows:
            sample = samples[row["sample_id"]]
            row["annotation"] = {
                "conflict_present": True,
                "conflict_type": sample["conflict_type"],
                "revision_action": sample["expected_revision"]["action"],
                "revised_answer_acceptable": True,
                "rationale": "Test-only completed annotation.",
            }
        (packet / name).write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
    adjudications = list(map(json.loads, (packet / "adjudications.jsonl").read_text().splitlines()))
    for row in adjudications:
        sample = samples[row["sample_id"]]
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
    compiled_dir = tmp_path / "compiled"
    report = compile_annotations(ROOT / "bench", packet, compiled_dir)
    assert report["agreement_gate_passed"] is True
    assert set(report["mean_kappas"].values()) == {1.0}
    assert validate(compiled_dir)["candidate_ready"] is True


def test_contamination_audit_reports_explicit_reference_overlap(tmp_path: Path) -> None:
    reference = tmp_path / "reference.jsonl"
    first_question = json.loads((ROOT / "bench/falsirag_bench.jsonl").read_text().splitlines()[0])
    reference.write_text(
        json.dumps({"text": first_question["question"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report = audit(ROOT / "bench/falsirag_bench.jsonl", [reference])
    assert report["conclusion"] == "potential_overlap_requires_review"
    assert report["exact_matches"]


@pytest.mark.skipif(not FEVER.exists(), reason="local FEVER candidate fixture unavailable")
def test_external_fever_slice_remains_non_gold(tmp_path: Path) -> None:
    manifest = import_slice(FEVER, tmp_path / "fever")
    assert manifest["counts"] == {"questions": 100, "documents": 200}
    assert manifest["publication_gold"] is False
