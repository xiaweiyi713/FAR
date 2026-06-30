from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from bench.annotations import build_annotation_packet, cohen_kappa, compile_annotations
from bench.build.audit_contamination import audit
from bench.build.auto_annotate import (
    build_review_draft,
    export_label_studio,
    generate_preannotations,
    import_label_studio,
    summarize_preannotations,
)
from bench.build.build_blind_bundle import build as build_blind_bundle
from bench.build.extend_from_verabench import build
from bench.build.import_fever_slice import import_slice
from bench.build.validate_bench import validate
from bench.schema import VALID_CONFLICT_TYPES, VALID_REVISION_ACTIONS

ROOT = Path(__file__).resolve().parents[1]
VERA_BENCH = Path("/Users/xuwenyao/VeraRAG/data/verabench")
FEVER = Path("/Users/xuwenyao/VeraRAG/data/external/fever_pair_candidates_v1")


def test_human_annotation_protocol_mentions_only_valid_labels() -> None:
    text = (ROOT / "docs" / "HUMAN_ANNOTATION_PROTOCOL.md").read_text(encoding="utf-8")
    action_section = text.split("## Revision action guidance", maxsplit=1)[1].split(
        "## Freeze reviewer files",
        maxsplit=1,
    )[0]
    action_labels = set(re.findall(r"-> `([^`]+)`", action_section))
    assert action_labels <= VALID_REVISION_ACTIONS
    assert action_labels >= VALID_REVISION_ACTIONS

    conflict_section = text.split("## Conflict type guidance", maxsplit=1)[1].split(
        "## Revision action guidance",
        maxsplit=1,
    )[0]
    conflict_labels = set(re.findall(r"`([^`]+)`", conflict_section))
    assert conflict_labels == VALID_CONFLICT_TYPES


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
    assert report["counts"]["ambiguous_operational_inputs"] == 0


def test_blind_bundle_contains_only_operational_inputs(tmp_path: Path) -> None:
    output_dir = tmp_path / "blind"
    manifest = build_blind_bundle(ROOT / "bench", output_dir)
    assert manifest["gold_included"] is False
    assert manifest["samples"] == 58
    assert set(path.relative_to(output_dir).as_posix() for path in output_dir.rglob("*")) == {
        "blind_bundle_manifest.json",
        "corpus.jsonl",
        "splits",
        "splits/test_inputs.jsonl",
    }
    rows = [
        json.loads(line)
        for line in (output_dir / "splits/test_inputs.jsonl").read_text().splitlines()
    ]
    assert all(
        set(row) == {"id", "category", "split", "question", "initial_answer"} for row in rows
    )
    corpus_rows = [
        json.loads(line) for line in (output_dir / "corpus.jsonl").read_text().splitlines()
    ]
    assert all("metadata" not in row and "source_doc_id" not in row for row in corpus_rows)
    assert all(set(row) <= set(manifest["public_corpus_fields"]) for row in corpus_rows)
    assert any(row.get("entities") for row in corpus_rows)


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


def test_llm_preannotations_are_non_gold_review_aids(tmp_path: Path) -> None:
    class FakeGenerator:
        def complete(self, prompt: str, **kwargs: object) -> str:
            assert "expected_revision" not in prompt
            assert "role-masked" in prompt
            del kwargs
            return json.dumps(
                {
                    "conflict_present": True,
                    "conflict_type": "numerical",
                    "revision_action": "replace_numerical",
                    "revised_answer_acceptable": True,
                    "suggested_revised_answer": "Use the evidence-backed number.",
                    "rationale": "The evidence snippets contain a different number.",
                    "confidence": 0.72,
                }
            )

    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    output = tmp_path / "preannotations"
    manifest = generate_preannotations(
        packet,
        output,
        generator=FakeGenerator(),
        preannotator_id="deepseek_dryrun",
        limit=2,
    )
    assert manifest["publication_gold"] is False
    assert manifest["can_satisfy_human_annotation_gate"] is False
    rows = list(
        map(json.loads, (output / "preannotations_deepseek_dryrun.jsonl").read_text().splitlines())
    )
    assert len(rows) == 2
    assert rows[0]["publication_gold"] is False
    assert rows[0]["preannotation"]["needs_human_review"] is True
    assert rows[0]["preannotation"]["conflict_type"] == "numerical"


def test_llm_preannotation_fallback_stays_review_only(tmp_path: Path) -> None:
    class BadGenerator:
        def complete(self, prompt: str, **kwargs: object) -> str:
            del prompt, kwargs
            return "not json"

    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    output = tmp_path / "preannotations"
    manifest = generate_preannotations(
        packet,
        output,
        generator=BadGenerator(),
        preannotator_id="bad_llm",
        limit=1,
    )
    assert manifest["llm_failures"] == 1
    row = json.loads((output / "preannotations_bad_llm.jsonl").read_text().splitlines()[0])
    assert row["preannotation"]["confidence"] == 0.0
    assert row["preannotation"]["needs_human_review"] is True


def test_llm_preannotation_normalises_no_action_alias(tmp_path: Path) -> None:
    class AliasGenerator:
        def complete(self, prompt: str, **kwargs: object) -> str:
            del prompt, kwargs
            return json.dumps(
                {
                    "conflict_present": False,
                    "conflict_type": "no_conflict",
                    "revision_action": "none",
                    "revised_answer_acceptable": True,
                    "suggested_revised_answer": "",
                    "rationale": "No evidence conflict found.",
                    "confidence": 0.61,
                }
            )

    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    output = tmp_path / "preannotations"
    manifest = generate_preannotations(
        packet,
        output,
        generator=AliasGenerator(),
        preannotator_id="alias_llm",
        limit=1,
    )

    row = json.loads((output / "preannotations_alias_llm.jsonl").read_text().splitlines()[0])
    assert manifest["llm_failures"] == 0
    assert row["preannotation"]["revision_action"] == "qualify_uncertainty"


def test_llm_preannotation_resume_skips_existing_rows(tmp_path: Path) -> None:
    calls: list[str] = []

    class FakeGenerator:
        def complete(self, prompt: str, **kwargs: object) -> str:
            del kwargs
            calls.append(prompt)
            return json.dumps(
                {
                    "conflict_present": True,
                    "conflict_type": "numerical",
                    "revision_action": "replace_numerical",
                    "revised_answer_acceptable": True,
                    "suggested_revised_answer": "Use the evidence-backed number.",
                    "rationale": "The evidence snippets contain a different number.",
                    "confidence": 0.72,
                }
            )

    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    output = tmp_path / "preannotations"
    generate_preannotations(
        packet,
        output,
        generator=FakeGenerator(),
        preannotator_id="resume_llm",
        limit=1,
    )
    manifest = generate_preannotations(
        packet,
        output,
        generator=FakeGenerator(),
        preannotator_id="resume_llm",
        limit=3,
        resume=True,
    )
    rows = (output / "preannotations_resume_llm.jsonl").read_text().splitlines()
    assert len(rows) == 3
    assert len(calls) == 3
    assert manifest["samples"] == 3
    assert manifest["resumed_existing_samples"] == 1


def test_llm_preannotation_resume_can_retry_fallback_rows(tmp_path: Path) -> None:
    class BadGenerator:
        def complete(self, prompt: str, **kwargs: object) -> str:
            del prompt, kwargs
            return "not json"

    class GoodGenerator:
        def complete(self, prompt: str, **kwargs: object) -> str:
            del prompt, kwargs
            return json.dumps(
                {
                    "conflict_present": True,
                    "conflict_type": "numerical",
                    "revision_action": "replace_numerical",
                    "revised_answer_acceptable": True,
                    "suggested_revised_answer": "Use the evidence-backed number.",
                    "rationale": "The evidence snippets contain a different number.",
                    "confidence": 0.72,
                }
            )

    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    output = tmp_path / "preannotations"
    generate_preannotations(
        packet,
        output,
        generator=BadGenerator(),
        preannotator_id="retry_llm",
        limit=1,
    )
    manifest = generate_preannotations(
        packet,
        output,
        generator=GoodGenerator(),
        preannotator_id="retry_llm",
        limit=1,
        resume=True,
        retry_fallbacks=True,
    )
    rows = [
        json.loads(line)
        for line in (output / "preannotations_retry_llm.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 1
    assert manifest["llm_failures"] == 0
    assert manifest["resumed_existing_samples"] == 0
    assert rows[0]["preannotation"]["confidence"] == 0.72


def test_llm_preannotation_rejects_resume_with_overwrite(tmp_path: Path) -> None:
    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    with pytest.raises(ValueError, match="overwrite and resume"):
        generate_preannotations(
            packet,
            tmp_path / "preannotations",
            generator=None,
            preannotator_id="invalid",
            overwrite=True,
            resume=True,
        )


def test_llm_preannotation_rejects_retry_fallbacks_without_resume(tmp_path: Path) -> None:
    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    with pytest.raises(ValueError, match="retry_fallbacks requires resume"):
        generate_preannotations(
            packet,
            tmp_path / "preannotations",
            generator=None,
            preannotator_id="invalid",
            retry_fallbacks=True,
        )


def test_preannotation_summary_audits_in_progress_outputs(tmp_path: Path) -> None:
    class BadGenerator:
        def complete(self, prompt: str, **kwargs: object) -> str:
            del prompt, kwargs
            return "not json"

    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    output = tmp_path / "preannotations"
    generate_preannotations(
        packet,
        output,
        generator=BadGenerator(),
        preannotator_id="summary_llm",
        limit=2,
    )
    (output / "preannotation_manifest.json").unlink()

    summary = summarize_preannotations(output, packet_dir=packet)

    assert summary["rows"] == 2
    assert summary["unique_samples"] == 2
    assert summary["fallback_failures"] == 2
    assert summary["publication_gold_false_rows"] == 2
    assert summary["needs_human_review_rows"] == 2
    assert summary["packet_samples"] == 300
    assert summary["missing_packet_samples"] == 298
    assert summary["matches_packet_complete"] is False
    assert (output / "preannotation_summary.json").exists()


def test_machine_review_draft_requires_explicit_human_review(tmp_path: Path) -> None:
    class FakeGenerator:
        def complete(self, prompt: str, **kwargs: object) -> str:
            del prompt, kwargs
            return json.dumps(
                {
                    "conflict_present": True,
                    "conflict_type": "entity",
                    "revision_action": "requalify_entity",
                    "revised_answer_acceptable": False,
                    "suggested_revised_answer": "Qualify the entity.",
                    "rationale": "The entity in the answer differs from the evidence.",
                    "confidence": 0.8,
                }
            )

    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    preannotations = tmp_path / "preannotations"
    generate_preannotations(
        packet,
        preannotations,
        generator=FakeGenerator(),
        preannotator_id="draft_source",
        limit=1,
    )
    draft_dir = tmp_path / "draft"
    manifest = build_review_draft(
        packet,
        preannotations,
        draft_dir,
        reviewer_id="alice",
    )
    assert manifest["human_review_required"] is True
    draft_row = json.loads(
        (draft_dir / "draft_annotations_alice.jsonl").read_text().splitlines()[0]
    )
    assert draft_row["draft_from_machine_preannotation"] is True
    assert draft_row["human_reviewed"] is False

    packet_manifest = json.loads((packet / "packet_manifest.json").read_text())
    packet_manifest["annotation_files"]["alice"] = "../draft/draft_annotations_alice.jsonl"
    (packet / "packet_manifest.json").write_text(json.dumps(packet_manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="human_reviewed=true"):
        compile_annotations(ROOT / "bench", packet, tmp_path / "compiled")


def test_label_studio_export_contains_machine_predictions_as_review_aids(
    tmp_path: Path,
) -> None:
    class FakeGenerator:
        def complete(self, prompt: str, **kwargs: object) -> str:
            del prompt, kwargs
            return json.dumps(
                {
                    "conflict_present": True,
                    "conflict_type": "causal",
                    "revision_action": "downgrade_causal_to_correlation",
                    "revised_answer_acceptable": True,
                    "suggested_revised_answer": "Treat the relationship as correlational.",
                    "rationale": "The evidence does not establish causality.",
                    "confidence": 0.66,
                }
            )

    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    preannotations = tmp_path / "preannotations"
    generate_preannotations(
        packet,
        preannotations,
        generator=FakeGenerator(),
        preannotator_id="label_studio_source",
        limit=2,
    )
    export_dir = tmp_path / "label_studio"
    manifest = export_label_studio(
        packet,
        export_dir,
        preannotation_dir=preannotations,
    )
    assert manifest["publication_gold"] is False
    assert manifest["human_review_required"] is True
    assert manifest["tasks_with_predictions"] == 2
    assert (export_dir / "label_config.xml").exists()
    tasks = json.loads((export_dir / "tasks.json").read_text(encoding="utf-8"))
    assert len(tasks) == 300
    assert tasks[0]["meta"]["publication_gold"] is False
    predicted_tasks = [task for task in tasks if task.get("predictions")]
    assert len(predicted_tasks) == 2
    result = predicted_tasks[0]["predictions"][0]["result"]
    assert any(
        item["from_name"] == "conflict_type" and item["value"]["choices"] == ["causal"]
        for item in result
    )


def test_label_studio_import_returns_reviewed_far_annotation_file(tmp_path: Path) -> None:
    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    export_dir = tmp_path / "label_studio"
    export_label_studio(packet, export_dir)
    tasks = json.loads((export_dir / "tasks.json").read_text(encoding="utf-8"))
    annotation_result = [
        {
            "from_name": "conflict_presence",
            "to_name": "context",
            "type": "choices",
            "value": {"choices": ["conflict"]},
        },
        {
            "from_name": "conflict_type",
            "to_name": "context",
            "type": "choices",
            "value": {"choices": ["counter_evidence"]},
        },
        {
            "from_name": "revision_action",
            "to_name": "context",
            "type": "choices",
            "value": {"choices": ["qualify_uncertainty"]},
        },
        {
            "from_name": "revised_answer_acceptable",
            "to_name": "context",
            "type": "choices",
            "value": {"choices": ["not_acceptable"]},
        },
        {
            "from_name": "rationale",
            "to_name": "context",
            "type": "textarea",
            "value": {"text": ["Reviewed in Label Studio."]},
        },
    ]
    for task in tasks:
        task["annotations"] = [{"result": annotation_result}]
    reviewed_json = tmp_path / "label_studio_reviewed.json"
    reviewed_json.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")

    import_dir = tmp_path / "imported"
    manifest = import_label_studio(
        packet,
        reviewed_json,
        import_dir,
        reviewer_id="alice",
    )
    assert manifest["samples"] == 300
    assert manifest["human_reviewed"] is True
    row = json.loads((import_dir / "annotations_alice.jsonl").read_text().splitlines()[0])
    assert row["source_tool"] == "label_studio"
    assert row["human_reviewed"] is True
    assert row["annotation"]["conflict_type"] == "counter_evidence"


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
