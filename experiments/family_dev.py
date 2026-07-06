"""Run and finalize the preregistered WS2 typed/untyped family-dev study."""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import shutil
from pathlib import Path
from statistics import mean
from typing import Any, cast

from bench.build.common import read_jsonl, sha256_file, write_json
from eval.run_eval import evaluate
from eval.stats import mcnemar_exact
from experiments.protocol_family_dev import (
    CORPUS_SHA256,
    DEV_INPUT_SHA256,
    FAMILY_DEV_ACTIVE_SHA256,
    FAMILY_ORDER,
    METHODS,
    MODEL_SPECS,
    require_clean_pushed_source,
    verify_family_protocol,
)
from experiments.protocol_longterm import ROOT
from experiments.run_far import run as run_far

DISPOSITION_PATH = (
    ROOT / "diagnostics" / "solo_v1" / "machine_annotation" / "machine_consensus_rows.jsonl"
)
CORRECTNESS_THRESHOLD = 0.8
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 1729


def prepare_dev_view(output_dir: Path) -> dict[str, Any]:
    audit = verify_family_protocol()
    if audit.get("valid") is not True:
        raise ValueError(f"family-dev protocol is invalid: {audit['errors']}")
    source_dev = ROOT / "bench" / "splits" / "dev.jsonl"
    source_corpus = ROOT / "bench" / "corpus.jsonl"
    manifest_path = output_dir / "manifest.json"
    if manifest_path.is_file():
        existing = cast(
            dict[str, Any],
            json.loads(manifest_path.read_text(encoding="utf-8")),
        )
        if (
            existing.get("schema_version") == "far-family-dev-input-v1"
            and existing.get("dev_sha256") == DEV_INPUT_SHA256
            and existing.get("corpus_sha256") == CORPUS_SHA256
            and sha256_file(output_dir / "falsirag_bench.jsonl") == DEV_INPUT_SHA256
            and sha256_file(output_dir / "corpus.jsonl") == CORPUS_SHA256
        ):
            return existing
        raise ValueError("existing family-dev input view has a different identity")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"{output_dir} is nonempty")
    rows = read_jsonl(source_dev)
    if len(rows) != 60 or {str(row.get("split")) for row in rows} != {"dev"}:
        raise ValueError("family-dev input requires exactly 60 dev rows")
    output_dir.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source_dev, output_dir / "falsirag_bench.jsonl")
    shutil.copyfile(source_corpus, output_dir / "corpus.jsonl")
    manifest = {
        "schema_version": "far-family-dev-input-v1",
        "protocol_fingerprint": FAMILY_DEV_ACTIVE_SHA256,
        "source": "bench/splits/dev.jsonl",
        "dev_sha256": sha256_file(output_dir / "falsirag_bench.jsonl"),
        "corpus_sha256": sha256_file(output_dir / "corpus.jsonl"),
        "samples": 60,
        "split": "dev",
        "contains_train": False,
        "contains_test": False,
        "test_accessed": False,
    }
    write_json(manifest_path, manifest)
    return manifest


def _validate_runtime_identity(identity_path: Path, family: str, commit: str) -> None:
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    spec = MODEL_SPECS[family]
    source = identity.get("source_revision", {})
    runtime = identity.get("llm_runtime", {}).get("ollama_model", {})
    if source.get("git_commit") != commit or source.get("git_dirty") is not False:
        raise ValueError(f"{family} run identity is not bound to the clean source commit")
    if runtime.get("model") != spec["model"] or runtime.get("digest") != spec["digest"]:
        raise ValueError(f"{family} Ollama runtime identity differs from preregistration")
    if identity.get("config_sha256") != spec["config_sha256"]:
        raise ValueError(f"{family} run config differs from preregistration")
    if identity.get("benchmark_input_sha256") != DEV_INPUT_SHA256:
        raise ValueError(f"{family} run did not use the frozen dev-only input")
    if identity.get("corpus_sha256") != CORPUS_SHA256:
        raise ValueError(f"{family} run corpus differs from preregistration")


def _run_arm(
    *,
    family: str,
    method: str,
    input_dir: Path,
    output_dir: Path,
    limit: int | None,
    commit: str,
) -> dict[str, Any]:
    spec = MODEL_SPECS[family]
    ablation = "full" if method == "far" else "minus_typed_conflict"
    manifest = run_far(
        ROOT / spec["config"],
        input_dir,
        output_dir,
        ablation=ablation,
        split="dev",
        limit=limit,
        allow_test=False,
    )
    _validate_runtime_identity(output_dir / "run_identity.json", family, commit)
    expected = 5 if limit == 5 else 60
    if (
        manifest.get("status") != "complete"
        or int(manifest.get("completed", -1)) != expected
        or bool(manifest.get("partial")) != (limit is not None)
        or int(manifest.get("errors", -1)) != 0
    ):
        raise ValueError(f"{family}/{method} run is incomplete")
    return manifest


def run_family(family: str, input_dir: Path, output_root: Path) -> dict[str, Any]:
    if family not in FAMILY_ORDER:
        raise ValueError(f"unknown family: {family}")
    audit = verify_family_protocol()
    if audit.get("valid") is not True:
        raise ValueError(f"family-dev protocol is invalid: {audit['errors']}")
    commit = require_clean_pushed_source()
    input_manifest = prepare_dev_view(input_dir)
    family_index = FAMILY_ORDER.index(family)
    for predecessor in FAMILY_ORDER[:family_index]:
        if not (output_root / "family_manifests" / f"{predecessor}.json").is_file():
            raise ValueError(f"{family} cannot start before {predecessor} completes")
    completion_path = output_root / "family_manifests" / f"{family}.json"
    if completion_path.is_file():
        existing = cast(
            dict[str, Any],
            json.loads(completion_path.read_text(encoding="utf-8")),
        )
        if existing.get("source_commit") != commit:
            raise ValueError(f"{family} completion belongs to another source commit")
        return existing
    manifests: dict[str, Any] = {"calibration": {}, "formal": {}}
    for method in METHODS:
        manifests["calibration"][method] = _run_arm(
            family=family,
            method=method,
            input_dir=input_dir,
            output_dir=output_root / "calibration" / family / method,
            limit=5,
            commit=commit,
        )
    for method in METHODS:
        manifests["formal"][method] = _run_arm(
            family=family,
            method=method,
            input_dir=input_dir,
            output_dir=output_root / "runs" / family / method,
            limit=None,
            commit=commit,
        )
    completion_path.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": "far-family-dev-family-run-v1",
        "protocol_fingerprint": FAMILY_DEV_ACTIVE_SHA256,
        "family": family,
        "model": MODEL_SPECS[family]["model"],
        "digest": MODEL_SPECS[family]["digest"],
        "config_sha256": MODEL_SPECS[family]["config_sha256"],
        "source_commit": commit,
        "input_manifest_sha256": sha256_file(input_dir / "manifest.json"),
        "input": input_manifest,
        "manifests": manifests,
        "calibration_pipeline_samples": 10,
        "formal_pipeline_samples": 120,
        "api_cost_usd": 0,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }
    write_json(completion_path, result)
    return result


def _by_id(path: Path) -> dict[str, dict[str, Any]]:
    rows = read_jsonl(path)
    result = {str(row["sample_id"]): row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"duplicate sample IDs in {path}")
    return result


def _dev_dispositions(dev_ids: set[str]) -> dict[str, str]:
    pattern = re.compile(r'"sample_id"\s*:\s*"([^"]+)"')
    result: dict[str, str] = {}
    with DISPOSITION_PATH.open(encoding="utf-8") as handle:
        for raw in handle:
            match = pattern.search(raw)
            if match is None or match.group(1) not in dev_ids:
                continue
            row = json.loads(raw)
            sample_id = str(row["sample_id"])
            if sample_id in result:
                raise ValueError(f"duplicate machine disposition: {sample_id}")
            result[sample_id] = str(row["disposition"])
    if set(result) != dev_ids:
        raise ValueError("machine dispositions do not exactly cover dev")
    return result


def _cluster_bootstrap(family_deltas: dict[str, list[float]]) -> dict[str, Any]:
    if set(family_deltas) != set(FAMILY_ORDER):
        raise ValueError("cluster bootstrap requires all three families")
    rng = random.Random(BOOTSTRAP_SEED)
    estimates: list[float] = []
    families = list(FAMILY_ORDER)
    for _ in range(BOOTSTRAP_RESAMPLES):
        sampled = [rng.choice(families) for _ in families]
        values = [value for family in sampled for value in family_deltas[family]]
        estimates.append(mean(values))
    estimates.sort()

    def percentile(probability: float) -> float:
        position = probability * (len(estimates) - 1)
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return estimates[lower]
        weight = position - lower
        return estimates[lower] * (1.0 - weight) + estimates[upper] * weight

    return {
        "method": "family-cluster-percentile-bootstrap-v1",
        "clusters": 3,
        "pairs_per_cluster": 60,
        "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED,
        "confidence": 0.95,
        "lower": percentile(0.025),
        "upper": percentile(0.975),
        "probability_positive": sum(value > 0 for value in estimates) / len(estimates),
    }


def compute_result(output_root: Path) -> dict[str, Any]:
    audit = verify_family_protocol()
    if audit.get("valid") is not True:
        raise ValueError(f"family-dev protocol is invalid: {audit['errors']}")
    dev_path = ROOT / "bench" / "splits" / "dev.jsonl"
    dev_rows = read_jsonl(dev_path)
    dev_ids = {str(row["id"]) for row in dev_rows}
    if len(dev_ids) != 60:
        raise ValueError("family-dev finalization requires 60 dev labels")
    dispositions = _dev_dispositions(dev_ids)
    family_rows: list[dict[str, Any]] = []
    family_deltas: dict[str, list[float]] = {}
    all_baseline_success: list[bool] = []
    all_candidate_success: list[bool] = []
    sensitivity_values: dict[str, list[float]] = {
        "machine_confirmed": [],
        "machine_disputed": [],
    }
    source_commits: set[str] = set()
    for family in FAMILY_ORDER:
        family_manifest_path = output_root / "family_manifests" / f"{family}.json"
        family_manifest = json.loads(family_manifest_path.read_text(encoding="utf-8"))
        source_commits.add(str(family_manifest["source_commit"]))
        typed_scores = _by_id(output_root / "evaluations" / family / "far" / "scores.jsonl")
        untyped_scores = _by_id(
            output_root / "evaluations" / family / "minus_typed_conflict" / "scores.jsonl"
        )
        if set(typed_scores) != dev_ids or set(untyped_scores) != dev_ids:
            raise ValueError(f"{family} scores do not exactly cover dev")
        deltas = [
            float(typed_scores[sample_id]["answer_correctness"])
            - float(untyped_scores[sample_id]["answer_correctness"])
            for sample_id in sorted(dev_ids)
        ]
        family_deltas[family] = deltas
        typed_success = [
            float(typed_scores[item]["answer_correctness"]) >= CORRECTNESS_THRESHOLD
            for item in sorted(dev_ids)
        ]
        untyped_success = [
            float(untyped_scores[item]["answer_correctness"]) >= CORRECTNESS_THRESHOLD
            for item in sorted(dev_ids)
        ]
        all_candidate_success.extend(typed_success)
        all_baseline_success.extend(untyped_success)
        for sample_id, delta in zip(sorted(dev_ids), deltas, strict=True):
            sensitivity_values[dispositions[sample_id]].append(delta)
        typed_report = json.loads(
            (output_root / "evaluations" / family / "far" / "report.json").read_text(
                encoding="utf-8"
            )
        )
        untyped_report = json.loads(
            (
                output_root / "evaluations" / family / "minus_typed_conflict" / "report.json"
            ).read_text(encoding="utf-8")
        )
        family_rows.append(
            {
                "family": family,
                "model": MODEL_SPECS[family]["model"],
                "digest": MODEL_SPECS[family]["digest"],
                "samples": 60,
                "typed_minus_untyped_answer_correctness": mean(deltas),
                "typed_minus_untyped_typed_conflict_f1": float(
                    typed_report["aggregate"]["metrics"]["typed_conflict_f1"]
                )
                - float(untyped_report["aggregate"]["metrics"]["typed_conflict_f1"]),
                "typed_minus_untyped_revision_accuracy": float(
                    typed_report["aggregate"]["metrics"]["revision_accuracy"]
                )
                - float(untyped_report["aggregate"]["metrics"]["revision_accuracy"]),
                "mcnemar": mcnemar_exact(untyped_success, typed_success),
                "direction_positive": mean(deltas) > 0.0,
            }
        )
    if len(source_commits) != 1:
        raise ValueError("family-dev runs mix source commits")
    combined_delta = mean(value for values in family_deltas.values() for value in values)
    mcnemar = mcnemar_exact(all_baseline_success, all_candidate_success)
    positive_families = sum(bool(row["direction_positive"]) for row in family_rows)
    gate_f = combined_delta > 0.0 and float(mcnemar["p_value"]) < 0.05
    return {
        "schema_version": "far-family-dev-result-v1",
        "protocol_fingerprint": FAMILY_DEV_ACTIVE_SHA256,
        "source_commit": next(iter(source_commits)),
        "split": "dev",
        "families": family_rows,
        "primary": {
            "metric": "typed_minus_untyped_answer_correctness",
            "pairs": 180,
            "combined_delta": combined_delta,
            "binary_threshold": CORRECTNESS_THRESHOLD,
            "stratified_exact_mcnemar": mcnemar,
            "family_cluster_bootstrap": _cluster_bootstrap(family_deltas),
            "positive_families": positive_families,
            "direction_consistent": positive_families >= 2,
            "gate_f_passed": gate_f,
        },
        "machine_disposition_sensitivity": {
            key: {"pairs": len(values), "combined_delta": mean(values)}
            for key, values in sensitivity_values.items()
        },
        "gate_p_completed": True,
        "adequately_powered": False,
        "required_claim_level": "directional_reproduction",
        "formal_pipeline_samples": 360,
        "calibration_pipeline_samples": 30,
        "api_cost_usd": 0,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }


def _report_text(result: dict[str, Any]) -> str:
    primary = result["primary"]
    lines = [
        "# FAR 跨家族 typed/untyped dev 复现 (WS2)",
        "",
        "> 机器审计 dev、非真人金标、非盲测、非外部验证；G-P 预先限定为方向性复现。",
        "",
        "| 家族 | typed-untyped answer | typed conflict F1 | revision accuracy | 方向 |",
        "|---|---:|---:|---:|---|",
    ]
    for row in result["families"]:
        lines.append(
            f"| {row['family']} | {row['typed_minus_untyped_answer_correctness']:+.4f} | "
            f"{row['typed_minus_untyped_typed_conflict_f1']:+.4f} | "
            f"{row['typed_minus_untyped_revision_accuracy']:+.4f} | "
            f"{'正' if row['direction_positive'] else '非正'} |"
        )
    cluster = primary["family_cluster_bootstrap"]
    mcnemar = primary["stratified_exact_mcnemar"]
    lines.extend(
        [
            "",
            "## 预注册主判定",
            "",
            f"- 合并连续差: {primary['combined_delta']:+.4f}。",
            f"- 分层 exact McNemar: candidate-only={mcnemar['candidate_only']}, "
            f"baseline-only={mcnemar['baseline_only']}, p={mcnemar['p_value']:.6f}。",
            f"- 家族 cluster bootstrap 95% CI: [{cluster['lower']:+.4f}, "
            f"{cluster['upper']:+.4f}]。",
            f"- 正方向家族: {primary['positive_families']}/3；"
            f"G-F=`{str(primary['gate_f_passed']).lower()}`。",
            "",
            "G-F 不显著不能在 0.414 功效下解释为机制不存在；少于 2/3 家族正方向或合并差"
            "非正时，主张按预注册收窄为 Qwen-specific。所有次级指标仅作描述性披露。",
            "",
        ]
    )
    return "\n".join(lines)


def finalize(output_root: Path) -> dict[str, Any]:
    if (output_root / "manifest.json").exists():
        raise FileExistsError("family-dev release is already finalized")
    dev_path = ROOT / "bench" / "splits" / "dev.jsonl"
    for family in FAMILY_ORDER:
        for method in METHODS:
            run_dir = output_root / "runs" / family / method
            evaluation_dir = output_root / "evaluations" / family / method
            evaluate(
                dev_path,
                run_dir / "predictions.jsonl",
                evaluation_dir,
                resamples=BOOTSTRAP_RESAMPLES,
                seed=BOOTSTRAP_SEED,
                benchmark_manifest_path=ROOT / "bench" / "manifest.json",
            )
    result = compute_result(output_root)
    write_json(output_root / "result.json", result)
    report = _report_text(result)
    (output_root / "family_dev_report.md").write_text(report, encoding="utf-8")
    artifacts = {
        str(path.relative_to(output_root)): sha256_file(path)
        for path in sorted(output_root.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    manifest = {
        "schema_version": "far-family-dev-release-v1",
        "protocol_fingerprint": FAMILY_DEV_ACTIVE_SHA256,
        "source_commit": result["source_commit"],
        "artifacts": artifacts,
        "result_sha256": sha256_file(output_root / "result.json"),
        "report_sha256": sha256_file(output_root / "family_dev_report.md"),
        "gate_f_passed": result["primary"]["gate_f_passed"],
        "direction_consistent": result["primary"]["direction_consistent"],
        "gate_p_completed": True,
        "adequately_powered": False,
        "required_claim_level": "directional_reproduction",
        "formal_pipeline_samples": 360,
        "calibration_pipeline_samples": 30,
        "api_cost_usd": 0,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }
    write_json(output_root / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare-input")
    prepare.add_argument("--output-dir", type=Path, required=True)
    run = subparsers.add_parser("run-family")
    run.add_argument("--family", choices=FAMILY_ORDER, required=True)
    run.add_argument("--input-dir", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    finish = subparsers.add_parser("finalize")
    finish.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare-input":
        result = prepare_dev_view(args.output_dir)
    elif args.command == "run-family":
        result = run_family(args.family, args.input_dir, args.output_dir)
    else:
        result = finalize(args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
