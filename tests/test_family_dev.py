from __future__ import annotations

import json

from bench.build.common import sha256_file
from experiments.evidence_family_dev import verify_release
from experiments.family_dev import _cluster_bootstrap, prepare_dev_view
from experiments.protocol_family_dev import (
    FAMILY_DEV_ACTIVE_SHA256,
    FAMILY_DEV_PLAN,
    verify_family_protocol,
)


def test_family_dev_protocol_and_config_parity_are_frozen() -> None:
    audit = verify_family_protocol()
    assert audit["valid"] is True
    assert audit["required_claim_level"] == "directional_reproduction"
    assert sha256_file(FAMILY_DEV_PLAN) == FAMILY_DEV_ACTIVE_SHA256


def test_dev_view_contains_only_sixty_dev_rows(tmp_path) -> None:
    output = tmp_path / "dev-view"
    manifest = prepare_dev_view(output)
    rows = [json.loads(line) for line in (output / "falsirag_bench.jsonl").read_text().splitlines()]
    assert manifest["contains_test"] is False
    assert manifest["contains_train"] is False
    assert len(rows) == 60
    assert {row["split"] for row in rows} == {"dev"}


def test_family_cluster_bootstrap_is_deterministic() -> None:
    values = {
        "mistral": [0.1] * 60,
        "google": [0.2] * 60,
        "meta": [-0.1] * 60,
    }
    first = _cluster_bootstrap(values)
    second = _cluster_bootstrap(values)
    assert first == second
    assert first["clusters"] == 3
    assert first["lower"] <= first["upper"]


def test_family_dev_verifier_fails_closed_without_release(tmp_path) -> None:
    audit = verify_release(tmp_path / "missing")
    assert audit["valid"] is False
    assert audit["gate_f_passed"] is False
    assert audit["test_accessed"] is False
