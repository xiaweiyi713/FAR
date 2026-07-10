"""Run, score, and finalize the preregistered WS3 boundary mapping study."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from far.bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.eval.metrics import soft_f1
from far.eval.ramdocs import normalize_ramdocs_answer
from far.eval.stats import mcnemar_exact, paired_bootstrap_comparison
from far.experiments.protocol_boundary import (
    BOUNDARY_ACTIVE_SHA256,
    CONFIG_PATH,
    DATASET_ORDER,
    DATASETS,
    METHODS,
    QWEN_DIGEST,
    verify_boundary_protocol,
)
from far.experiments.protocol_family_dev import require_clean_pushed_source
from far.experiments.run_ramdocs import _far_prediction
from far.experiments.runner import (
    CheckpointWriter,
    _implementation_sha256,
    _llm_runtime_identity,
    _source_revision,
    build_generator,
    generator_sample_scope,
    load_config,
)
from far.models import EvidenceDocument

BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 1729
CALIBRATION_LIMIT = 5
CONFLICT_TERMS = re.compile(
    r"\b(?:conflict|conflicting|contradict|contradictory|disagree|disagreement|"
    r"different answers|depending on)\b",
    flags=re.I,
)
PUBLIC_ENTITY_PHRASE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9&'./-]+|[A-Z]{2,})"
    r"(?:\s+(?:of|the|and|for|in|on|at|by|de|van|"
    r"[A-Z][A-Za-z0-9&'./-]+|[A-Z]{2,})){0,5}\b"
)
PUBLIC_ENTITY_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "list",
    "of",
    "on",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
}


def _contains_phrase(container: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    if not phrase or len(phrase) > len(container):
        return False
    return any(
        container[index : index + len(phrase)] == phrase
        for index in range(len(container) - len(phrase) + 1)
    )


def boundary_score(task: dict[str, Any], answer: str) -> dict[str, float | int]:
    references = [str(item) for item in task["reference_answers"]]
    if task["benchmark"] == "wikicontradict":
        normalized = normalize_ramdocs_answer(answer)
        hits = sum(
            _contains_phrase(normalized, normalize_ramdocs_answer(reference))
            for reference in references
        )
        score = hits / len(references)
        return {
            "boundary_score": score,
            "binary_success": int(hits == len(references)),
            "reference_hits": hits,
            "conflict_acknowledged": int(bool(CONFLICT_TERMS.search(answer))),
        }
    if task["benchmark"] == "google_rag_conflicts":
        score = soft_f1(answer, references[0])
        return {
            "boundary_score": score,
            "binary_success": int(score >= 0.8),
            "reference_hits": int(score >= 0.8),
            "conflict_acknowledged": int(bool(CONFLICT_TERMS.search(answer))),
        }
    raise ValueError(f"unknown boundary benchmark: {task['benchmark']}")


def _tasks(data_dir: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(data_dir / "tasks.jsonl")
    if len(rows) != 150 or {str(row.get("split")) for row in rows} != {"dev"}:
        raise ValueError("boundary run requires exactly 150 dev tasks")
    return sorted(rows, key=lambda row: str(row["id"]))


def _public_corpus_entities(row: dict[str, Any]) -> list[str]:
    """Derive a small non-oracle entity list from public corpus text only."""

    entities: list[str] = [
        str(entity).strip() for entity in row.get("entities", []) if str(entity).strip()
    ]
    title = str(row.get("title") or "")
    content = str(row.get("content") or "")
    title_variants = [
        title,
        re.sub(r"\s+-\s+Wikipedia$", "", title),
        re.sub(r"\s+\|\s+.*$", "", title),
        re.sub(r"\s*\([^)]*\)", "", title),
    ]
    candidates = [*title_variants]
    for text in (title, content[:1200]):
        candidates.extend(PUBLIC_ENTITY_PHRASE.findall(text))
    for candidate in candidates:
        if re.search(r"[.!?]\s", candidate):
            continue
        entity = re.sub(r"\s+", " ", candidate).strip(" \t\r\n:;,.-")
        if not entity:
            continue
        tokens = entity.split()
        if len(entity) < 3 or len(tokens) > 8:
            continue
        if all(token.casefold() in PUBLIC_ENTITY_STOPWORDS for token in tokens):
            continue
        if tokens[0].casefold() in {"a", "an", "the"} and len(tokens) > 1:
            entity = " ".join(tokens[1:])
        entities.append(entity)
    return list(dict.fromkeys(entities))[:24]


def _documents(data_dir: Path) -> dict[str, list[EvidenceDocument]]:
    grouped: dict[str, list[EvidenceDocument]] = defaultdict(list)
    for row in read_jsonl(data_dir / "corpus.jsonl"):
        sample_id = str(row.get("metadata", {}).get("sample_id", ""))
        if not sample_id:
            raise ValueError("boundary corpus document lacks sample_id")
        grouped[sample_id].append(
            EvidenceDocument(
                evidence_id=str(row["doc_id"]),
                text=str(row["content"]),
                title=str(row["title"]),
                source=str(row["source"]),
                date=row.get("date"),
                url=row.get("url"),
                metadata={"entities": _public_corpus_entities(row)},
            )
        )
    return grouped


def _calibration_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[json.dumps(row["strata"], sort_keys=True)].append(row)
    selected: list[dict[str, Any]] = []
    ordered_groups = sorted(groups.items())
    offset = 0
    while len(selected) < CALIBRATION_LIMIT:
        _, values = ordered_groups[offset % len(ordered_groups)]
        index = offset // len(ordered_groups)
        if index < len(values):
            selected.append(values[index])
        offset += 1
    return sorted(selected, key=lambda row: str(row["id"]))


def _identity(
    *,
    dataset: str,
    data_dir: Path,
    method: str,
    limit: int | None,
) -> dict[str, Any]:
    config = load_config(CONFIG_PATH)
    stable = {
        "schema_version": "far-boundary-run-signature-v1",
        "protocol_fingerprint": BOUNDARY_ACTIVE_SHA256,
        "dataset": dataset,
        "method": method,
        "split": "dev",
        "limit": limit,
        "config_sha256": sha256_file(CONFIG_PATH),
        "data_manifest_sha256": sha256_file(data_dir / "manifest.json"),
        "tasks_sha256": sha256_file(data_dir / "tasks.jsonl"),
        "corpus_sha256": sha256_file(data_dir / "corpus.jsonl"),
        "implementation_sha256": _implementation_sha256(),
        "source_revision": _source_revision(),
        "llm": config["llm"],
        "llm_runtime": _llm_runtime_identity(config),
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    return {**stable, "run_signature": hashlib.sha256(encoded).hexdigest()}


def _run_dir(output_root: Path, dataset: str, method: str, *, calibration: bool) -> Path:
    section = "calibration" if calibration else "runs"
    return output_root / section / dataset / method


def _completed_run(path: Path, *, expected: int, partial: bool) -> bool:
    manifest_path = path / "run_manifest.json"
    predictions_path = path / "predictions.jsonl"
    if not manifest_path.is_file() or not predictions_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return (
        manifest.get("status") == "complete"
        and int(manifest.get("completed", -1)) == expected
        and int(manifest.get("errors", -1)) == 0
        and bool(manifest.get("partial")) is partial
        and sha256_file(predictions_path) == manifest.get("predictions_sha256")
    )


def _require_boundary_order(
    output_root: Path,
    dataset: str,
    *,
    calibration: bool,
) -> None:
    dataset_index = DATASET_ORDER.index(dataset)
    for predecessor in DATASET_ORDER[:dataset_index]:
        for method in METHODS:
            if not _completed_run(
                _run_dir(output_root, predecessor, method, calibration=False),
                expected=150,
                partial=False,
            ):
                raise ValueError(
                    f"{dataset} cannot start before {predecessor}/{method} formal completes"
                )
    if calibration:
        return
    missing = [
        method
        for method in METHODS
        if not _completed_run(
            _run_dir(output_root, dataset, method, calibration=True),
            expected=CALIBRATION_LIMIT,
            partial=True,
        )
    ]
    if missing:
        raise ValueError(
            f"{dataset} formal run cannot start before calibration completes: {', '.join(missing)}"
        )


def run_method(
    dataset: str,
    output_root: Path,
    *,
    method: str,
    calibration: bool,
) -> dict[str, Any]:
    if dataset not in DATASETS or method not in METHODS:
        raise ValueError("unknown boundary dataset or method")
    protocol = verify_boundary_protocol()
    if protocol.get("valid") is not True:
        raise ValueError(f"boundary protocol is invalid: {protocol['errors']}")
    commit = require_clean_pushed_source()
    _require_boundary_order(output_root, dataset, calibration=calibration)
    data_dir = Path(DATASETS[dataset]["path"])
    rows = _tasks(data_dir)
    if calibration:
        rows = _calibration_rows(rows)
    documents = _documents(data_dir)
    if any(str(row["id"]) not in documents for row in rows):
        raise ValueError("boundary corpus does not cover all selected tasks")
    identity = _identity(
        dataset=dataset,
        data_dir=data_dir,
        method=method,
        limit=CALIBRATION_LIMIT if calibration else None,
    )
    source = identity["source_revision"]
    runtime = identity["llm_runtime"]["ollama_model"]
    if source.get("git_commit") != commit or source.get("git_dirty") is not False:
        raise ValueError("boundary run identity is not bound to clean source")
    if runtime.get("model") != "qwen3.5:9b" or runtime.get("digest") != QWEN_DIGEST:
        raise ValueError("boundary Qwen runtime digest differs from preregistration")
    writer = CheckpointWriter(
        _run_dir(output_root, dataset, method, calibration=calibration),
        identity,
    )
    config = load_config(CONFIG_PATH)
    generator = build_generator(config)
    for row in rows:
        sample_id = str(row["id"])
        if sample_id in writer.completed_ids:
            print(f"{dataset}/{method}: skip completed {sample_id}", flush=True)
            continue
        print(f"{dataset}/{method}: start {sample_id}", flush=True)
        started = time.perf_counter()
        with generator_sample_scope(generator):
            prediction = _far_prediction(
                method,
                str(row["question"]),
                str(row["initial_answer"]),
                documents[sample_id],
                config,
                generator,
            )
        writer.append(
            {
                "sample_id": sample_id,
                "method": method,
                **prediction,
                "metadata": {
                    **prediction["metadata"],
                    "elapsed_seconds": time.perf_counter() - started,
                },
            }
        )
        print(
            f"{dataset}/{method}: completed {sample_id} in {time.perf_counter() - started:.2f}s",
            flush=True,
        )
    return writer.finalize(
        {str(row["id"]) for row in rows},
        partial=calibration,
    )


def run_all(output_root: Path) -> dict[str, Any]:
    manifests: dict[str, Any] = {"calibration": {}, "formal": {}}
    for dataset in DATASET_ORDER:
        manifests["calibration"][dataset] = {}
        manifests["formal"][dataset] = {}
        for method in METHODS:
            manifests["calibration"][dataset][method] = run_method(
                dataset,
                output_root,
                method=method,
                calibration=True,
            )
        for method in METHODS:
            manifests["formal"][dataset][method] = run_method(
                dataset,
                output_root,
                method=method,
                calibration=False,
            )
    return {
        "schema_version": "far-boundary-run-all-v1",
        "protocol_fingerprint": BOUNDARY_ACTIVE_SHA256,
        "datasets": list(DATASET_ORDER),
        "methods": list(METHODS),
        "manifests": manifests,
        "formal_pipeline_samples": 600,
        "calibration_pipeline_samples": 20,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }


def evaluate_run(
    dataset: str,
    predictions_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    data_dir = Path(DATASETS[dataset]["path"])
    tasks = {str(row["id"]): row for row in _tasks(data_dir)}
    predictions = read_jsonl(predictions_path)
    if len(predictions) != 150 or {str(row["sample_id"]) for row in predictions} != set(tasks):
        raise ValueError("boundary evaluation requires exactly 150 predictions")
    scores: list[dict[str, Any]] = []
    for prediction in predictions:
        sample_id = str(prediction["sample_id"])
        task = tasks[sample_id]
        score = boundary_score(task, str(prediction["answer"]))
        predicted_conflict = bool(prediction.get("predicted_conflict_types", []))
        gold_conflict = task["conflict_type"] != "no_conflict"
        scores.append(
            {
                "sample_id": sample_id,
                "method": prediction["method"],
                "category": json.dumps(task["strata"], sort_keys=True),
                "benchmark": dataset,
                "boundary_score": float(score["boundary_score"]),
                "binary_success": int(score["binary_success"]),
                "reference_hits": int(score["reference_hits"]),
                "conflict_acknowledged": int(score["conflict_acknowledged"]),
                "conflict_detection_correct": int(predicted_conflict == gold_conflict),
                "strata": task["strata"],
            }
        )
    output_dir.mkdir(parents=True, exist_ok=False)
    write_jsonl(output_dir / "scores.jsonl", scores)
    report = {
        "schema_version": "far-boundary-evaluation-v1",
        "dataset": dataset,
        "method": predictions[0]["method"],
        "samples": 150,
        "metrics": {
            key: mean(float(row[key]) for row in scores)
            for key in (
                "boundary_score",
                "binary_success",
                "conflict_acknowledged",
                "conflict_detection_correct",
            )
        },
        "predictions_sha256": sha256_file(predictions_path),
        "scores_sha256": sha256_file(output_dir / "scores.jsonl"),
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }
    write_json(output_dir / "report.json", report)
    return report


def _paired_result(
    dataset: str,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    typed = read_jsonl(output_root / "evaluations" / dataset / "far" / "scores.jsonl")
    untyped = read_jsonl(
        output_root / "evaluations" / dataset / "far_minus_typed_conflict" / "scores.jsonl"
    )
    comparison = paired_bootstrap_comparison(
        untyped,
        typed,
        "boundary_score",
        resamples=BOOTSTRAP_RESAMPLES,
        seed=BOOTSTRAP_SEED,
    )
    typed_by_id = {str(row["sample_id"]): row for row in typed}
    untyped_by_id = {str(row["sample_id"]): row for row in untyped}
    ids = sorted(typed_by_id)
    mcnemar = mcnemar_exact(
        [bool(untyped_by_id[item]["binary_success"]) for item in ids],
        [bool(typed_by_id[item]["binary_success"]) for item in ids],
    )
    strata: dict[str, dict[str, Any]] = {}
    categories = sorted({str(row["category"]) for row in typed})
    for category in categories:
        category_ids = [item for item in ids if typed_by_id[item]["category"] == category]
        strata[category] = paired_bootstrap_comparison(
            [untyped_by_id[item] for item in category_ids],
            [typed_by_id[item] for item in category_ids],
            "boundary_score",
            resamples=BOOTSTRAP_RESAMPLES,
            seed=BOOTSTRAP_SEED,
        )
    return {
        "dataset": dataset,
        "samples": 150,
        "comparison": comparison,
        "mcnemar": mcnemar,
    }, strata


def _holm(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values, key=lambda key: p_values[key])
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for index, key in enumerate(ordered):
        running = max(running, min(1.0, (total - index) * p_values[key]))
        adjusted[key] = running
    return dict(sorted(adjusted.items()))


def compute_boundary_result(output_root: Path) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    strata: dict[str, Any] = {}
    p_values: dict[str, float] = {}
    for dataset in DATASET_ORDER:
        comparisons[dataset], strata[dataset] = _paired_result(dataset, output_root)
        p_values[dataset] = float(comparisons[dataset]["mcnemar"]["p_value"])

    def subgroup(dataset: str, predicate: Any) -> float:
        typed = read_jsonl(output_root / "evaluations" / dataset / "far" / "scores.jsonl")
        untyped = {
            str(row["sample_id"]): row
            for row in read_jsonl(
                output_root / "evaluations" / dataset / "far_minus_typed_conflict" / "scores.jsonl"
            )
        }
        deltas = [
            float(row["boundary_score"]) - float(untyped[str(row["sample_id"])]["boundary_score"])
            for row in typed
            if predicate(row["strata"])
        ]
        if not deltas:
            raise ValueError("boundary hypothesis subgroup is empty")
        return mean(deltas)

    wiki_explicit = subgroup("wikicontradict", lambda row: str(row["reasoning"]) == "Explicit")
    wiki_implicit = subgroup(
        "wikicontradict",
        lambda row: str(row["reasoning"]) == "Implicit (reasoning required)",
    )
    google_outdated = subgroup(
        "rag_conflicts",
        lambda row: str(row["upstream_conflict_type"]) == "Conflict due to outdated information",
    )
    google_misinfo = subgroup(
        "rag_conflicts",
        lambda row: str(row["upstream_conflict_type"]) == "Conflict due to misinformation",
    )
    google_safe = subgroup(
        "rag_conflicts",
        lambda row: str(row["upstream_conflict_type"]) == "No conflict",
    )
    hypotheses = {
        "B-W-explicit": {
            "expected": "positive",
            "delta": wiki_explicit,
            "outcome": "matched" if wiki_explicit > 0.0 else "contradicted",
        },
        "B-W-implicit": {
            "expected": "weaker_than_explicit",
            "explicit_delta": wiki_explicit,
            "implicit_delta": wiki_implicit,
            "outcome": "matched" if wiki_explicit > wiki_implicit else "contradicted",
        },
        "B-G-outdated": {
            "expected": "positive",
            "delta": google_outdated,
            "outcome": "matched" if google_outdated > 0.0 else "contradicted",
        },
        "B-G-misinfo": {
            "expected": "indeterminate_n5",
            "delta": google_misinfo,
            "outcome": "descriptive_only",
        },
        "B-G-safe": {
            "expected": "noninferior_minus_0_03",
            "delta": google_safe,
            "outcome": "matched" if google_safe >= -0.03 else "safety_violated",
        },
    }
    return {
        "schema_version": "far-boundary-result-v1",
        "protocol_fingerprint": BOUNDARY_ACTIVE_SHA256,
        "comparisons": comparisons,
        "strata": strata,
        "holm_adjusted_mcnemar": _holm(p_values),
        "hypotheses": hypotheses,
        "global_pass_fail": None,
        "gate_b_complete": True,
        "gate_p_completed": True,
        "adequately_powered": False,
        "required_claim_level": "directional_boundary_mapping",
        "formal_pipeline_samples": 600,
        "calibration_pipeline_samples": 20,
        "api_cost_usd": 0,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }


def _report_text(result: dict[str, Any]) -> str:
    lines = [
        "# FAR 外部冲突边界矩阵 (WS3)",
        "",
        "> 两个公开 dev 诊断、Qwen 单模型、方向性功效；不是全局胜负、FAR 真人 IAA 或盲测。",
        "",
        "| 基准 | typed-untyped 主分数 | 95% CI | McNemar p | Holm p |",
        "|---|---:|---:|---:|---:|",
    ]
    for dataset in DATASET_ORDER:
        row = result["comparisons"][dataset]
        comparison = row["comparison"]
        lines.append(
            f"| {dataset} | {comparison['candidate_minus_baseline']:+.4f} | "
            f"[{comparison['lower']:+.4f}, {comparison['upper']:+.4f}] | "
            f"{row['mcnemar']['p_value']:.6f} | "
            f"{result['holm_adjusted_mcnemar'][dataset]:.6f} |"
        )
    lines.extend(["", "## 预注册预测对照", "", "| 假设 | 结果 |", "|---|---|"])
    for key, row in result["hypotheses"].items():
        lines.append(f"| {key} | `{row['outcome']}` |")
    lines.extend(
        [
            "",
            "G-B 只表示制品完整，不存在全局通过/失败。功效低于 0.60，null 不能证明无效；"
            "任何正方向也只描述该基准、该 dev 抽样和 Qwen 的边界。RAMDocs 双失败保持不变。",
            "",
        ]
    )
    return "\n".join(lines)


def finalize(output_root: Path, report_path: Path) -> dict[str, Any]:
    if (output_root / "manifest.json").exists():
        raise FileExistsError("boundary release is already finalized")
    for dataset in DATASET_ORDER:
        for method in METHODS:
            evaluate_run(
                dataset,
                output_root / "runs" / dataset / method / "predictions.jsonl",
                output_root / "evaluations" / dataset / method,
            )
    result = compute_boundary_result(output_root)
    source_commits = {
        json.loads(
            (output_root / "runs" / dataset / method / "run_identity.json").read_text(
                encoding="utf-8"
            )
        )
        .get("source_revision", {})
        .get("git_commit")
        for dataset in DATASET_ORDER
        for method in METHODS
    }
    if len(source_commits) != 1 or None in source_commits:
        raise ValueError("boundary release mixes formal source commits")
    source_commit = next(iter(source_commits))
    result["source_commit"] = source_commit
    write_json(output_root / "result.json", result)
    report = _report_text(result)
    (output_root / "boundary_matrix.md").write_text(report, encoding="utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    artifacts = {
        str(path.relative_to(output_root)): sha256_file(path)
        for path in sorted(output_root.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    manifest = {
        "schema_version": "far-boundary-release-v1",
        "protocol_fingerprint": BOUNDARY_ACTIVE_SHA256,
        "source_commit": source_commit,
        "artifacts": artifacts,
        "external_report_sha256": sha256_file(report_path),
        "gate_b_complete": True,
        "global_pass_fail": None,
        "formal_pipeline_samples": 600,
        "calibration_pipeline_samples": 20,
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
    run = subparsers.add_parser("run")
    run.add_argument("--dataset", choices=DATASET_ORDER, required=True)
    run.add_argument("--method", choices=METHODS, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--calibration", action="store_true")
    run_all_parser = subparsers.add_parser("run-all")
    run_all_parser.add_argument("--output-dir", type=Path, required=True)
    finish = subparsers.add_parser("finalize")
    finish.add_argument("--output-dir", type=Path, required=True)
    finish.add_argument("--report", type=Path, default=Path("reports/boundary_matrix.md"))
    args = parser.parse_args()
    if args.command == "run":
        result = run_method(
            args.dataset,
            args.output_dir,
            method=args.method,
            calibration=args.calibration,
        )
    elif args.command == "run-all":
        result = run_all(args.output_dir)
    else:
        result = finalize(args.output_dir, args.report)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
