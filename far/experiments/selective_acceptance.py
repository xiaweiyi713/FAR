"""Run and audit the preregistered P14 selective-acceptance study.

P14 evaluates a post-generation, reference-free accept/reject controller on a
new group-disjoint train subset. Model execution is remote-only; packet
construction, scoring, and verification are deterministic and model-free.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import shutil
import subprocess
import tempfile
from collections import Counter
from itertools import product
from pathlib import Path
from statistics import mean
from typing import Any

from far.bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.eval.metrics import (
    PredictionRecord,
    revision_delta_scores,
    score_sample,
    soft_f1,
    token_edit_counters,
)
from far.experiments.revision_trace_audit import audit_row
from far.experiments.run_far import run as run_far
from far.paths import experiment_config_dir, repository_root

ROOT = repository_root()
PROTOCOL_PATH = ROOT / "docs" / "PREREG_SELECTIVE_ACCEPTANCE_2026-07-14.md"
PROTOCOL_SHA256 = "bfb9546c26b05c44e99f9d85bdc62c0eb24653dd97bd4b5924a3f9c871383e89"
AMENDMENT_PATH = ROOT / "docs" / "AMENDMENT_SELECTIVE_ACCEPTANCE_PERFORMANCE_2026-07-14.md"
AMENDMENT_SHA256 = "735daa41d6417dcf5df0b03775a7d315eaab1973a646a812fd8c2b65f6be0080"
PREREG_TAG = "prereg-selective-acceptance-v2"
RETIRED_PREREG_TAG = "prereg-selective-acceptance-v1"
SCHEMA_VERSION = "far-selective-acceptance-result-v2"
AUDIT_SCHEMA_VERSION = "far-selective-acceptance-result-audit-v2"
PACKET_SCHEMA_VERSION = "far-selective-acceptance-input-v2"
PROTOCOL_AUDIT_SCHEMA_VERSION = "far-selective-acceptance-protocol-audit-v2"
ANALYSIS_PROFILE = "preregistered-reference-free-post-generation-acceptance-v2"

TRAIN_PATH = ROOT / "bench" / "splits" / "train.jsonl"
CORPUS_PATH = ROOT / "bench" / "corpus.jsonl"
CONFIG_PATH = experiment_config_dir() / "qwen_selective_acceptance.yaml"
TRAIN_SHA256 = "7796d44fd7673c7c4a6b22cce6829f9463d72635b08d6394887945ce8e561df4"
CORPUS_SHA256 = "cca5f62db0fbb51e1bae8111ea85fe169fba7be5a8e63847a9c1c048cdae25cd"
CONFIG_SHA256 = "e0a825fbac36c21ce7dc08f73f30f6bf75e7ed5da7dac561bf964d5388bd75d9"
MODEL = "qwen3.5:9b"
MODEL_DIGEST = "6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7"
SPLIT_SEED = "far-p14-selective-acceptance-v1"
CATEGORIES = (
    "causal_overclaim",
    "entity_confusion",
    "multi_source_conflict",
    "numerical_conflict",
    "temporal_shift",
)
PARTITIONS = ("calibration", "evaluation")
ROWS_PER_CATEGORY = 12
OPERATIONAL_FIELDS = {"id", "category", "split", "question", "initial_answer"}
CONFIDENCE_GRID = (0.0, 0.75, 0.8, 0.85, 0.9)
MAX_EDIT_FRACTION_GRID = (0.2, 0.35, 0.5, 1.0, 2.0)
MIN_TRACE_MARGIN_GRID = (-1.0, 0.0, 0.1, 0.25)
MIN_COVERAGE = 0.25
MAX_COVERAGE = 0.75
MIN_ENRICHMENT = 0.03
BOOTSTRAP_SEED = 20260714
BOOTSTRAP_RESAMPLES = 2000

DEFAULT_OUTPUT_ROOT = ROOT / "outputs" / "selective_acceptance_v2"
V2_CACHE_PATH = ROOT / "outputs" / "cache" / "qwen_selective_acceptance_v2.sqlite3"
DEFAULT_REPORT_JSON = ROOT / "reports" / "selective_acceptance.json"
DEFAULT_REPORT_MARKDOWN = ROOT / "reports" / "selective_acceptance.md"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _by_id(rows: list[dict[str, Any]], *, key: str, role: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        item_id = str(row.get(key, ""))
        if not item_id or item_id in result:
            raise ValueError(f"{role} contains a missing or duplicate {key}: {item_id!r}")
        result[item_id] = row
    if not result:
        raise ValueError(f"{role} must not be empty")
    return result


def _git_output(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def prereg_commit(*, required: bool = True) -> str | None:
    try:
        commit = _git_output("rev-list", "-n", "1", PREREG_TAG)
    except (OSError, subprocess.CalledProcessError):
        if required:
            raise ValueError(f"missing preregistration tag: {PREREG_TAG}") from None
        return None
    if not commit:
        if required:
            raise ValueError(f"empty preregistration tag: {PREREG_TAG}")
        return None
    return commit


def _validate_source_rows(rows: list[dict[str, Any]]) -> None:
    counts = Counter(str(row.get("category")) for row in rows)
    if len(rows) != 182 or tuple(sorted(counts)) != CATEGORIES:
        raise ValueError("P14 requires the exact 182-row train source")
    if any(str(row.get("split")) != "train" for row in rows):
        raise ValueError("P14 source contains a non-train row")
    if any(not str(row.get("source_metadata", {}).get("dependency_group", "")) for row in rows):
        raise ValueError("P14 source row lacks a dependency group")


def _partition_rows(
    rows: list[dict[str, Any]],
) -> tuple[int, dict[str, list[dict[str, Any]]]]:
    """Select the first feasible seeded group partition without outcome access."""

    _validate_source_rows(rows)
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        group = str(row["source_metadata"]["dependency_group"])
        groups.setdefault(group, []).append(row)

    assignment: dict[str, str] | None = None
    nonce = -1
    for candidate_nonce in range(100_000):
        candidate = {
            group: PARTITIONS[
                int(_hash_text(f"{SPLIT_SEED}:partition:{candidate_nonce}:{group}"), 16) % 2
            ]
            for group in groups
        }
        available = {
            partition: Counter(
                str(row["category"])
                for group, group_rows in groups.items()
                if candidate[group] == partition
                for row in group_rows
            )
            for partition in PARTITIONS
        }
        if all(
            available[partition][category] >= ROWS_PER_CATEGORY
            for partition in PARTITIONS
            for category in CATEGORIES
        ):
            assignment = candidate
            nonce = candidate_nonce
            break
    if assignment is None:
        raise ValueError("no feasible deterministic P14 group partition found")

    selected: dict[str, list[dict[str, Any]]] = {}
    for partition in PARTITIONS:
        partition_rows = [
            row
            for row in rows
            if assignment[str(row["source_metadata"]["dependency_group"])] == partition
        ]
        chosen: list[dict[str, Any]] = []
        for category in CATEGORIES:
            eligible = [row for row in partition_rows if str(row["category"]) == category]
            eligible.sort(
                key=lambda row: (
                    _hash_text(f"{SPLIT_SEED}:select:{partition}:{row['id']}"),
                    str(row["id"]),
                )
            )
            chosen.extend(eligible[:ROWS_PER_CATEGORY])
        selected[partition] = sorted(chosen, key=lambda row: str(row["id"]))

    calibration_groups = {
        str(row["source_metadata"]["dependency_group"]) for row in selected["calibration"]
    }
    evaluation_groups = {
        str(row["source_metadata"]["dependency_group"]) for row in selected["evaluation"]
    }
    if calibration_groups & evaluation_groups:
        raise ValueError("P14 dependency groups overlap across partitions")
    for partition in PARTITIONS:
        counts = Counter(str(row["category"]) for row in selected[partition])
        if len(selected[partition]) != 60 or counts != Counter(
            {category: ROWS_PER_CATEGORY for category in CATEGORIES}
        ):
            raise ValueError(f"P14 {partition} selection is not exactly balanced")
    return nonce, selected


def _operational(row: dict[str, Any]) -> dict[str, Any]:
    operational = {
        "id": str(row["id"]),
        "category": str(row["category"]),
        "split": "train",
        "question": str(row["question"]),
        "initial_answer": str(row["initial_answer"]),
    }
    if set(operational) != OPERATIONAL_FIELDS:
        raise AssertionError("P14 operational projection changed")
    return operational


def build_packet(
    output_dir: Path,
    *,
    train_path: Path = TRAIN_PATH,
    corpus_path: Path = CORPUS_PATH,
    source_commit: str | None = None,
) -> dict[str, Any]:
    rows = read_jsonl(train_path)
    nonce, selected = _partition_rows(rows)
    operational_rows = sorted(
        [_operational(row) for partition in PARTITIONS for row in selected[partition]],
        key=lambda row: str(row["id"]),
    )
    if len({str(row["id"]) for row in operational_rows}) != 120:
        raise ValueError("P14 packet must contain 120 unique operational rows")
    output_dir.mkdir(parents=True, exist_ok=True)
    input_path = output_dir / "falsirag_bench.jsonl"
    write_jsonl(input_path, operational_rows)
    shutil.copyfile(corpus_path, output_dir / "corpus.jsonl")
    manifest = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "analysis_profile": ANALYSIS_PROFILE,
        "preregistration_tag": PREREG_TAG,
        "preregistration_commit": source_commit,
        "source": {
            "train_path": "bench/splits/train.jsonl",
            "train_sha256": sha256_file(train_path),
            "corpus_path": "bench/corpus.jsonl",
            "corpus_sha256": sha256_file(corpus_path),
            "config_path": "far/experiments/configs/qwen_selective_acceptance.yaml",
            "config_sha256": sha256_file(CONFIG_PATH),
            "model": MODEL,
            "model_digest": MODEL_DIGEST,
        },
        "split": {
            "seed": SPLIT_SEED,
            "nonce": nonce,
            "rows_per_category": ROWS_PER_CATEGORY,
            "calibration_ids": [str(row["id"]) for row in selected["calibration"]],
            "evaluation_ids": [str(row["id"]) for row in selected["evaluation"]],
            "calibration_dependency_groups": sorted(
                {str(row["source_metadata"]["dependency_group"]) for row in selected["calibration"]}
            ),
            "evaluation_dependency_groups": sorted(
                {str(row["source_metadata"]["dependency_group"]) for row in selected["evaluation"]}
            ),
            "category_counts": {
                partition: dict(
                    sorted(Counter(str(row["category"]) for row in selected[partition]).items())
                )
                for partition in PARTITIONS
            },
        },
        "operational_fields": sorted(OPERATIONAL_FIELDS),
        "operational_rows": 120,
        "operational_sha256": sha256_file(input_path),
        "allow_test": False,
        "test_accessed": False,
        "construction_references_exposed": False,
        "performance_amendment_sha256": AMENDMENT_SHA256,
        "fresh_restart_after_retired_v1": True,
        "retired_v1_checkpoint_rows_reused": 0,
    }
    write_json(output_dir / "protocol_manifest.json", manifest)
    return manifest


def verify_protocol(*, require_tag: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    for path, expected, label in (
        (PROTOCOL_PATH, PROTOCOL_SHA256, "preregistration"),
        (AMENDMENT_PATH, AMENDMENT_SHA256, "performance amendment"),
        (TRAIN_PATH, TRAIN_SHA256, "train source"),
        (CORPUS_PATH, CORPUS_SHA256, "corpus"),
        (CONFIG_PATH, CONFIG_SHA256, "configuration"),
    ):
        if not path.is_file() or sha256_file(path) != expected:
            errors.append(f"P14 {label} fingerprint mismatch")
    commit: str | None = None
    try:
        commit = prereg_commit(required=require_tag)
        if commit is not None:
            for path, expected, label in (
                (PROTOCOL_PATH, PROTOCOL_SHA256, "original preregistration"),
                (AMENDMENT_PATH, AMENDMENT_SHA256, "performance amendment"),
            ):
                tagged_protocol = subprocess.run(
                    ["git", "show", f"{commit}:docs/{path.name}"],
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                ).stdout
                if hashlib.sha256(tagged_protocol).hexdigest() != expected:
                    errors.append(f"P14 tag does not contain the frozen {label}")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        errors.append(str(exc))
    try:
        nonce, selected = _partition_rows(read_jsonl(TRAIN_PATH))
        if nonce < 0:
            errors.append("P14 split nonce is invalid")
        if {str(row["source_metadata"]["dependency_group"]) for row in selected["calibration"]} & {
            str(row["source_metadata"]["dependency_group"]) for row in selected["evaluation"]
        }:
            errors.append("P14 split leaks dependency groups")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": PROTOCOL_AUDIT_SCHEMA_VERSION,
        "valid": not errors,
        "errors": errors,
        "preregistration_tag": PREREG_TAG,
        "retired_preregistration_tag": RETIRED_PREREG_TAG,
        "preregistration_commit": commit,
        "performance_amendment": True,
        "amendment_sha256": AMENDMENT_SHA256,
        "fresh_restart_after_retired_v1": True,
        "retired_v1_complete_checkpoint_rows": 10,
        "retired_v1_rows_reused": 0,
        "calibration_samples": 60,
        "evaluation_samples": 60,
        "dependency_group_disjoint": not errors,
        "reference_free_operational_input": True,
        "post_generation_policy": True,
        "model": MODEL,
        "model_digest": MODEL_DIGEST,
        "model_execution_location": "windows-gpu",
        "local_model_execution": False,
        "unload_after_sample": False,
        "keep_alive": "24h",
        "fresh_cache_namespace": "far-qwen3.5-9b-selective-acceptance-v2",
        "test_accessed": False,
        "human_review": False,
        "publication_gold": False,
        "semantic_correctness": False,
    }


def verify_packet(packet_dir: Path, *, require_tag: bool = True) -> dict[str, Any]:
    errors = list(verify_protocol(require_tag=require_tag)["errors"])
    try:
        commit = prereg_commit(required=require_tag)
        observed_manifest = json.loads(
            (packet_dir / "protocol_manifest.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory(prefix="far-p14-packet-") as temporary:
            expected_dir = Path(temporary)
            expected_manifest = build_packet(expected_dir, source_commit=commit)
            if observed_manifest != expected_manifest:
                errors.append("P14 protocol manifest differs from deterministic rebuild")
            for name in ("falsirag_bench.jsonl", "corpus.jsonl"):
                if (packet_dir / name).read_bytes() != (expected_dir / name).read_bytes():
                    errors.append(f"P14 packet differs from deterministic rebuild: {name}")
        operational = read_jsonl(packet_dir / "falsirag_bench.jsonl")
        if any(set(row) != OPERATIONAL_FIELDS for row in operational):
            errors.append("P14 packet exposes non-operational fields")
        if any(str(row.get("split")) != "train" for row in operational):
            errors.append("P14 packet contains a non-train row")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "far-selective-acceptance-input-audit-v1",
        "valid": not errors,
        "errors": errors,
        "operational_rows": 120,
        "construction_references_exposed": False,
        "test_accessed": False,
    }


def _require_formal_source() -> str:
    commit = prereg_commit(required=True)
    if _git_output("status", "--porcelain"):
        raise ValueError("formal P14 run requires a clean worktree")
    head = _git_output("rev-parse", "HEAD")
    if head != commit:
        raise ValueError("formal P14 run must use the exact preregistration commit")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "origin/main"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return commit


def _counter_total(value: Counter[str]) -> int:
    return sum(value.values())


def reference_free_features(sample: dict[str, Any], prediction: dict[str, Any]) -> dict[str, Any]:
    """Extract registered policy features without consulting construction labels."""

    metadata = prediction.get("metadata")
    if not isinstance(metadata, dict):
        raise TypeError("P14 prediction metadata must be an object")
    primary = metadata.get("primary_revision_trace")
    if not isinstance(primary, dict):
        raise TypeError("P14 prediction requires a primary revision trace")
    before = primary.get("before")
    after = primary.get("after")
    changed = primary.get("changed")
    confidence = primary.get("confidence")
    action = primary.get("action")
    answer = prediction.get("answer")
    if (
        not isinstance(before, str)
        or not isinstance(after, str)
        or not isinstance(changed, bool)
        or not isinstance(confidence, (int, float))
        or not isinstance(action, str)
        or not isinstance(answer, str)
    ):
        raise TypeError("P14 primary trace has an invalid feature schema")
    initial = str(sample["initial_answer"])
    removed, added = token_edit_counters(initial, answer)
    _, initial_tokens = token_edit_counters("", initial)
    edit_fraction = (_counter_total(removed) + _counter_total(added)) / max(
        _counter_total(initial_tokens), 1
    )
    return {
        "changed_non_keep": bool(changed and action != "keep"),
        "primary_confidence": float(confidence),
        "edit_fraction": edit_fraction,
        "trace_consistency_margin": soft_f1(answer, after) - soft_f1(answer, before),
    }


def _policies() -> list[dict[str, float]]:
    return [
        {
            "confidence_min": confidence,
            "max_edit_fraction": edit_fraction,
            "min_trace_consistency_margin": margin,
        }
        for confidence, edit_fraction, margin in product(
            CONFIDENCE_GRID,
            MAX_EDIT_FRACTION_GRID,
            MIN_TRACE_MARGIN_GRID,
        )
    ]


def _policy_id(policy: dict[str, float]) -> str:
    return json.dumps(policy, sort_keys=True, separators=(",", ":"))


def _accept(features: dict[str, Any], policy: dict[str, float]) -> bool:
    return bool(
        features["changed_non_keep"]
        and float(features["primary_confidence"]) >= policy["confidence_min"]
        and float(features["edit_fraction"]) <= policy["max_edit_fraction"]
        and float(features["trace_consistency_margin"]) >= policy["min_trace_consistency_margin"]
    )


def _outcome_rows(
    samples: dict[str, dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
    sample_ids: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sample_id in sample_ids:
        sample = samples[sample_id]
        prediction = predictions[sample_id]
        trace = audit_row(sample, prediction)
        score = score_sample(sample, PredictionRecord.from_dict(prediction))
        reference = str(sample["expected_revision"]["revised_answer"])
        preserve_answer = str(sample["initial_answer"])
        _, _, preserve_delta = revision_delta_scores(
            preserve_answer,
            preserve_answer,
            reference,
        )
        rows.append(
            {
                "sample_id": sample_id,
                "category": str(sample["category"]),
                "features": reference_free_features(sample, prediction),
                "typed_answer_soft_f1": float(score["answer_correctness"]),
                "typed_revision_delta_f1": float(score["revision_delta_f1"]),
                "typed_trace_target_complete": float(trace["trace_target_complete"]),
                "typed_trace_collateral_edit": float(trace["trace_collateral_edit"]),
                "preserve_answer_soft_f1": soft_f1(preserve_answer, reference),
                "preserve_revision_delta_f1": preserve_delta,
            }
        )
    return rows


def _policy_summary(rows: list[dict[str, Any]], policy: dict[str, float]) -> dict[str, Any]:
    selected = [row for row in rows if _accept(row["features"], policy)]
    selected_ids = {str(row["sample_id"]) for row in selected}
    always_delta = mean(float(row["typed_revision_delta_f1"]) for row in rows)
    always_collateral = mean(float(row["typed_trace_collateral_edit"]) for row in rows)
    always_complete = mean(float(row["typed_trace_target_complete"]) for row in rows)
    return {
        "policy": policy,
        "policy_id": _policy_id(policy),
        "samples": len(rows),
        "selected_rows": len(selected),
        "coverage": len(selected) / len(rows),
        "selected_sample_ids": sorted(selected_ids),
        "selected_mean_revision_delta_f1": (
            mean(float(row["typed_revision_delta_f1"]) for row in selected) if selected else None
        ),
        "selected_collateral_rate": (
            mean(float(row["typed_trace_collateral_edit"]) for row in selected)
            if selected
            else None
        ),
        "selected_target_complete_rate": (
            mean(float(row["typed_trace_target_complete"]) for row in selected)
            if selected
            else None
        ),
        "always_typed_mean_revision_delta_f1": always_delta,
        "always_typed_collateral_rate": always_collateral,
        "always_typed_target_complete_rate": always_complete,
        "selected_delta_enrichment": (
            mean(float(row["typed_revision_delta_f1"]) for row in selected) - always_delta
            if selected
            else None
        ),
        "policy_global_answer_soft_f1": mean(
            float(row["typed_answer_soft_f1"])
            if str(row["sample_id"]) in selected_ids
            else float(row["preserve_answer_soft_f1"])
            for row in rows
        ),
        "policy_global_revision_delta_f1": mean(
            float(row["typed_revision_delta_f1"])
            if str(row["sample_id"]) in selected_ids
            else float(row["preserve_revision_delta_f1"])
            for row in rows
        ),
    }


def _choose_policy(rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, int]:
    candidates = [_policy_summary(rows, policy) for policy in _policies()]
    eligible = [
        candidate
        for candidate in candidates
        if MIN_COVERAGE <= float(candidate["coverage"]) <= MAX_COVERAGE
    ]
    if not eligible:
        return None, len(candidates)
    eligible.sort(
        key=lambda candidate: (
            -float(candidate["selected_mean_revision_delta_f1"]),
            float(candidate["selected_collateral_rate"]),
            -float(candidate["selected_target_complete_rate"]),
            -float(candidate["coverage"]),
            str(candidate["policy_id"]),
        )
    )
    return eligible[0], len(candidates)


def _calibration_gate(summary: dict[str, Any] | None) -> dict[str, bool]:
    if summary is None:
        return {
            "eligible_policy_found": False,
            "coverage_registered": False,
            "delta_enrichment_at_least_0_03": False,
            "collateral_not_worse": False,
            "target_complete_not_worse": False,
        }
    return {
        "eligible_policy_found": True,
        "coverage_registered": MIN_COVERAGE <= float(summary["coverage"]) <= MAX_COVERAGE,
        "delta_enrichment_at_least_0_03": float(summary["selected_delta_enrichment"])
        >= MIN_ENRICHMENT,
        "collateral_not_worse": float(summary["selected_collateral_rate"])
        <= float(summary["always_typed_collateral_rate"]),
        "target_complete_not_worse": float(summary["selected_target_complete_rate"])
        >= float(summary["always_typed_target_complete_rate"]),
    }


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _enrichment_bootstrap(rows: list[dict[str, Any]], policy: dict[str, float]) -> dict[str, Any]:
    by_category = {
        category: [row for row in rows if str(row["category"]) == category]
        for category in CATEGORIES
    }
    rng = random.Random(BOOTSTRAP_SEED)
    estimates: list[float] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sampled = [
            rng.choice(by_category[category])
            for category in CATEGORIES
            for _ in by_category[category]
        ]
        selected = [row for row in sampled if _accept(row["features"], policy)]
        if not selected:
            raise ValueError("P14 bootstrap produced an empty selected subset")
        estimates.append(
            mean(float(row["typed_revision_delta_f1"]) for row in selected)
            - mean(float(row["typed_revision_delta_f1"]) for row in sampled)
        )
    return {
        "method": "category-stratified-percentile-bootstrap-v1",
        "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED,
        "confidence": 0.95,
        "lower": _percentile(estimates, 0.025),
        "upper": _percentile(estimates, 0.975),
        "probability_positive": mean(float(value > 0.0) for value in estimates),
    }


def _validate_run(packet_dir: Path, run_dir: Path) -> dict[str, Any]:
    packet_audit = verify_packet(packet_dir, require_tag=True)
    if packet_audit["valid"] is not True:
        raise ValueError(f"P14 packet audit failed: {packet_audit['errors']}")
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    identity = json.loads((run_dir / "run_identity.json").read_text(encoding="utf-8"))
    predictions = read_jsonl(run_dir / "predictions.jsonl")
    checkpoint = read_jsonl(run_dir / "checkpoint.jsonl")
    prediction_map = _by_id(predictions, key="sample_id", role="P14 predictions")
    checkpoint_map = _by_id(checkpoint, key="sample_id", role="P14 checkpoint")
    packet_rows = _by_id(
        read_jsonl(packet_dir / "falsirag_bench.jsonl"),
        key="id",
        role="P14 packet",
    )
    commit = prereg_commit(required=True)
    runtime = identity.get("llm_runtime", {}).get("ollama_model", {})
    llm = identity.get("llm", {})
    source_revision = identity.get("source_revision", {})
    checks = {
        "packet_valid": True,
        "complete_120": manifest.get("status") == "complete"
        and manifest.get("completed") == 120
        and manifest.get("expected") == 120,
        "method_far": manifest.get("method") == identity.get("method") == "far",
        "train_only": manifest.get("split") == identity.get("split") == "train",
        "no_limit": identity.get("limit") is None,
        "prediction_coverage": set(prediction_map) == set(checkpoint_map) == set(packet_rows),
        "checkpoint_matches_predictions": checkpoint_map == prediction_map,
        "prediction_hash_bound": manifest.get("predictions_sha256")
        == sha256_file(run_dir / "predictions.jsonl"),
        "packet_hash_bound": identity.get("benchmark_input_sha256")
        == sha256_file(packet_dir / "falsirag_bench.jsonl"),
        "corpus_hash_bound": identity.get("corpus_sha256") == CORPUS_SHA256,
        "config_hash_bound": identity.get("config_sha256") == CONFIG_SHA256,
        "model_digest_bound": identity.get("llm_runtime", {}).get("model") == MODEL
        and runtime.get("digest") == MODEL_DIGEST,
        "v2_model_lifecycle_bound": llm.get("unload_after_sample") is False
        and llm.get("keep_alive") == "24h",
        "v2_cache_isolated": llm.get("cache_path")
        == "outputs/cache/qwen_selective_acceptance_v2.sqlite3"
        and llm.get("cache_namespace") == "far-qwen3.5-9b-selective-acceptance-v2",
        "clean_preregistered_source": source_revision.get("git_commit") == commit
        and source_revision.get("git_dirty") is False,
    }
    if not all(checks.values()):
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise ValueError(f"P14 run validation failed: {failed}")
    return {
        "checks": checks,
        "identity_sha256": sha256_file(run_dir / "run_identity.json"),
        "manifest_sha256": sha256_file(run_dir / "run_manifest.json"),
        "predictions_sha256": sha256_file(run_dir / "predictions.jsonl"),
        "checkpoint_sha256": sha256_file(run_dir / "checkpoint.jsonl"),
        "source_revision": source_revision,
        "implementation_sha256": identity.get("implementation_sha256"),
    }


def compute_report(
    *,
    packet_dir: Path,
    run_dir: Path,
    train_path: Path = TRAIN_PATH,
) -> dict[str, Any]:
    run = _validate_run(packet_dir, run_dir)
    source_rows = _by_id(read_jsonl(train_path), key="id", role="P14 train source")
    predictions = _by_id(
        read_jsonl(run_dir / "predictions.jsonl"),
        key="sample_id",
        role="P14 predictions",
    )
    packet = json.loads((packet_dir / "protocol_manifest.json").read_text(encoding="utf-8"))
    calibration_ids = [str(item) for item in packet["split"]["calibration_ids"]]
    evaluation_ids = [str(item) for item in packet["split"]["evaluation_ids"]]
    if set(predictions) != set(calibration_ids) | set(evaluation_ids):
        raise ValueError("P14 predictions do not match the registered partitions")

    calibration_rows = _outcome_rows(source_rows, predictions, calibration_ids)
    selected, candidate_count = _choose_policy(calibration_rows)
    calibration_checks = _calibration_gate(selected)
    calibration_passed = all(calibration_checks.values())
    evaluation: dict[str, Any]
    outcome: str
    if not calibration_passed or selected is None:
        evaluation = {
            "scored": False,
            "reason": "registered calibration gate did not pass",
            "outcome_rows_included": False,
        }
        outcome = "stopped_at_calibration"
    else:
        evaluation_rows = _outcome_rows(source_rows, predictions, evaluation_ids)
        evaluation_summary = _policy_summary(evaluation_rows, selected["policy"])
        bootstrap = _enrichment_bootstrap(evaluation_rows, selected["policy"])
        evaluation_checks = {
            "coverage_registered": MIN_COVERAGE
            <= float(evaluation_summary["coverage"])
            <= MAX_COVERAGE,
            "delta_enrichment_at_least_0_03": float(evaluation_summary["selected_delta_enrichment"])
            >= MIN_ENRICHMENT,
            "enrichment_interval_lower_positive": float(bootstrap["lower"]) > 0.0,
            "collateral_not_worse": float(evaluation_summary["selected_collateral_rate"])
            <= float(evaluation_summary["always_typed_collateral_rate"]),
            "target_complete_not_worse": float(evaluation_summary["selected_target_complete_rate"])
            >= float(evaluation_summary["always_typed_target_complete_rate"]),
        }
        evaluation = {
            "scored": True,
            "summary": evaluation_summary,
            "enrichment_bootstrap": bootstrap,
            "success_checks": evaluation_checks,
            "success": all(evaluation_checks.values()),
            "rows": evaluation_rows,
        }
        outcome = "evaluation_success" if evaluation["success"] else "evaluation_null"

    return {
        "schema_version": SCHEMA_VERSION,
        "analysis_profile": ANALYSIS_PROFILE,
        "valid": True,
        "registered_outcome": outcome,
        "protocol": verify_protocol(require_tag=True),
        "run": run,
        "packet_manifest_sha256": sha256_file(packet_dir / "protocol_manifest.json"),
        "candidate_grid": {
            "candidate_count": candidate_count,
            "confidence_min": list(CONFIDENCE_GRID),
            "max_edit_fraction": list(MAX_EDIT_FRACTION_GRID),
            "min_trace_consistency_margin": list(MIN_TRACE_MARGIN_GRID),
            "coverage_bounds": [MIN_COVERAGE, MAX_COVERAGE],
            "minimum_enrichment": MIN_ENRICHMENT,
        },
        "calibration": {
            "samples": 60,
            "selected_policy": selected,
            "gate_checks": calibration_checks,
            "gate_passed": calibration_passed,
            "rows": calibration_rows,
        },
        "evaluation": evaluation,
        "boundaries": {
            "preregistered": True,
            "new_inference": True,
            "pipeline_sample_executions": 120,
            "exact_internal_llm_calls_claimed": False,
            "reference_free_policy_features": True,
            "post_generation_acceptance": True,
            "pre_execution_selector": False,
            "deterministic_preserve_fallback": True,
            "dependency_group_disjoint": True,
            "same_corpus_and_construction_process": True,
            "test_accessed": False,
            "human_review": False,
            "human_iaa": False,
            "publication_gold": False,
            "semantic_correctness": False,
            "external_validation": False,
            "causal_policy_effect": False,
            "local_model_execution": False,
            "model_execution_location": "windows-gpu",
            "performance_amendment": True,
            "retired_v1_rows_reused": 0,
            "fresh_v2_run_required": True,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    calibration = report["calibration"]
    selected = calibration["selected_policy"]
    lines = [
        "# P14 Reference-Free Selective Acceptance",
        "",
        "> Preregistered, machine-seeded development study. The controller acts after "
        "generation; this is not semantic correctness, human review, external validation, "
        "or a pre-execution selector.",
        "",
        "## Registered outcome",
        "",
        f"`{report['registered_outcome']}`",
        "",
        "## Calibration",
        "",
        f"- Gate passed: `{str(calibration['gate_passed']).lower()}`",
        f"- Candidate policies evaluated: `{report['candidate_grid']['candidate_count']}`",
    ]
    if selected is None:
        lines.append("- No policy satisfied the registered coverage range.")
    else:
        lines.extend(
            [
                f"- Policy: `{selected['policy_id']}`",
                f"- Coverage: `{selected['coverage']:.4f}` ({selected['selected_rows']}/60)",
                "- Selected revision-delta F1: "
                f"`{selected['selected_mean_revision_delta_f1']:.4f}`; enrichment over "
                "always typed "
                f"`{selected['selected_delta_enrichment']:+.4f}`",
                f"- Collateral rate: `{selected['selected_collateral_rate']:.4f}`; "
                f"always typed `{selected['always_typed_collateral_rate']:.4f}`",
                f"- Target-complete rate: `{selected['selected_target_complete_rate']:.4f}`; "
                f"always typed `{selected['always_typed_target_complete_rate']:.4f}`",
            ]
        )
    lines.extend(["", "## Evaluation", ""])
    evaluation = report["evaluation"]
    if evaluation["scored"] is not True:
        lines.append(
            "Evaluation outcomes were not scored because the preregistered calibration gate failed."
        )
    else:
        summary = evaluation["summary"]
        bootstrap = evaluation["enrichment_bootstrap"]
        lines.extend(
            [
                f"- Success: `{str(evaluation['success']).lower()}`",
                f"- Coverage: `{summary['coverage']:.4f}` ({summary['selected_rows']}/60)",
                "- Selected revision-delta F1: "
                f"`{summary['selected_mean_revision_delta_f1']:.4f}`; enrichment "
                f"`{summary['selected_delta_enrichment']:+.4f}`",
                f"- Enrichment 95% bootstrap interval: `[{bootstrap['lower']:+.4f}, "
                f"{bootstrap['upper']:+.4f}]`",
                f"- Policy global answer soft F1: `{summary['policy_global_answer_soft_f1']:.4f}`",
                f"- Policy global revision-delta F1: "
                f"`{summary['policy_global_revision_delta_f1']:.4f}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "The policy features contain no construction reference or expected action, but outcome "
            "metrics remain construction-derived lexical diagnostics. Calibration and evaluation "
            "are dependency-group disjoint yet share one corpus and construction process. The "
            "policy accepts or rejects an already-generated typed answer and therefore does not "
            "save inference or establish deployment safety, semantic repair, human agreement, "
            "causal policy effect, or held-out/test performance.",
            "",
        ]
    )
    return "\n".join(lines)


def build_reports(
    *,
    packet_dir: Path,
    run_dir: Path,
    output_json: Path,
    output_markdown: Path,
) -> dict[str, Any]:
    report = compute_report(packet_dir=packet_dir, run_dir=run_dir)
    write_json(output_json, report)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(render_markdown(report), encoding="utf-8")
    return report


def verify_reports(
    *,
    packet_dir: Path,
    run_dir: Path,
    output_json: Path,
    output_markdown: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    outcome: str | None = None
    try:
        expected = compute_report(packet_dir=packet_dir, run_dir=run_dir)
        observed = json.loads(output_json.read_text(encoding="utf-8"))
        outcome = str(expected["registered_outcome"])
        if observed != expected:
            errors.append("P14 JSON report differs from deterministic recomputation")
        if output_markdown.read_text(encoding="utf-8") != render_markdown(expected):
            errors.append("P14 Markdown report differs from deterministic recomputation")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "valid": not errors,
        "errors": errors,
        "registered_outcome": outcome,
        "test_accessed": False,
        "human_review": False,
        "publication_gold": False,
        "semantic_correctness": False,
        "local_model_execution": False,
    }


def run_registered(output_root: Path) -> dict[str, Any]:
    if output_root.name != DEFAULT_OUTPUT_ROOT.name:
        raise ValueError("formal P14 v2 run requires a fresh selective_acceptance_v2 output root")
    run_identity = output_root / "runs" / "far" / "run_identity.json"
    if V2_CACHE_PATH.exists() and not run_identity.is_file():
        raise ValueError("formal P14 v2 run refuses a pre-existing unbound v2 cache")
    commit = _require_formal_source()
    packet_dir = output_root / "input"
    run_dir = output_root / "runs" / "far"
    manifest_path = packet_dir / "protocol_manifest.json"
    if manifest_path.is_file():
        packet_audit = verify_packet(packet_dir, require_tag=True)
        if packet_audit["valid"] is not True:
            raise ValueError(f"existing P14 input packet is invalid: {packet_audit['errors']}")
    else:
        build_packet(packet_dir, source_commit=commit)
    run_far(
        CONFIG_PATH,
        packet_dir,
        run_dir,
        split="train",
        limit=None,
        allow_test=False,
    )
    return build_reports(
        packet_dir=packet_dir,
        run_dir=run_dir,
        output_json=output_root / "selective_acceptance.json",
        output_markdown=output_root / "selective_acceptance.md",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    protocol_parser = subparsers.add_parser("verify-protocol")
    protocol_parser.add_argument("--allow-missing-tag", action="store_true")

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--output-dir", type=Path, required=True)

    packet_parser = subparsers.add_parser("verify-packet")
    packet_parser.add_argument("--packet-dir", type=Path, required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)

    for name in ("finalize", "verify"):
        report_parser = subparsers.add_parser(name)
        report_parser.add_argument("--packet-dir", type=Path, required=True)
        report_parser.add_argument("--run-dir", type=Path, required=True)
        report_parser.add_argument("--output-json", type=Path, default=DEFAULT_REPORT_JSON)
        report_parser.add_argument("--output-markdown", type=Path, default=DEFAULT_REPORT_MARKDOWN)

    args = parser.parse_args()
    if args.command == "verify-protocol":
        result = verify_protocol(require_tag=not args.allow_missing_tag)
    elif args.command == "prepare":
        commit = prereg_commit(required=True)
        result = build_packet(args.output_dir, source_commit=commit)
    elif args.command == "verify-packet":
        result = verify_packet(args.packet_dir, require_tag=True)
    elif args.command == "run":
        result = run_registered(args.output_root)
    else:
        kwargs = {
            "packet_dir": args.packet_dir,
            "run_dir": args.run_dir,
            "output_json": args.output_json,
            "output_markdown": args.output_markdown,
        }
        result = build_reports(**kwargs) if args.command == "finalize" else verify_reports(**kwargs)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result.get("valid") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
