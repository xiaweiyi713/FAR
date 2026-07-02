from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest

from bench.annotations import (
    annotation_packet_status,
    build_annotation_packet,
    build_reviewer_handoff,
    cohen_kappa,
    compile_annotations,
    install_adjudication_file,
    install_review_file,
    validate_annotation_evidence,
)
from bench.build.audit_contamination import audit
from bench.build.auto_annotate import (
    build_review_draft,
    export_adjudication_label_studio,
    export_label_studio,
    generate_preannotations,
    import_adjudication_label_studio,
    import_label_studio,
    summarize_preannotations,
)
from bench.build.build_blind_bundle import (
    audit_bundle,
    package_handoff,
)
from bench.build.build_blind_bundle import (
    build as build_blind_bundle,
)
from bench.build.extend_from_verabench import build
from bench.build.import_fever_slice import import_slice
from bench.build.machine_label_audit import audit_machine_labels
from bench.build.validate_bench import validate
from bench.build.weak_label import generate_weak_labels, weak_label_row
from bench.schema import VALID_CONFLICT_TYPES, VALID_REVISION_ACTIONS
from eval.run_eval import evaluate
from experiments.run_far import run

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
    assert audit_bundle(output_dir)["valid"] is True


def test_blind_handoff_package_is_gold_free_and_deterministic(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "blind"
    build_blind_bundle(ROOT / "bench", bundle_dir)
    output_dir = tmp_path / "custodian_package"
    manifest = package_handoff(
        bundle_dir,
        output_dir,
        config_paths=[ROOT / "experiments/configs/offline_smoke.yaml"],
        frozen_commit="abc123",
    )
    assert manifest["schema_version"] == "falsirag-blind-custodian-handoff-v1"
    assert manifest["safety"]["gold_included"] is False
    assert manifest["bundle_audit"]["samples"] == 58
    archive = tmp_path / "custodian_package.zip"
    assert archive.exists()
    first_sha = manifest["archive_sha256"]
    with zipfile.ZipFile(archive) as package:
        names = set(package.namelist())
    assert names == {
        "CUSTODIAN_RUN_SHEET.md",
        "blind_bundle/blind_bundle_manifest.json",
        "blind_bundle/corpus.jsonl",
        "blind_bundle/splits/test_inputs.jsonl",
        "configs/offline_smoke.yaml",
        "custodian_handoff_manifest.json",
    }
    assert not any("falsirag_bench" in name or "annotation" in name for name in names)
    second = package_handoff(
        bundle_dir,
        output_dir,
        config_paths=[ROOT / "experiments/configs/offline_smoke.yaml"],
        frozen_commit="abc123",
        overwrite=True,
    )
    assert second["archive_sha256"] == first_sha


def test_blind_bundle_audit_rejects_technical_and_forbidden_gold_keys(tmp_path: Path) -> None:
    technical_dir = tmp_path / "falsirag_blind_test_technical_v1"
    build_blind_bundle(ROOT / "bench", technical_dir)
    with pytest.raises(ValueError, match="technical dry-run"):
        audit_bundle(technical_dir)

    unsafe_dir = tmp_path / "unsafe"
    build_blind_bundle(ROOT / "bench", unsafe_dir)
    rows = [
        json.loads(line)
        for line in (unsafe_dir / "splits/test_inputs.jsonl").read_text().splitlines()
    ]
    rows[0]["expected_revision"] = {"action": "leaked"}
    (unsafe_dir / "splits/test_inputs.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-operational fields"):
        audit_bundle(unsafe_dir)


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


def test_annotation_packet_status_reports_review_and_adjudication_progress(
    tmp_path: Path,
) -> None:
    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    blank_status = annotation_packet_status(packet, data_dir=ROOT / "bench")
    assert blank_status["samples"] == 300
    assert blank_status["reviewers_complete"] is False
    assert blank_status["ready_to_export_adjudication_label_studio"] is False
    assert blank_status["ready_to_compile"] is False
    assert blank_status["reviewers"]["alice"]["blank"] == 300
    assert blank_status["adjudication"]["blank"] == 300
    assert blank_status["source_fingerprints"]["matches"] is True

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
                "rationale": "Reviewer completed this row.",
            }
        (packet / name).write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    reviewer_status = annotation_packet_status(packet, data_dir=ROOT / "bench")
    assert reviewer_status["reviewers_complete"] is True
    assert reviewer_status["ready_to_export_adjudication_label_studio"] is True
    assert reviewer_status["ready_to_compile"] is False
    assert reviewer_status["reviewers"]["alice"]["visible_fields_match"] is True

    adjudications = list(map(json.loads, (packet / "adjudications.jsonl").read_text().splitlines()))
    for row in adjudications:
        sample = samples[row["sample_id"]]
        row["adjudicator_id"] = "judge_1"
        row["gold_annotation"] = {
            "conflict_present": True,
            "conflict_type": sample["conflict_type"],
            "revision_action": sample["expected_revision"]["action"],
            "revised_answer_acceptable": True,
            "revised_answer": sample["expected_revision"]["revised_answer"],
            "rationale": "Final adjudication.",
        }
    adjudications[0]["gold_annotation"]["revised_answer"] = ""
    (packet / "adjudications.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in adjudications),
        encoding="utf-8",
    )
    invalid_status = annotation_packet_status(packet, data_dir=ROOT / "bench")
    assert invalid_status["adjudication"]["invalid"] == 1
    assert invalid_status["ready_to_compile"] is False

    adjudications[0]["gold_annotation"]["revised_answer"] = samples[adjudications[0]["sample_id"]][
        "expected_revision"
    ]["revised_answer"]
    (packet / "adjudications.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in adjudications),
        encoding="utf-8",
    )
    ready_status = annotation_packet_status(packet, data_dir=ROOT / "bench")
    assert ready_status["adjudication"]["consistent_adjudicator_id"] is True
    assert ready_status["adjudication"]["completed"] == 300
    assert ready_status["ready_to_compile"] is True
    assert ready_status["next_steps"] == [
        "run compile to freeze annotation evidence and compute kappa"
    ]


def test_reviewer_handoff_contains_only_one_blank_reviewer_packet(tmp_path: Path) -> None:
    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])

    handoff_dir = tmp_path / "alice_handoff"
    manifest = build_reviewer_handoff(packet, handoff_dir, reviewer_id="alice")
    assert manifest["samples"] == 300
    assert manifest["safety"]["single_reviewer_only"] is True
    assert manifest["safety"]["machine_predictions_included"] is False
    assert (handoff_dir / "annotations_alice.jsonl").exists()
    assert not (handoff_dir / "annotations_bob.jsonl").exists()
    assert not (handoff_dir / "packet_manifest.json").exists()
    assert (tmp_path / "alice_handoff.zip").exists()
    assert manifest["archive_sha256"]

    names = set()
    with zipfile.ZipFile(tmp_path / "alice_handoff.zip") as archive:
        names = set(archive.namelist())
        assert "annotations_alice.jsonl" in names
        assert "annotations_bob.jsonl" not in names
        assert "packet_manifest.json" not in names
    assert names == {
        "annotations_alice.jsonl",
        "PACKET_README.md",
        "REVIEWER_INSTRUCTIONS.md",
        "handoff_manifest.json",
    }

    rows = list(map(json.loads, (packet / "annotations_alice.jsonl").read_text().splitlines()))
    rows[0]["annotation"]["conflict_present"] = False
    rows[0]["annotation"]["revision_action"] = "qualify_uncertainty"
    rows[0]["annotation"]["revised_answer_acceptable"] = True
    rows[0]["annotation"]["rationale"] = "Already filled."
    (packet / "annotations_alice.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="blank reviewer template"):
        build_reviewer_handoff(packet, tmp_path / "filled_handoff", reviewer_id="alice")


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


def test_weak_labels_are_non_gold_review_aids(tmp_path: Path) -> None:
    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    output = tmp_path / "weak"
    manifest = generate_weak_labels(packet, output, limit=12)
    assert manifest["publication_gold"] is False
    assert manifest["can_satisfy_human_annotation_gate"] is False
    assert manifest["samples"] == 12
    assert manifest["non_abstained"] > 0
    rows = [
        json.loads(line) for line in (output / "weak_annotations.jsonl").read_text().splitlines()
    ]
    assert rows[0]["publication_gold"] is False
    assert rows[0]["weak_annotation"]["needs_human_review"] is True
    assert rows[0]["weak_annotation"]["conflict_type"] in VALID_CONFLICT_TYPES | {"no_conflict"}


def test_weak_label_row_detects_temporal_and_source_signals() -> None:
    row = {
        "sample_id": "W1",
        "question": "When did the policy start?",
        "initial_answer": "An unverified secondary summary reports: 2024年8月15日。",
        "claims": [{"claim_id": "C1", "claim": "2024年8月15日。"}],
        "evidence": [
            {
                "evidence_id": "EVIDENCE_A",
                "text": "2023年8月15日，《生成式人工智能服务管理暂行办法》正式施行。",
            }
        ],
    }
    annotation = weak_label_row(row)
    signal_names = {signal["name"] for signal in annotation["signals"]}
    assert annotation["conflict_present"] is True
    assert annotation["conflict_type"] == "temporal"
    assert {"year_mismatch", "unverified_source_phrase"} <= signal_names


def test_machine_label_audit_prioritizes_disagreements(tmp_path: Path) -> None:
    class TemporalGenerator:
        def complete(self, prompt: str, **kwargs: object) -> str:
            del prompt, kwargs
            return json.dumps(
                {
                    "conflict_present": True,
                    "conflict_type": "temporal",
                    "revision_action": "correct_temporal",
                    "revised_answer_acceptable": True,
                    "suggested_revised_answer": "",
                    "rationale": "The year differs.",
                    "confidence": 0.8,
                }
            )

    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    preannotations = tmp_path / "preannotations"
    generate_preannotations(
        packet,
        preannotations,
        generator=TemporalGenerator(),
        preannotator_id="temporal_llm",
        limit=6,
    )
    weak = tmp_path / "weak"
    generate_weak_labels(packet, weak, limit=6)
    audit_dir = tmp_path / "audit"
    report = audit_machine_labels(preannotations, weak, audit_dir, packet_dir=packet)
    assert report["publication_gold"] is False
    assert report["can_satisfy_human_annotation_gate"] is False
    assert report["shared_samples"] == 6
    assert report["priority_review_samples"] >= 0
    assert (audit_dir / "machine_label_comparison.jsonl").exists()


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

    draft_in_packet = packet / "draft_annotations_alice.jsonl"
    draft_in_packet.write_text(
        (draft_dir / "draft_annotations_alice.jsonl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    packet_manifest = json.loads((packet / "packet_manifest.json").read_text())
    packet_manifest["annotation_files"]["alice"] = draft_in_packet.name
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
        reviewer_id="alice",
        preannotation_dir=preannotations,
    )
    assert manifest["publication_gold"] is False
    assert manifest["human_review_required"] is True
    assert manifest["tasks_with_predictions"] == 2
    assert (export_dir / "label_config.xml").exists()
    assert "blind review: alice" in (export_dir / "README.md").read_text(encoding="utf-8")
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
    export_label_studio(packet, export_dir, reviewer_id="alice")
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


def test_label_studio_exports_are_bound_to_one_reviewer_packet(tmp_path: Path) -> None:
    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    alice_dir = tmp_path / "alice-label-studio"
    bob_dir = tmp_path / "bob-label-studio"
    export_label_studio(packet, alice_dir, reviewer_id="alice")
    export_label_studio(packet, bob_dir, reviewer_id="bob")
    alice_tasks = json.loads((alice_dir / "tasks.json").read_text(encoding="utf-8"))
    bob_tasks = json.loads((bob_dir / "tasks.json").read_text(encoding="utf-8"))
    alice_by_id = {task["data"]["sample_id"]: task for task in alice_tasks}
    bob_by_id = {task["data"]["sample_id"]: task for task in bob_tasks}
    assert all(task["meta"]["reviewer_id"] == "alice" for task in alice_tasks)
    assert any(
        alice_by_id[sample_id]["data"]["context"] != bob_by_id[sample_id]["data"]["context"]
        for sample_id in alice_by_id
    )
    reviewed = tmp_path / "alice-export.json"
    reviewed.write_text(json.dumps(alice_tasks), encoding="utf-8")
    with pytest.raises(ValueError, match="different reviewer"):
        import_label_studio(
            packet,
            reviewed,
            tmp_path / "wrong-reviewer",
            reviewer_id="bob",
        )


def test_label_studio_adjudication_round_trip_installs_and_compiles(tmp_path: Path) -> None:
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
                "rationale": "Reviewer checked the visible evidence.",
            }
        (packet / name).write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    export_dir = tmp_path / "adjudication-label-studio"
    manifest = export_adjudication_label_studio(packet, export_dir)
    assert manifest["tasks"] == 300
    assert manifest["reviewer_ids"] == ["alice", "bob"]
    tasks = json.loads((export_dir / "tasks.json").read_text(encoding="utf-8"))
    assert "Frozen independent reviewer labels" in tasks[0]["data"]["context"]
    assert "evidence_id_map_to_adjudicator_packet" in tasks[0]["data"]["context"]

    for task in tasks:
        sample = samples[task["data"]["sample_id"]]
        task["annotations"] = [
            {
                "result": [
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
                        "value": {"choices": [sample["conflict_type"]]},
                    },
                    {
                        "from_name": "revision_action",
                        "to_name": "context",
                        "type": "choices",
                        "value": {"choices": [sample["expected_revision"]["action"]]},
                    },
                    {
                        "from_name": "revised_answer_acceptable",
                        "to_name": "context",
                        "type": "choices",
                        "value": {"choices": ["acceptable"]},
                    },
                    {
                        "from_name": "revised_answer",
                        "to_name": "context",
                        "type": "textarea",
                        "value": {"text": [sample["expected_revision"]["revised_answer"]]},
                    },
                    {
                        "from_name": "rationale",
                        "to_name": "context",
                        "type": "textarea",
                        "value": {"text": ["Adjudicator selected the final label."]},
                    },
                ]
            }
        ]
    reviewed_json = tmp_path / "label_studio_adjudicated.json"
    reviewed_json.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")

    imported = tmp_path / "adjudication-imported"
    import_manifest = import_adjudication_label_studio(
        packet,
        reviewed_json,
        imported,
        adjudicator_id="judge_1",
    )
    assert import_manifest["samples"] == 300
    installed = install_adjudication_file(
        packet,
        imported / "adjudications.jsonl",
        adjudicator_id="judge_1",
    )
    assert installed["samples"] == 300
    compiled = tmp_path / "compiled"
    report = compile_annotations(ROOT / "bench", packet, compiled)
    assert report["adjudicator_id"] == "judge_1"
    assert validate_annotation_evidence(compiled)["valid"] is True


def test_install_review_file_is_atomic_and_refuses_replacement(tmp_path: Path) -> None:
    packet = tmp_path / "packet"
    build_annotation_packet(ROOT / "bench", packet, ["alice", "bob"])
    rows = [
        json.loads(line) for line in (packet / "annotations_alice.jsonl").read_text().splitlines()
    ]
    for row in rows:
        row["annotation"] = {
            "conflict_present": True,
            "conflict_type": "counter_evidence",
            "revision_action": "qualify_uncertainty",
            "revised_answer_acceptable": True,
            "rationale": "Human-reviewed visible evidence.",
        }
    review_file = tmp_path / "completed_alice.jsonl"
    review_file.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    installed = install_review_file(packet, review_file, reviewer_id="alice")
    assert installed["samples"] == 300
    with pytest.raises(FileExistsError, match="already completed"):
        install_review_file(packet, review_file, reviewer_id="alice")


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
    alice_path = packet / "annotations_alice.jsonl"
    valid_alice = alice_path.read_text(encoding="utf-8")
    tampered = [json.loads(line) for line in valid_alice.splitlines()]
    tampered[0]["question"] = "Modified question"
    alice_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in tampered),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="modified blind packet fields"):
        compile_annotations(ROOT / "bench", packet, tmp_path / "tampered-compiled")
    alice_path.write_text(valid_alice, encoding="utf-8")
    alice_path.write_text(valid_alice + valid_alice.splitlines()[0] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="301 rows"):
        compile_annotations(ROOT / "bench", packet, tmp_path / "duplicate-compiled")
    alice_path.write_text(valid_alice, encoding="utf-8")
    adjudication_path = packet / "adjudications.jsonl"
    valid_adjudications = adjudication_path.read_text(encoding="utf-8")
    blank_conflict = [json.loads(line) for line in valid_adjudications.splitlines()]
    blank_conflict[0]["gold_annotation"]["revised_answer"] = ""
    adjudication_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in blank_conflict),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="requires revised_answer"):
        compile_annotations(ROOT / "bench", packet, tmp_path / "blank-answer-compiled")
    no_conflict = [json.loads(line) for line in valid_adjudications.splitlines()]
    no_conflict[0]["gold_annotation"].update(
        {
            "conflict_present": False,
            "conflict_type": "",
            "revision_action": "qualify_uncertainty",
            "revised_answer": "This should not be accepted for no-conflict adjudication.",
            "rationale": "No material conflict in the visible evidence.",
        }
    )
    no_conflict_id = no_conflict[0]["sample_id"]
    adjudication_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in no_conflict),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must not set revised_answer"):
        compile_annotations(ROOT / "bench", packet, tmp_path / "no-conflict-answer-compiled")
    no_conflict[0]["gold_annotation"]["revised_answer"] = ""
    adjudication_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in no_conflict),
        encoding="utf-8",
    )
    compiled_dir = tmp_path / "compiled"
    report = compile_annotations(ROOT / "bench", packet, compiled_dir)
    assert report["agreement_gate_passed"] is True
    assert report["adjudicator_id"] == "adjudicator_1"
    assert set(report["mean_kappas"].values()) == {1.0}
    evidence_validation = validate_annotation_evidence(compiled_dir)
    assert evidence_validation["valid"] is True
    archived_alice = compiled_dir / "annotation_evidence/annotations_alice.jsonl"
    archived_content = archived_alice.read_text(encoding="utf-8")
    archived_alice.write_text(archived_content + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_annotation_evidence(compiled_dir)
    archived_alice.write_text(archived_content, encoding="utf-8")
    assert validate(compiled_dir)["candidate_ready"] is True
    compiled_by_id = {
        row["id"]: row
        for row in map(
            json.loads,
            (compiled_dir / "falsirag_bench.jsonl").read_text().splitlines(),
        )
    }
    assert compiled_by_id[no_conflict_id]["conflict_type"] == "no_conflict"
    assert (
        compiled_by_id[no_conflict_id]["expected_revision"]["revised_answer"]
        == compiled_by_id[no_conflict_id]["initial_answer"]
    )

    run_dir = tmp_path / "adjudicated-run"
    run(
        ROOT / "experiments/configs/offline_smoke.yaml",
        compiled_dir,
        run_dir,
        split="dev",
        limit=5,
    )
    evaluation = evaluate(
        compiled_dir / "falsirag_bench.jsonl",
        run_dir / "predictions.jsonl",
        tmp_path / "adjudicated-evaluation",
        resamples=20,
    )
    assert evaluation["publication_ready"] is True
    assert evaluation["publication"]["phase"] == "development"
    assert evaluation["publication"]["annotation_ready"] is True
    assert evaluation["publication"]["external_blind_ready"] is False


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
