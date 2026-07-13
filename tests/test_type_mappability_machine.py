from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import far.experiments.type_mappability_machine as p6m
from far.bench.build.common import sha256_file, write_json, write_jsonl
from far.experiments.type_mappability_machine import (
    JUROR_SPECS,
    P6M_MAX_ATTEMPTS,
    P6M_RESPONSE_SCHEMA,
    PROFILE,
    PROMPT_TEMPLATE_SHA256,
    PROTOCOL_PATH,
    PROTOCOL_SHA256,
    VIEW_IDS,
    _parse_p6m_response,
    _prompt,
    _source,
    analyze,
    annotate_juror,
    compute_result,
    verify_report,
)

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "diagnostics" / "type_mappability_v1"


def _annotation(label: str, mapped_type: str) -> dict[str, object]:
    if label == "clean":
        return {
            "mappability": "clean",
            "mapped_types": [mapped_type],
            "missing_concept": "",
            "rationale": "The frozen type fully describes the visible conflict.",
        }
    return {
        "mappability": "partial",
        "mapped_types": [mapped_type],
        "missing_concept": "relation_detail",
        "rationale": "The type covers part of the visible conflict but misses a key relation.",
    }


def _write_juror(
    output_dir: Path,
    juror_id: str,
    *,
    majority_id: str,
    contested_id: str,
) -> Path:
    _, items, source_sha = _source(PACKET)
    spec = JUROR_SPECS[juror_id]
    runtime: dict[str, object] = {
        "enabled": True,
        "provider": spec["provider"],
        "model": spec["model"],
    }
    if spec["provider"] == "ollama":
        runtime["ollama_model"] = {"model": spec["model"], "digest": juror_id[-1] * 64}
    identity = {
        "schema_version": "far-p6m-juror-identity-v1",
        "study_profile": PROFILE,
        "juror_id": juror_id,
        "model_family": spec["family"],
        "provider": spec["provider"],
        "model": spec["model"],
        "config_sha256": juror_id[-1] * 64,
        "llm_runtime": runtime,
        "implementation_sha256": "a" * 64,
        "source_revision": {"git_dirty": False, "git_commit": "b" * 40},
        "source_packet_manifest_sha256": source_sha,
        "protocol_sha256": PROTOCOL_SHA256,
        "prompt_template_sha256": PROMPT_TEMPLATE_SHA256,
    }
    output_dir.mkdir()
    identity_path = output_dir / "run_identity.json"
    write_json(identity_path, identity)
    rows = []
    for sample_id, item in sorted(items.items()):
        for view_id in VIEW_IDS:
            annotation = _annotation("clean", "temporal")
            if sample_id == majority_id and juror_id == "J3" and view_id == "view_b":
                annotation = _annotation("partial", "temporal")
            if sample_id == contested_id:
                if juror_id == "J2":
                    annotation = _annotation("partial", "entity")
                elif juror_id == "J3" and view_id == "view_b":
                    annotation = _annotation("partial", "numerical")
            response = json.dumps(annotation, ensure_ascii=False, sort_keys=True)
            prompt = _prompt(item, view_id)
            rows.append(
                {
                    "schema_version": "far-p6m-juror-annotation-v1",
                    "sample_id": sample_id,
                    "view_id": view_id,
                    "context_sha256": item["context_sha256"],
                    "juror_id": juror_id,
                    "model_family": spec["family"],
                    "annotation": annotation,
                    "attempts": [
                        {
                            "attempt": 1,
                            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                            "raw_response": response,
                            "raw_response_sha256": hashlib.sha256(response.encode()).hexdigest(),
                            "valid": True,
                            "validation_error": None,
                        }
                    ],
                    "human_annotator": False,
                    "publication_gold": False,
                }
            )
    annotations_path = output_dir / f"annotations_{juror_id}.jsonl"
    failures_path = output_dir / "failed_attempts.jsonl"
    write_jsonl(annotations_path, rows)
    write_jsonl(failures_path, [])
    write_json(
        output_dir / "juror_manifest.json",
        {
            "schema_version": "far-p6m-juror-manifest-v1",
            "study_profile": PROFILE,
            "protocol_sha256": PROTOCOL_SHA256,
            "prompt_template_sha256": PROMPT_TEMPLATE_SHA256,
            "source_packet_manifest_sha256": source_sha,
            "juror_id": juror_id,
            "model_family": spec["family"],
            "provider": spec["provider"],
            "model": spec["model"],
            "config_sha256": identity["config_sha256"],
            "samples": len(items),
            "views_per_sample": len(VIEW_IDS),
            "rows": len(rows),
            "expected_samples": len(items),
            "expected_rows": len(items) * len(VIEW_IDS),
            "complete": True,
            "annotation_file": annotations_path.name,
            "annotation_sha256": sha256_file(annotations_path),
            "failed_attempt_file": failures_path.name,
            "failed_attempts": 0,
            "failed_attempt_sha256": sha256_file(failures_path),
            "run_identity_sha256": sha256_file(identity_path),
            "qwen_prelabels_used": False,
            "human_annotator": False,
            "human_annotation_replaced": False,
            "human_iaa_computed": False,
            "publication_gold": False,
            "test_accessed": False,
        },
    )
    return output_dir


def _jurors(tmp_path: Path) -> tuple[list[Path], str, str]:
    _, items, _ = _source(PACKET)
    majority_id, contested_id = sorted(items)[:2]
    paths = [
        _write_juror(
            tmp_path / juror_id.lower(),
            juror_id,
            majority_id=majority_id,
            contested_id=contested_id,
        )
        for juror_id in sorted(JUROR_SPECS)
    ]
    return paths, majority_id, contested_id


def test_p6m_protocol_fingerprint_and_views_are_frozen() -> None:
    assert sha256_file(PROTOCOL_PATH) == PROTOCOL_SHA256
    _, items, _ = _source(PACKET)
    item = items[sorted(items)[0]]
    prompt_a = _prompt(item, "view_a")
    prompt_b = _prompt(item, "view_b")
    assert prompt_a != prompt_b
    evidence_ids = [entry["evidence_id"] for entry in item["evidence"]]
    for evidence_id in evidence_ids:
        assert prompt_a.count(evidence_id) == 1
        assert prompt_b.count(evidence_id) == 1


def test_p6m_parser_extracts_one_object_but_keeps_schema_fail_closed() -> None:
    annotation = _annotation("clean", "temporal")
    response = f"Preface\n```json\n{json.dumps(annotation)}\n```\nTrailing prose"
    assert _parse_p6m_response(response, sample_id="sample") == annotation
    with pytest.raises(ValueError, match="mapped_types must be unique"):
        _parse_p6m_response(
            json.dumps({**annotation, "mapped_types": ["temporal", "temporal"]}),
            sample_id="sample",
        )
    assert P6M_RESPONSE_SCHEMA["properties"]["mapped_types"]["maxItems"] == 7
    assert "uniqueItems" not in P6M_RESPONSE_SCHEMA["properties"]["mapped_types"]


def test_p6m_consensus_preserves_majority_and_contested_layers(tmp_path: Path) -> None:
    jurors, majority_id, contested_id = _jurors(tmp_path)
    result, rows = compute_result(PACKET, jurors)
    by_id = {row["sample_id"]: row for row in rows}
    assert result["study_profile"] == PROFILE
    assert result["dispositions"] == {
        "contested": 1,
        "majority": 1,
        "unanimous": 215,
    }
    assert by_id[majority_id]["disposition"] == "majority"
    assert by_id[majority_id]["stable_juror_count"] == 2
    assert by_id[contested_id]["disposition"] == "contested"
    assert by_id[contested_id]["consensus_annotation"] is None
    assert result["consensus_samples"] == 216
    assert result["human_annotation_replaced"] is False
    assert result["human_iaa_computed"] is False
    assert result["publication_gold"] is False
    assert result["qwen_prelabels_used"] is False


def test_p6m_report_verifies_and_tampering_fails_closed(tmp_path: Path) -> None:
    jurors, _, _ = _jurors(tmp_path)
    report_dir = tmp_path / "report"
    manifest = analyze(PACKET, jurors, report_dir)
    assert manifest["human_annotation_replaced"] is False
    assert verify_report(PACKET, jurors, report_dir)["valid"] is True
    report_path = report_dir / "type_mappability_machine.md"
    report_path.write_text(report_path.read_text() + "tampered\n")
    audit = verify_report(PACKET, jurors, report_dir)
    assert audit["valid"] is False
    assert any("differs from deterministic recomputation" in error for error in audit["errors"])


def test_p6m_rejects_reused_juror_identity(tmp_path: Path) -> None:
    jurors, _, _ = _jurors(tmp_path)
    try:
        compute_result(PACKET, [jurors[0], jurors[0], jurors[2]])
    except ValueError as exc:
        assert "three frozen distinct identities" in str(exc)
    else:
        raise AssertionError("P6-M accepted a reused juror identity")


def test_p6m_annotation_runner_writes_two_views_without_a_real_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeGenerator:
        def __init__(self) -> None:
            self.prompts: list[str] = []
            self.calls: list[dict[str, object]] = []
            self.released = False

        def complete(self, prompt: str, **kwargs: object) -> str:
            self.prompts.append(prompt)
            self.calls.append(kwargs)
            return json.dumps(_annotation("clean", "temporal"), sort_keys=True)

        def release(self) -> None:
            self.released = True

    generator = FakeGenerator()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("llm:\n  max_tokens: 1200\n")
    runtime = {
        "enabled": True,
        "provider": "ollama",
        "model": "mistral:7b-instruct",
        "ollama_model": {"model": "mistral:7b-instruct", "digest": "1" * 64},
    }
    monkeypatch.setattr(p6m, "build_generator", lambda _: generator)
    monkeypatch.setattr(
        p6m,
        "_validate_runtime",
        lambda _config, _juror: (JUROR_SPECS["J1"], runtime),
    )
    monkeypatch.setattr(
        p6m,
        "_source_revision",
        lambda: {"git_dirty": False, "git_commit": "c" * 40},
    )
    output_dir = tmp_path / "juror"
    manifest = annotate_juror(
        PACKET,
        config_path,
        output_dir,
        juror_id="J1",
        limit=1,
        resume=True,
    )
    assert manifest["complete"] is False
    assert manifest["rows"] == 2
    assert manifest["failed_attempts"] == 0
    assert len(generator.prompts) == 2
    assert generator.prompts[0] != generator.prompts[1]
    assert all(call["response_format"] == P6M_RESPONSE_SCHEMA for call in generator.calls)
    assert all(call["max_tokens"] == 1200 for call in generator.calls)
    assert generator.released is True

    unowned = tmp_path / "unowned"
    unowned.mkdir()
    (unowned / "foreign.txt").write_text("foreign")
    with pytest.raises(ValueError, match="without a P6-M run identity"):
        annotate_juror(
            PACKET,
            config_path,
            unowned,
            juror_id="J1",
            limit=1,
            resume=True,
        )


def test_p6m_terminal_failures_are_fsynced_and_retries_do_not_nest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class InvalidGenerator:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        def complete(self, prompt: str, **_: object) -> str:
            self.prompts.append(prompt)
            return "not-json"

    generator = InvalidGenerator()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("llm:\n  max_tokens: 1200\n")
    runtime = {
        "enabled": True,
        "provider": "ollama",
        "model": "mistral:7b-instruct",
        "ollama_model": {"model": "mistral:7b-instruct", "digest": "1" * 64},
    }
    monkeypatch.setattr(p6m, "build_generator", lambda _: generator)
    monkeypatch.setattr(
        p6m,
        "_validate_runtime",
        lambda _config, _juror: (JUROR_SPECS["J1"], runtime),
    )
    monkeypatch.setattr(
        p6m,
        "_source_revision",
        lambda: {"git_dirty": False, "git_commit": "d" * 40},
    )
    output_dir = tmp_path / "failed-juror"
    with pytest.raises(ValueError, match=f"invalid after {P6M_MAX_ATTEMPTS} attempts"):
        annotate_juror(
            PACKET,
            config_path,
            output_dir,
            juror_id="J1",
            limit=1,
            resume=True,
        )
    failures = [
        json.loads(line) for line in (output_dir / "failed_attempts.jsonl").read_text().splitlines()
    ]
    assert len(failures) == P6M_MAX_ATTEMPTS
    assert [row["sequence"] for row in failures] == list(range(1, P6M_MAX_ATTEMPTS + 1))
    assert len(generator.prompts) == P6M_MAX_ATTEMPTS
    assert all(prompt.count("Your preceding response") == 1 for prompt in generator.prompts[1:])
