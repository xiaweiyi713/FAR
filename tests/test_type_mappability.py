from __future__ import annotations

import json
from pathlib import Path

import pytest

from far.bench.build.common import read_jsonl, write_json, write_jsonl
from far.experiments.type_mappability import (
    DATASET_ORDER,
    HUMAN_ROLES,
    MAPPABILITY_LABELS,
    _association,
    analyze,
    install_human_annotations,
    install_machine_prelabels,
    packet_status,
    prelabel_packet,
    prepare_packet,
    validate_annotation,
    verify_protocol_inputs,
    verify_report,
)

ROOT = Path(__file__).resolve().parents[1]


def _annotation(label: str, index: int) -> dict[str, object]:
    if label == "clean":
        return {
            "mappability": "clean",
            "mapped_types": ["temporal" if index % 2 else "entity"],
            "missing_concept": "",
            "rationale": "One frozen type fully represents the decisive conflict.",
        }
    if label == "partial":
        return {
            "mappability": "partial",
            "mapped_types": ["counter_evidence"],
            "missing_concept": "multi_hop_relation",
            "rationale": "A direct contradiction is present but a relation is missing.",
        }
    return {
        "mappability": "unmappable",
        "mapped_types": [],
        "missing_concept": "pragmatic_incompatibility",
        "rationale": "The decisive incompatibility is outside the frozen ontology.",
    }


def _completed_source(
    packet_dir: Path,
    output_path: Path,
    *,
    offset: int = 0,
) -> Path:
    items = read_jsonl(packet_dir / "items.jsonl")
    rows = []
    for index, item in enumerate(items):
        label = MAPPABILITY_LABELS[(index + offset) % len(MAPPABILITY_LABELS)]
        rows.append(
            {
                "sample_id": item["sample_id"],
                "context_sha256": item["context_sha256"],
                "annotation": _annotation(label, index),
            }
        )
    write_jsonl(output_path, rows)
    return output_path


def _install_complete_synthetic_packet(packet_dir: Path, tmp_path: Path) -> None:
    reviewer_a = _completed_source(packet_dir, tmp_path / "reviewer_a.jsonl")
    reviewer_b = _completed_source(packet_dir, tmp_path / "reviewer_b.jsonl", offset=1)
    adjudicator = _completed_source(packet_dir, tmp_path / "adjudicator.jsonl")
    machine = _completed_source(packet_dir, tmp_path / "machine.jsonl", offset=2)
    install_human_annotations(
        packet_dir,
        reviewer_a,
        role="reviewer_a",
        annotator_id="reviewer-a",
    )
    install_human_annotations(
        packet_dir,
        reviewer_b,
        role="reviewer_b",
        annotator_id="reviewer-b",
    )
    identity = tmp_path / "machine_identity.json"
    write_json(
        identity,
        {
            "model": "synthetic-test-model",
            "model_digest": "sha256:" + "3" * 64,
            "config_sha256": "1" * 64,
            "prompt_template_sha256": "2" * 64,
        },
    )
    install_machine_prelabels(packet_dir, machine, identity)
    install_human_annotations(
        packet_dir,
        adjudicator,
        role="adjudicator",
        annotator_id="adjudicator-c",
    )


def test_protocol_inputs_and_packet_selection_are_frozen(tmp_path: Path) -> None:
    audit = verify_protocol_inputs()
    assert audit["valid"] is True
    assert audit["retrospective"] is True
    assert audit["confirmatory_h4"] is False

    packet = tmp_path / "packet"
    manifest = prepare_packet(packet)
    items = read_jsonl(packet / "items.jsonl")

    assert manifest["samples"] == 217
    assert manifest["dataset_counts"] == {"wikicontradict": 150, "rag_conflicts": 67}
    assert {row["dataset"] for row in items} == set(DATASET_ORDER)
    assert all("strata" not in row for row in items)
    assert len(read_jsonl(packet / "analysis_index.jsonl")) == 217
    assert all(str(row["sample_id"]).startswith(("WIKI", "GCON")) for row in items)
    assert len({row["context_sha256"] for row in items}) == 217
    status = packet_status(packet)
    assert status["ready_to_analyze"] is False
    assert all(status["roles"][role]["complete"] is False for role in HUMAN_ROLES)
    with pytest.raises(ValueError, match="not ready"):
        analyze(packet, tmp_path / "report")


def test_committed_blank_packet_is_valid_and_fail_closed() -> None:
    status = packet_status(ROOT / "diagnostics" / "type_mappability_v1")
    assert status["valid_packet"] is True
    assert status["samples"] == 217
    assert status["input_audit"]["valid"] is True
    assert status["ready_to_analyze"] is False


def test_annotation_schema_enforces_the_three_frozen_meanings() -> None:
    for index, label in enumerate(MAPPABILITY_LABELS):
        assert (
            validate_annotation(_annotation(label, index), sample_id="S1")["mappability"] == label
        )
    invalid_clean = _annotation("clean", 0)
    invalid_clean["mapped_types"] = ["entity", "temporal"]
    with pytest.raises(ValueError, match="clean requires one type"):
        validate_annotation(invalid_clean, sample_id="S1")
    invalid_unmappable = _annotation("unmappable", 0)
    invalid_unmappable["mapped_types"] = ["counter_evidence"]
    with pytest.raises(ValueError, match="unmappable requires no types"):
        validate_annotation(invalid_unmappable, sample_id="S1")


def test_install_fails_closed_for_reused_identity_and_context_tamper(tmp_path: Path) -> None:
    packet = tmp_path / "packet"
    prepare_packet(packet)
    source = _completed_source(packet, tmp_path / "review.jsonl")
    install_human_annotations(
        packet,
        source,
        role="reviewer_a",
        annotator_id="same-person",
    )
    with pytest.raises(ValueError, match="must be distinct"):
        install_human_annotations(
            packet,
            source,
            role="reviewer_b",
            annotator_id="same-person",
        )

    items_path = packet / "items.jsonl"
    items = read_jsonl(items_path)
    items[0]["question"] = "tampered question"
    write_jsonl(items_path, items)
    status = packet_status(packet)
    assert status["valid_packet"] is False
    assert "immutable file changed" in status["errors"][0]


def test_adjudication_requires_reviewers_and_machine_prelabels(tmp_path: Path) -> None:
    packet = tmp_path / "packet"
    prepare_packet(packet)
    source = _completed_source(packet, tmp_path / "adjudicator.jsonl")
    with pytest.raises(ValueError, match="both frozen reviewer"):
        install_human_annotations(
            packet,
            source,
            role="adjudicator",
            annotator_id="adjudicator-c",
        )


def test_installed_annotation_change_is_detected(tmp_path: Path) -> None:
    packet = tmp_path / "packet"
    prepare_packet(packet)
    source = _completed_source(packet, tmp_path / "reviewer.jsonl")
    install_human_annotations(
        packet,
        source,
        role="reviewer_a",
        annotator_id="reviewer-a",
    )
    installed = packet / "completed" / "reviewer_a.jsonl"
    rows = read_jsonl(installed)
    rows[0]["annotation"] = _annotation("unmappable", 0)
    write_jsonl(installed, rows)
    status = packet_status(packet)
    assert status["roles"]["reviewer_a"]["complete"] is False
    assert "frozen install manifest" in status["roles"]["reviewer_a"]["error"]


def test_association_reports_descriptive_statistics_without_p_value() -> None:
    result = _association(
        [
            {"weighted_mappability": 0.0, "mean_delta": -0.1},
            {"weighted_mappability": 0.5, "mean_delta": 0.0},
            {"weighted_mappability": 1.0, "mean_delta": 0.1},
        ]
    )
    assert result["spearman_rho"] == pytest.approx(1.0)
    assert result["ols_slope"] == pytest.approx(0.2)
    assert result["ols_r_squared"] == pytest.approx(1.0)
    assert result["confirmatory_p_value"] is None


def test_machine_prelabel_is_resumable_provenanced_and_released_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = tmp_path / "packet"
    prepare_packet(packet)
    config = tmp_path / "config.yaml"
    config.write_text(
        "llm:\n  enabled: true\n  provider: ollama\n  model: test-model\n",
        encoding="utf-8",
    )

    class FakeGenerator:
        def __init__(self) -> None:
            self.calls = 0
            self.releases = 0

        def complete(self, prompt: str, **kwargs: object) -> str:
            del prompt, kwargs
            self.calls += 1
            return json.dumps(_annotation("clean", self.calls))

        def release(self) -> None:
            self.releases += 1

    generator = FakeGenerator()
    monkeypatch.setattr(
        "far.experiments.type_mappability.build_generator",
        lambda value: generator,
    )
    monkeypatch.setattr(
        "far.experiments.type_mappability._llm_runtime_identity",
        lambda value: {"ollama_model": {"digest": "sha256:" + "4" * 64}},
    )

    result = prelabel_packet(packet, config)

    assert result["samples"] == 217
    assert generator.calls == 217
    assert generator.releases == 1
    assert (packet / "machine_prelabel_checkpoint.jsonl").is_file()
    assert (packet / "machine_prelabel_work_identity.json").is_file()
    status = packet_status(packet)
    assert status["machine_prelabels"]["complete"] is True
    assert status["ready_to_analyze"] is False


def test_complete_packet_analysis_and_verifier_recompute_everything(tmp_path: Path) -> None:
    packet = tmp_path / "packet"
    prepare_packet(packet)
    _install_complete_synthetic_packet(packet, tmp_path)

    status = packet_status(packet)
    assert status["ready_to_analyze"] is True
    assert status["machine_prelabels"]["complete"] is True

    report_dir = tmp_path / "report"
    analyze(packet, report_dir)
    result = json.loads((report_dir / "type_mappability.json").read_text(encoding="utf-8"))
    assert result["samples"] == 217
    assert len(result["strata"]) == 6
    assert result["association"]["units"] == 6
    assert result["retrospective"] is True
    assert result["confirmatory_h4"] is False
    assert result["human_iaa_computed"] is True
    assert result["human_identity_verified"] is False
    assert result["publication_gold"] is False
    assert result["test_accessed"] is False
    assert verify_report(packet, report_dir)["valid"] is True

    result["confirmatory_h4"] = True
    write_json(report_dir / "type_mappability.json", result)
    audit = verify_report(packet, report_dir)
    assert audit["valid"] is False
    assert any("deterministic recomputation" in error for error in audit["errors"])
