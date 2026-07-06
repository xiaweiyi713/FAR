"""Deterministic bootstrap intervals and paired exact tests.

The resampling discipline is adapted from VeraRAG's MIT-licensed
``src/evaluation/statistics.py`` and specialized for FalsiRAG row schemas.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def stratified_bootstrap_ci(
    rows: list[dict[str, Any]],
    metric: str,
    *,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 1729,
    strata_key: str = "category",
) -> dict[str, Any]:
    if not rows or resamples < 1:
        raise ValueError("bootstrap requires rows and at least one resample")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    strata: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get(metric)
        if value is not None:
            strata[str(row[strata_key])].append(float(value))
    if not strata:
        raise ValueError(f"metric {metric} has no defined values")
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        sampled = [
            rng.choice(values) for _, values in sorted(strata.items()) for _ in range(len(values))
        ]
        estimates.append(sum(sampled) / len(sampled))
    observed_values = [value for values in strata.values() for value in values]
    alpha = (1.0 - confidence) / 2.0
    return {
        "method": "stratified-percentile-bootstrap-v1",
        "metric": metric,
        "estimate": sum(observed_values) / len(observed_values),
        "lower": _percentile(estimates, alpha),
        "upper": _percentile(estimates, 1.0 - alpha),
        "confidence": confidence,
        "resamples": resamples,
        "seed": seed,
        "strata": {key: len(values) for key, values in sorted(strata.items())},
    }


def paired_bootstrap_comparison(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    metric: str,
    *,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 1729,
    higher_is_better: bool = True,
) -> dict[str, Any]:
    if resamples < 1:
        raise ValueError("paired bootstrap requires at least one resample")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    if len({str(row["sample_id"]) for row in baseline_rows}) != len(baseline_rows):
        raise ValueError("baseline rows contain duplicate sample IDs")
    if len({str(row["sample_id"]) for row in candidate_rows}) != len(candidate_rows):
        raise ValueError("candidate rows contain duplicate sample IDs")
    baseline = {str(row["sample_id"]): row for row in baseline_rows}
    candidate = {str(row["sample_id"]): row for row in candidate_rows}
    if set(baseline) != set(candidate):
        raise ValueError("paired comparison requires identical sample IDs")
    pairs = [
        (
            float(baseline[sample_id][metric]),
            float(candidate[sample_id][metric]),
            str(candidate[sample_id]["category"]),
        )
        for sample_id in sorted(baseline)
        if baseline[sample_id].get(metric) is not None
        and candidate[sample_id].get(metric) is not None
    ]
    if not pairs:
        raise ValueError(f"metric {metric} has no aligned values")
    by_category: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for baseline_value, candidate_value, category in pairs:
        by_category[category].append((baseline_value, candidate_value))
    rng = random.Random(seed)
    differences: list[float] = []
    for _ in range(resamples):
        sampled = [
            rng.choice(values)
            for _, values in sorted(by_category.items())
            for _ in range(len(values))
        ]
        differences.append(sum(candidate - base for base, candidate in sampled) / len(sampled))
    observed = sum(candidate - base for base, candidate, _ in pairs) / len(pairs)
    alpha = (1.0 - confidence) / 2.0
    return {
        "method": "paired-stratified-percentile-bootstrap-v1",
        "metric": metric,
        "candidate_minus_baseline": observed,
        "lower": _percentile(differences, alpha),
        "upper": _percentile(differences, 1.0 - alpha),
        "higher_is_better": higher_is_better,
        "probability_candidate_better": sum(
            value > 0 if higher_is_better else value < 0 for value in differences
        )
        / len(differences),
        "confidence": confidence,
        "resamples": resamples,
        "seed": seed,
        "pairs": len(pairs),
    }


def _typed_conflict_f1(rows: list[dict[str, Any]]) -> float:
    rows = [row for row in rows if row.get("typed_conflict_correct") is not None]
    true_positives = sum(
        int(row["typed_conflict_correct"])
        for row in rows
        if bool(row.get("gold_conflict_present", True))
    )
    predicted = sum(int(row["predicted_conflict_count"]) for row in rows)
    gold = sum(bool(row.get("gold_conflict_present", True)) for row in rows)
    denominator = predicted + gold
    return 2 * true_positives / denominator if denominator else 0.0


def _conflict_presence_f1(rows: list[dict[str, Any]]) -> float:
    true_positives = sum(
        int(bool(row.get("predicted_conflict_count")))
        for row in rows
        if bool(row.get("gold_conflict_present", True))
    )
    predicted = sum(bool(row.get("predicted_conflict_count")) for row in rows)
    gold = sum(bool(row.get("gold_conflict_present", True)) for row in rows)
    denominator = predicted + gold
    return 2 * true_positives / denominator if denominator else 0.0


def stratified_conflict_presence_f1_ci(
    rows: list[dict[str, Any]],
    *,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 1729,
    strata_key: str = "category",
) -> dict[str, Any]:
    if not rows or resamples < 1:
        raise ValueError("bootstrap requires rows and at least one resample")
    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        strata[str(row[strata_key])].append(row)
    rng = random.Random(seed)
    estimates = [
        _conflict_presence_f1(
            [rng.choice(values) for _, values in sorted(strata.items()) for _ in range(len(values))]
        )
        for _ in range(resamples)
    ]
    alpha = (1.0 - confidence) / 2.0
    return {
        "method": "stratified-percentile-bootstrap-conflict-presence-f1-v1",
        "metric": "conflict_presence_f1",
        "estimate": _conflict_presence_f1(rows),
        "lower": _percentile(estimates, alpha),
        "upper": _percentile(estimates, 1.0 - alpha),
        "confidence": confidence,
        "resamples": resamples,
        "seed": seed,
        "strata": {key: len(values) for key, values in sorted(strata.items())},
    }


def paired_conflict_presence_f1_comparison(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    *,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 1729,
) -> dict[str, Any]:
    baseline = {str(row["sample_id"]): row for row in baseline_rows}
    candidate = {str(row["sample_id"]): row for row in candidate_rows}
    if set(baseline) != set(candidate) or not baseline:
        raise ValueError("paired comparison requires identical non-empty sample IDs")
    by_category: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for sample_id in sorted(baseline):
        by_category[str(candidate[sample_id]["category"])].append(
            (baseline[sample_id], candidate[sample_id])
        )
    rng = random.Random(seed)
    differences = []
    for _ in range(resamples):
        sampled = [
            rng.choice(values)
            for _, values in sorted(by_category.items())
            for _ in range(len(values))
        ]
        differences.append(
            _conflict_presence_f1([candidate_row for _, candidate_row in sampled])
            - _conflict_presence_f1([baseline_row for baseline_row, _ in sampled])
        )
    observed = _conflict_presence_f1(candidate_rows) - _conflict_presence_f1(baseline_rows)
    alpha = (1.0 - confidence) / 2.0
    return {
        "method": "paired-stratified-percentile-bootstrap-conflict-presence-f1-v1",
        "metric": "conflict_presence_f1",
        "candidate_minus_baseline": observed,
        "lower": _percentile(differences, alpha),
        "upper": _percentile(differences, 1.0 - alpha),
        "higher_is_better": True,
        "probability_candidate_better": sum(value > 0 for value in differences) / len(differences),
        "confidence": confidence,
        "resamples": resamples,
        "seed": seed,
        "pairs": len(baseline),
    }


def stratified_typed_conflict_f1_ci(
    rows: list[dict[str, Any]],
    *,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 1729,
    strata_key: str = "category",
) -> dict[str, Any]:
    """Bootstrap the corpus-level typed conflict F1 rather than a row proxy."""

    if not rows or resamples < 1:
        raise ValueError("bootstrap requires rows and at least one resample")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        strata[str(row[strata_key])].append(row)
    rng = random.Random(seed)
    estimates = []
    for _ in range(resamples):
        sampled = [
            rng.choice(values) for _, values in sorted(strata.items()) for _ in range(len(values))
        ]
        estimates.append(_typed_conflict_f1(sampled))
    alpha = (1.0 - confidence) / 2.0
    return {
        "method": "stratified-percentile-bootstrap-typed-f1-v1",
        "metric": "typed_conflict_f1",
        "estimate": _typed_conflict_f1(rows),
        "lower": _percentile(estimates, alpha),
        "upper": _percentile(estimates, 1.0 - alpha),
        "confidence": confidence,
        "resamples": resamples,
        "seed": seed,
        "strata": {key: len(values) for key, values in sorted(strata.items())},
    }


def paired_typed_conflict_f1_comparison(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    *,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 1729,
) -> dict[str, Any]:
    """Paired stratified bootstrap for the nonlinear typed-conflict F1."""

    if resamples < 1:
        raise ValueError("paired bootstrap requires at least one resample")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    if len({str(row["sample_id"]) for row in baseline_rows}) != len(baseline_rows):
        raise ValueError("baseline rows contain duplicate sample IDs")
    if len({str(row["sample_id"]) for row in candidate_rows}) != len(candidate_rows):
        raise ValueError("candidate rows contain duplicate sample IDs")
    baseline = {str(row["sample_id"]): row for row in baseline_rows}
    candidate = {str(row["sample_id"]): row for row in candidate_rows}
    if set(baseline) != set(candidate) or not baseline:
        raise ValueError("paired comparison requires identical non-empty sample IDs")
    by_category: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for sample_id in sorted(baseline):
        by_category[str(candidate[sample_id]["category"])].append(
            (baseline[sample_id], candidate[sample_id])
        )
    rng = random.Random(seed)
    differences = []
    for _ in range(resamples):
        sampled_pairs = [
            rng.choice(values)
            for _, values in sorted(by_category.items())
            for _ in range(len(values))
        ]
        differences.append(
            _typed_conflict_f1([candidate_row for _, candidate_row in sampled_pairs])
            - _typed_conflict_f1([baseline_row for baseline_row, _ in sampled_pairs])
        )
    observed = _typed_conflict_f1(candidate_rows) - _typed_conflict_f1(baseline_rows)
    alpha = (1.0 - confidence) / 2.0
    return {
        "method": "paired-stratified-percentile-bootstrap-typed-f1-v1",
        "metric": "typed_conflict_f1",
        "candidate_minus_baseline": observed,
        "lower": _percentile(differences, alpha),
        "upper": _percentile(differences, 1.0 - alpha),
        "higher_is_better": True,
        "probability_candidate_better": sum(value > 0 for value in differences) / len(differences),
        "confidence": confidence,
        "resamples": resamples,
        "seed": seed,
        "pairs": len(baseline),
    }


def mcnemar_exact(
    baseline_success: list[bool],
    candidate_success: list[bool],
) -> dict[str, Any]:
    if len(baseline_success) != len(candidate_success) or not baseline_success:
        raise ValueError("McNemar requires non-empty aligned outcomes")
    baseline_only = sum(
        base and not candidate
        for base, candidate in zip(baseline_success, candidate_success, strict=True)
    )
    candidate_only = sum(
        candidate and not base
        for base, candidate in zip(baseline_success, candidate_success, strict=True)
    )
    discordant = baseline_only + candidate_only
    if discordant == 0:
        p_value = 1.0
    else:
        tail = min(baseline_only, candidate_only)
        cumulative = sum(math.comb(discordant, value) for value in range(tail + 1))
        p_value = min(1.0, 2.0 * cumulative / (2**discordant))
    return {
        "method": "exact-two-sided-mcnemar-v1",
        "baseline_only": baseline_only,
        "candidate_only": candidate_only,
        "discordant": discordant,
        "p_value": p_value,
    }


def dependency_cluster_bootstrap_ci(
    rows: list[dict[str, Any]],
    metric: str,
    *,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 1729,
    cluster_key: str = "dependency_group",
) -> dict[str, Any]:
    """Resample complete source-document groups to respect shared evidence."""
    if not rows or resamples < 1:
        raise ValueError("cluster bootstrap requires rows and at least one resample")
    clusters: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get(metric)
        cluster = row.get(cluster_key)
        if value is not None and cluster is not None:
            clusters[str(cluster)].append(float(value))
    if not clusters:
        raise ValueError(f"metric {metric} has no clustered values")
    cluster_ids = sorted(clusters)
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        sampled_ids = [rng.choice(cluster_ids) for _ in cluster_ids]
        sampled = [value for cluster_id in sampled_ids for value in clusters[cluster_id]]
        estimates.append(sum(sampled) / len(sampled))
    observed = [value for values in clusters.values() for value in values]
    alpha = (1.0 - confidence) / 2.0
    return {
        "method": "source-dependency-cluster-bootstrap-v1",
        "metric": metric,
        "estimate": sum(observed) / len(observed),
        "lower": _percentile(estimates, alpha),
        "upper": _percentile(estimates, 1.0 - alpha),
        "confidence": confidence,
        "resamples": resamples,
        "seed": seed,
        "clusters": len(clusters),
    }


def dependency_cluster_typed_conflict_f1_ci(
    rows: list[dict[str, Any]],
    *,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 1729,
    cluster_key: str = "dependency_group",
) -> dict[str, Any]:
    """Cluster-resample the nonlinear typed conflict F1 sensitivity interval."""

    if not rows or resamples < 1:
        raise ValueError("cluster bootstrap requires rows and at least one resample")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cluster = row.get(cluster_key)
        if cluster is not None:
            clusters[str(cluster)].append(row)
    if not clusters:
        raise ValueError("typed_conflict_f1 has no clustered rows")
    cluster_ids = sorted(clusters)
    rng = random.Random(seed)
    estimates = []
    for _ in range(resamples):
        sampled_ids = [rng.choice(cluster_ids) for _ in cluster_ids]
        sampled = [row for cluster_id in sampled_ids for row in clusters[cluster_id]]
        estimates.append(_typed_conflict_f1(sampled))
    alpha = (1.0 - confidence) / 2.0
    return {
        "method": "source-dependency-cluster-bootstrap-typed-f1-v1",
        "metric": "typed_conflict_f1",
        "estimate": _typed_conflict_f1(rows),
        "lower": _percentile(estimates, alpha),
        "upper": _percentile(estimates, 1.0 - alpha),
        "confidence": confidence,
        "resamples": resamples,
        "seed": seed,
        "clusters": len(clusters),
    }


def dependency_cluster_conflict_presence_f1_ci(
    rows: list[dict[str, Any]],
    *,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 1729,
    cluster_key: str = "dependency_group",
) -> dict[str, Any]:
    if not rows or resamples < 1:
        raise ValueError("cluster bootstrap requires rows and at least one resample")
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cluster = row.get(cluster_key)
        if cluster is not None:
            clusters[str(cluster)].append(row)
    if not clusters:
        raise ValueError("conflict_presence_f1 has no clustered rows")
    cluster_ids = sorted(clusters)
    rng = random.Random(seed)
    estimates = []
    for _ in range(resamples):
        sampled_ids = [rng.choice(cluster_ids) for _ in cluster_ids]
        sampled = [row for cluster_id in sampled_ids for row in clusters[cluster_id]]
        estimates.append(_conflict_presence_f1(sampled))
    alpha = (1.0 - confidence) / 2.0
    return {
        "method": "source-dependency-cluster-bootstrap-conflict-presence-f1-v1",
        "metric": "conflict_presence_f1",
        "estimate": _conflict_presence_f1(rows),
        "lower": _percentile(estimates, alpha),
        "upper": _percentile(estimates, 1.0 - alpha),
        "confidence": confidence,
        "resamples": resamples,
        "seed": seed,
        "clusters": len(clusters),
    }
