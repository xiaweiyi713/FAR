from __future__ import annotations

import json
from pathlib import Path

import pytest

from far.bench.build.common import read_jsonl, write_jsonl
from far.experiments import selective_acceptance as study
from far.experiments.selective_acceptance import (
    CATEGORIES,
    OPERATIONAL_FIELDS,
    _calibration_gate,
    _choose_policy,
    _enrichment_bootstrap,
    _policy_summary,
    build_packet,
    prereg_commit,
    reference_free_features,
    render_markdown,
    verify_packet,
    verify_protocol,
)

ROOT = Path(__file__).resolve().parents[1]


def test_protocol_freezes_balanced_group_disjoint_split() -> None:
    audit = verify_protocol(require_tag=False)

    assert audit["valid"] is True
    assert audit["calibration_samples"] == 60
    assert audit["evaluation_samples"] == 60
    assert audit["reference_free_operational_input"] is True
    assert audit["post_generation_policy"] is True
    assert audit["performance_amendment"] is True
    assert audit["fresh_restart_after_retired_v1"] is True
    assert audit["retired_v1_complete_checkpoint_rows"] == 10
    assert audit["retired_v1_rows_reused"] == 0
    assert audit["unload_after_sample"] is False
    assert audit["keep_alive"] == "24h"
    assert audit["test_accessed"] is False
    assert audit["local_model_execution"] is False


def test_packet_contains_only_operational_train_fields(tmp_path: Path) -> None:
    packet_dir = tmp_path / "packet"
    manifest = build_packet(packet_dir, source_commit=prereg_commit(required=False))
    rows = read_jsonl(packet_dir / "falsirag_bench.jsonl")

    assert len(rows) == 120
    assert len({row["id"] for row in rows}) == 120
    assert all(set(row) == OPERATIONAL_FIELDS for row in rows)
    assert {row["split"] for row in rows} == {"train"}
    assert set(manifest["split"]["category_counts"]) == {"calibration", "evaluation"}
    for counts in manifest["split"]["category_counts"].values():
        assert counts == {category: 12 for category in CATEGORIES}
    assert not (
        set(manifest["split"]["calibration_dependency_groups"])
        & set(manifest["split"]["evaluation_dependency_groups"])
    )
    assert manifest["fresh_restart_after_retired_v1"] is True
    assert manifest["retired_v1_checkpoint_rows_reused"] == 0
    assert verify_packet(packet_dir, require_tag=False)["valid"] is True


def test_v2_runtime_uses_fresh_keepalive_configuration() -> None:
    config = study.CONFIG_PATH.read_text(encoding="utf-8")

    assert "unload_after_sample: false" in config
    assert "keep_alive: 24h" in config
    assert "qwen_selective_acceptance_v2.sqlite3" in config
    assert "far-qwen3.5-9b-selective-acceptance-v2" in config
    assert "qwen_open.sqlite3" not in config


def test_formal_v2_runner_rejects_retired_v1_output_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="selective_acceptance_v2 output root"):
        study.run_registered(tmp_path / "selective_acceptance_v1")


def test_formal_v2_runner_rejects_unbound_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = tmp_path / "unknown.sqlite3"
    cache.write_bytes(b"unknown")
    monkeypatch.setattr(study, "V2_CACHE_PATH", cache)

    with pytest.raises(ValueError, match="pre-existing unbound v2 cache"):
        study.run_registered(tmp_path / "selective_acceptance_v2")


def test_packet_verifier_rejects_reference_injection(tmp_path: Path) -> None:
    packet_dir = tmp_path / "packet"
    build_packet(packet_dir, source_commit=None)
    path = packet_dir / "falsirag_bench.jsonl"
    rows = read_jsonl(path)
    rows[0]["expected_revision"] = {"revised_answer": "leak"}
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    audit = verify_packet(packet_dir, require_tag=False)

    assert audit["valid"] is False
    assert any("falsirag_bench.jsonl" in error for error in audit["errors"])
    assert any("non-operational fields" in error for error in audit["errors"])


def test_reference_free_features_ignore_construction_fields() -> None:
    prediction = {
        "answer": "The corrected value is 20.",
        "metadata": {
            "primary_revision_trace": {
                "before": "The value is 10.",
                "after": "The corrected value is 20.",
                "changed": True,
                "confidence": 0.9,
                "action": "replace_numerical",
            }
        },
    }
    sample = {
        "initial_answer": "The value is 10.",
        "expected_revision": {"revised_answer": "SECRET A"},
        "conflict_type": "SECRET B",
    }
    changed_labels = {
        **sample,
        "expected_revision": {"revised_answer": "DIFFERENT SECRET"},
        "conflict_type": "DIFFERENT",
    }

    assert reference_free_features(sample, prediction) == reference_free_features(
        changed_labels, prediction
    )


def test_registered_policy_selection_can_pass_only_on_calibration_outcomes() -> None:
    rows = []
    for index in range(60):
        good = index < 30
        rows.append(
            {
                "sample_id": f"S{index:03d}",
                "category": CATEGORIES[index % len(CATEGORIES)],
                "features": {
                    "changed_non_keep": True,
                    "primary_confidence": 0.9 if good else 0.7,
                    "edit_fraction": 0.2 if good else 0.8,
                    "trace_consistency_margin": 0.25 if good else -0.1,
                },
                "typed_answer_soft_f1": 0.8,
                "typed_revision_delta_f1": 0.5 if good else 0.0,
                "typed_trace_target_complete": 1.0 if good else 0.0,
                "typed_trace_collateral_edit": 0.0 if good else 1.0,
                "preserve_answer_soft_f1": 0.98,
                "preserve_revision_delta_f1": 0.0,
            }
        )

    selected, candidates = _choose_policy(rows)
    gate = _calibration_gate(selected)

    assert candidates == 100
    assert selected is not None
    assert selected["coverage"] == 0.5
    assert selected["selected_delta_enrichment"] == 0.25
    assert all(gate.values())


def test_tracked_v2_result_recomputes_registered_success() -> None:
    report = json.loads((ROOT / "reports/selective_acceptance.json").read_text(encoding="utf-8"))
    selected, candidates = _choose_policy(report["calibration"]["rows"])

    assert candidates == 100
    assert selected == report["calibration"]["selected_policy"]
    assert selected is not None
    assert all(_calibration_gate(selected).values())
    assert (
        _policy_summary(report["evaluation"]["rows"], selected["policy"])
        == report["evaluation"]["summary"]
    )
    assert (
        _enrichment_bootstrap(report["evaluation"]["rows"], selected["policy"])
        == report["evaluation"]["enrichment_bootstrap"]
    )
    assert report["registered_outcome"] == "evaluation_success"
    assert report["run"]["source_revision"] == {
        "git_commit": "04b60a75960d24f911bef4889e2639e238457ccd",
        "git_dirty": False,
    }
    assert report["protocol"]["retired_v1_rows_reused"] == 0
    assert report["boundaries"]["local_model_execution"] is False
    assert report["boundaries"]["test_accessed"] is False
    assert (ROOT / "reports/selective_acceptance.md").read_text(
        encoding="utf-8"
    ) == render_markdown(report)


def test_full_report_path_keeps_evaluation_separate_until_calibration_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet_dir = tmp_path / "packet"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest = build_packet(packet_dir, source_commit=None)
    train = {row["id"]: row for row in read_jsonl(ROOT / "bench/splits/train.jsonl")}
    good_ids = {
        *manifest["split"]["calibration_ids"][:30],
        *manifest["split"]["evaluation_ids"][:30],
    }
    predictions = []
    for sample_id in sorted(
        manifest["split"]["calibration_ids"] + manifest["split"]["evaluation_ids"]
    ):
        sample = train[sample_id]
        good = sample_id in good_ids
        initial = sample["initial_answer"]
        reference = sample["expected_revision"]["revised_answer"]
        action = sample["expected_revision"]["action"] if good else "keep"
        trace = {
            "action": action,
            "after": reference if good else initial,
            "before": initial,
            "changed": good,
            "claim_id": "C1",
            "confidence": 0.9 if good else 0.7,
            "conflict_types": [sample["conflict_type"]] if good else [],
            "evidence_ids": [],
            "rationale": "synthetic registered-path test",
        }
        predictions.append(
            {
                "sample_id": sample_id,
                "method": "far",
                "answer": reference if good else initial,
                "evidence_ids": [],
                "predicted_conflict_types": [sample["conflict_type"]] if good else [],
                "revision_action": action,
                "metadata": {
                    "primary_revision_trace": trace,
                    "revision_trace": [trace],
                },
            }
        )
    write_jsonl(run_dir / "predictions.jsonl", predictions)
    monkeypatch.setattr(
        study,
        "_validate_run",
        lambda packet_dir, run_dir: {
            "checks": {"synthetic": True},
            "source_revision": {"git_commit": "synthetic", "git_dirty": False},
        },
    )
    monkeypatch.setattr(
        study,
        "verify_protocol",
        lambda require_tag=True: {"valid": True, "errors": []},
    )

    report = study.compute_report(packet_dir=packet_dir, run_dir=run_dir)

    assert report["calibration"]["gate_passed"] is True
    assert report["evaluation"]["scored"] is True
    assert report["evaluation"]["success"] is True
    assert report["registered_outcome"] == "evaluation_success"
    assert report["boundaries"]["pre_execution_selector"] is False
    assert report["boundaries"]["test_accessed"] is False


def test_remote_execution_path_is_guarded_and_never_pulls_a_model() -> None:
    prepare = (ROOT / "scripts/prepare_windows_selective_acceptance.sh").read_text(encoding="utf-8")
    preflight = (ROOT / "scripts/preflight_windows_selective_acceptance.sh").read_text(
        encoding="utf-8"
    )
    start = (ROOT / "scripts/start_windows_selective_acceptance.sh").read_text(encoding="utf-8")
    pause = (ROOT / "scripts/pause_windows_selective_acceptance.sh").read_text(encoding="utf-8")
    service = (ROOT / "scripts/systemd/far-selective-acceptance.service").read_text(
        encoding="utf-8"
    )

    assert "FAR_P14_PREP_ALLOWED" in prepare
    assert "FAR_P14_RUN_ALLOWED" in start
    assert "FAR_P14_PAUSE_ALLOWED" in pause
    assert "--query-compute-apps" in preflight
    assert "GPU busy" in preflight
    assert "is already active; inspect it instead of starting again" in preflight
    assert "Ollama is already active outside the P14 start sequence" in preflight
    assert "6488c96f" in preflight
    assert "prereg-selective-acceptance-v2" in prepare
    assert "prereg-selective-acceptance-v1" not in prepare
    assert "far-tmux-server.service" not in prepare
    assert "unknown pre-existing P14 v2 output root" in prepare
    assert "v2 cache without a bound run identity" in prepare
    assert "/mnt/d/FAR-outputs/selective_acceptance_v2" in service
    assert "/mnt/d/FAR-outputs/selective_acceptance_v1" not in service
    assert "stop --no-block far-ollama-selective-acceptance.service" in service
    assert "checkpoint retained" in pause
    assert "rm " not in pause
    assert "ollama pull" not in prepare + preflight + start + pause + service
