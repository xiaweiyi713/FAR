from __future__ import annotations

from pathlib import Path

import pytest

from far.experiments.power import (
    exact_mcnemar_power,
    minimum_detectable_effect,
    simulate_mcnemar_power,
    simulate_stratified_power,
    verify_release,
)


def test_exact_power_increases_with_effect_and_sample_size() -> None:
    low = exact_mcnemar_power(60, 0.30, 0.05)
    stronger = exact_mcnemar_power(60, 0.30, 0.15)
    larger = exact_mcnemar_power(180, 0.30, 0.05)
    assert 0.0 <= low < stronger <= 1.0
    assert low < larger <= 1.0


def test_exact_and_simulated_mcnemar_power_agree() -> None:
    result = simulate_mcnemar_power(
        80,
        0.30,
        0.10,
        simulations=20_000,
        seed=7,
    )
    assert abs(result["power"] - result["exact_power"]) < 0.02


def test_minimum_detectable_effect_reaches_target() -> None:
    effect = minimum_detectable_effect(180, 0.30, target_power=0.60)
    assert effect is not None
    assert exact_mcnemar_power(180, 0.30, effect) >= 0.60
    assert exact_mcnemar_power(180, 0.30, effect - 2e-5) < 0.60


def test_impossible_effect_is_rejected() -> None:
    with pytest.raises(ValueError):
        exact_mcnemar_power(60, 0.10, 0.20)


def test_stratified_power_reports_all_registered_views() -> None:
    result = simulate_stratified_power(
        [{"n": 20, "discordance_rate": 0.4, "effect": 0.2}] * 3,
        simulations=200,
        bootstrap_resamples=50,
        seed=11,
    )
    assert result["families"] == 3
    assert result["pairs"] == 60
    assert 0.0 <= result["stratified_mcnemar_power"] <= 1.0
    assert 0.0 <= result["family_cluster_bootstrap_power"] <= 1.0
    assert 0.0 <= result["at_least_two_thirds_positive_probability"] <= 1.0


def test_power_verifier_fails_closed_without_release(tmp_path: Path) -> None:
    audit = verify_release(tmp_path / "missing", tmp_path / "missing.md")
    assert audit["valid"] is False
    assert audit["gate_p_completed"] is False
