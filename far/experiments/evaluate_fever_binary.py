"""Evaluate FAR conflict detection against inherited FEVER binary labels.

The external pair transformation contains machine-generated typed buckets, but
its SUPPORTS/REFUTES labels and evidence originate in the human-annotated FEVER
dataset.  This evaluator therefore scores only binary conflict detection.  It
never treats the typed buckets as gold and never presents this visible slice as
an externally held blind test or a full FAR pipeline evaluation.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import yaml

from far.adapters.conflict import HeuristicConflictDetector, VeraConflictDetector
from far.bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.claims import ClaimNode, RuleBasedClaimDecomposer
from far.eval.stats import mcnemar_exact, paired_bootstrap_comparison, stratified_bootstrap_ci
from far.evidence_types import TypedConflict
from far.models import EvidenceDocument

REPORT_VERSION = "far-fever-binary-evaluation-v1"
AUDIT_VERSION = "far-fever-binary-evaluation-audit-v1"
ALLOWED_LABELS = {"SUPPORTS", "REFUTES"}
OFFICIAL_FEVER_URL = "https://fever.ai/dataset/fever.html"
UPSTREAM_DATASET_URL = "https://huggingface.co/datasets/copenlu/fever_gold_evidence"


class BinaryDetector(Protocol):
    def detect(
        self,
        claim: ClaimNode,
        evidence: EvidenceDocument,
        *,
        question: str = "",
    ) -> tuple[TypedConflict, ...]: ...


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def validate_source(data_dir: Path) -> dict[str, Any]:
    manifest_path = data_dir / "manifest.json"
    upstream_path = data_dir / "upstream_manifest.json"
    questions_path = data_dir / "questions.jsonl"
    corpus_path = data_dir / "corpus.jsonl"
    manifest = _json(manifest_path)
    upstream = _json(upstream_path)
    questions = read_jsonl(questions_path)
    corpus = read_jsonl(corpus_path)
    errors: list[str] = []

    expected_fingerprints = {
        "questions_sha256": sha256_file(questions_path),
        "corpus_sha256": sha256_file(corpus_path),
        "upstream_manifest_sha256": sha256_file(upstream_path),
    }
    if manifest.get("fingerprints") != expected_fingerprints:
        errors.append("external slice fingerprints differ from manifest")
    if (
        upstream.get("fingerprints", {}).get("questions_sha256")
        != expected_fingerprints["questions_sha256"]
    ):
        errors.append("upstream manifest points to different questions")
    if (
        upstream.get("fingerprints", {}).get("corpus_sha256")
        != expected_fingerprints["corpus_sha256"]
    ):
        errors.append("upstream manifest points to different corpus")
    if manifest.get("publication_gold") is not False:
        errors.append("typed external candidate must remain publication_gold:false")
    if len(questions) != 100 or len(corpus) != 200:
        errors.append("expected exactly 100 question pairs and 200 documents")
    if len({str(row.get("id")) for row in questions}) != len(questions):
        errors.append("duplicate external question IDs")
    if len({str(row.get("doc_id")) for row in corpus}) != len(corpus):
        errors.append("duplicate external document IDs")

    labels: Counter[str] = Counter()
    typed_buckets: Counter[str] = Counter()
    for row in questions:
        sample_id = str(row.get("id", ""))
        metadata = row.get("source_metadata", {})
        label = str(metadata.get("fever_label", ""))
        labels[label] += 1
        typed_buckets[str(metadata.get("sampling_bucket", ""))] += 1
        evidence = row.get("evidence", [])
        claims = row.get("ground_truth_claims", [])
        if label not in ALLOWED_LABELS:
            errors.append(f"{sample_id}: unsupported or missing FEVER label")
            continue
        if not isinstance(evidence, list) or len(evidence) != 2:
            errors.append(f"{sample_id}: expected exactly two visible evidence objects")
            continue
        if not isinstance(claims, list) or len(claims) != 1:
            errors.append(f"{sample_id}: expected exactly one inherited claim record")
            continue
        claim_text = str(evidence[0].get("text_span", "")).strip()
        source_text = str(evidence[1].get("text_span", "")).strip()
        if not claim_text or not source_text or str(claims[0].get("claim", "")) != claim_text:
            errors.append(f"{sample_id}: visible claim/evidence text is incomplete or inconsistent")
        expected_status = "refuted" if label == "REFUTES" else "supported"
        if claims[0].get("status") != expected_status:
            errors.append(f"{sample_id}: transformed status disagrees with FEVER label")
        expected_conflict = label == "REFUTES"
        if (row.get("expected_behavior") == "answer_with_conflict_note") != expected_conflict:
            errors.append(f"{sample_id}: behavior disagrees with FEVER label")
        expected_conflicts = row.get("expected_conflicts", [])
        if bool(expected_conflicts) != expected_conflict:
            errors.append(f"{sample_id}: typed seed presence disagrees with FEVER label")

    return {
        "schema_version": "far-fever-binary-source-audit-v1",
        "valid": not errors,
        "errors": errors,
        "questions": len(questions),
        "documents": len(corpus),
        "labels": dict(sorted(labels.items())),
        "machine_typed_buckets": dict(sorted(typed_buckets.items())),
        "fingerprints": expected_fingerprints,
        "binary_reference": {
            "source": "human-annotated FEVER SUPPORTS/REFUTES labels and gold evidence",
            "official_fever_url": OFFICIAL_FEVER_URL,
            "upstream_dataset_url": UPSTREAM_DATASET_URL,
        },
        "typed_bucket_publication_gold": False,
    }


def _prepare_output(output_dir: Path, *, overwrite: bool) -> None:
    if not output_dir.exists():
        output_dir.mkdir(parents=True)
        return
    if not any(output_dir.iterdir()):
        return
    if not overwrite:
        raise FileExistsError("FEVER evaluation output directory must be empty")
    report_path = output_dir / "report.json"
    if not report_path.is_file() or _json(report_path).get("schema_version") != REPORT_VERSION:
        raise ValueError("refusing to overwrite a directory not owned by FAR FEVER evaluation")
    shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)


def _detector(name: str, config: dict[str, Any] | None) -> BinaryDetector:
    if name == "heuristic":
        return HeuristicConflictDetector()
    if name == "vera_nli":
        if config is None:
            raise ValueError("vera_nli requires --config")
        return VeraConflictDetector(config=config)
    raise ValueError(f"unsupported detector: {name}")


def _row_prediction(
    row: dict[str, Any], detector: BinaryDetector, decomposer: RuleBasedClaimDecomposer
) -> dict[str, Any]:
    evidence = row["evidence"]
    claim_text = str(evidence[0]["text_span"])
    evidence_text = str(evidence[1]["text_span"])
    claim = decomposer.decompose(claim_text).claims[0]
    document = EvidenceDocument(
        evidence_id=str(evidence[1]["evidence_id"]),
        text=evidence_text,
        title=str(row.get("source_metadata", {}).get("wikipedia_title", "")),
        source="wiki",
        score=1.0,
    )
    if isinstance(detector, VeraConflictDetector):
        conflicts = detector.detect_many(claim, (document,), question=str(row["question"]))
    else:
        conflicts = detector.detect(claim, document, question=str(row["question"]))
    label = str(row["source_metadata"]["fever_label"])
    gold_conflict = label == "REFUTES"
    predicted_conflict = bool(conflicts)
    return {
        "sample_id": str(row["id"]),
        "category": label,
        "upstream_fever_label": label,
        "gold_binary_conflict": gold_conflict,
        "predicted_binary_conflict": predicted_conflict,
        "correct": float(gold_conflict == predicted_conflict),
        "predicted_conflict_types": sorted(
            {conflict.conflict_type.value for conflict in conflicts}
        ),
        "predicted_conflicts": [conflict.to_dict() for conflict in conflicts],
        "machine_sampling_bucket": str(row["source_metadata"]["sampling_bucket"]),
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(
        bool(row["gold_binary_conflict"]) and bool(row["predicted_binary_conflict"]) for row in rows
    )
    fp = sum(
        not bool(row["gold_binary_conflict"]) and bool(row["predicted_binary_conflict"])
        for row in rows
    )
    fn = sum(
        bool(row["gold_binary_conflict"]) and not bool(row["predicted_binary_conflict"])
        for row in rows
    )
    tn = len(rows) - tp - fp - fn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    by_bucket: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_bucket[str(row["machine_sampling_bucket"])].append(float(row["correct"]))
    return {
        "samples": len(rows),
        "accuracy": sum(float(row["correct"]) for row in rows) / len(rows),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "accuracy_by_machine_sampling_bucket": {
            bucket: sum(values) / len(values) for bucket, values in sorted(by_bucket.items())
        },
    }


def _readme(methods: dict[str, dict[str, Any]], comparisons: dict[str, Any]) -> str:
    lines = [
        "# FEVER binary transfer diagnostic",
        "",
        "This frozen diagnostic evaluates binary conflict detection on 100 visible",
        "FEVER claim-to-gold-evidence pairs: 40 inherited REFUTES positives and 60",
        "inherited SUPPORTS negatives.",
        "",
        "The SUPPORTS/REFUTES reference comes from human-annotated FEVER labels.",
        "The temporal/numeric/source/definition buckets were generated heuristically",
        "and are used only for descriptive slices; they are not typed gold.",
        "",
        "## Results",
        "",
        "| Detector | Accuracy | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, summary in methods.items():
        metrics = summary["metrics"]
        lines.append(
            f"| {name} | {metrics['accuracy']:.3f} | {metrics['precision']:.3f} | "
            f"{metrics['recall']:.3f} | {metrics['f1']:.3f} |"
        )
    if comparisons:
        comparison = next(iter(comparisons.values()))
        accuracy = comparison["accuracy"]
        mcnemar = comparison["mcnemar"]
        lines.extend(
            [
                "",
                "The paired accuracy difference is "
                f"{accuracy['candidate_minus_baseline']:+.3f} "
                f"(95% bootstrap [{accuracy['lower']:+.3f}, {accuracy['upper']:+.3f}]); "
                f"exact McNemar p={mcnemar['p_value']:.3f}.",
            ]
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "This is a visible external-slice binary transfer diagnostic. It is not a",
            "full FAR pipeline result, typed-conflict gold, an externally held blind test,",
            "or a publication-ready main result. The frozen result is intentionally not",
            "tuned after inspection.",
            "",
            f"- FEVER dataset: {OFFICIAL_FEVER_URL}",
            f"- Pinned gold-evidence derivative: {UPSTREAM_DATASET_URL}",
            "",
        ]
    )
    return "\n".join(lines)


def evaluate(
    data_dir: Path,
    output_dir: Path,
    *,
    detector_names: list[str],
    config_path: Path | None = None,
    resamples: int = 2000,
    seed: int = 1729,
    overwrite: bool = False,
) -> dict[str, Any]:
    source_audit = validate_source(data_dir)
    if not source_audit["valid"]:
        raise ValueError(f"FEVER source audit failed: {source_audit['errors']}")
    if not detector_names or len(set(detector_names)) != len(detector_names):
        raise ValueError("detector names must be non-empty and unique")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path else None
    if config is not None and not isinstance(config, dict):
        raise ValueError("detector config must be a YAML mapping")
    _prepare_output(output_dir, overwrite=overwrite)
    config_file = None
    if config_path is not None:
        config_file = "detector_config.yaml"
        shutil.copyfile(config_path, output_dir / config_file)
    questions = read_jsonl(data_dir / "questions.jsonl")
    decomposer = RuleBasedClaimDecomposer()
    methods: dict[str, dict[str, Any]] = {}
    all_rows: dict[str, list[dict[str, Any]]] = {}
    for name in detector_names:
        detector = _detector(name, config)
        rows = [_row_prediction(row, detector, decomposer) for row in questions]
        predictions_path = output_dir / f"predictions_{name}.jsonl"
        write_jsonl(predictions_path, rows)
        all_rows[name] = rows
        methods[name] = {
            "metrics": _metrics(rows),
            "accuracy_ci": stratified_bootstrap_ci(
                rows,
                "correct",
                resamples=resamples,
                seed=seed,
                strata_key="category",
            ),
            "predictions_file": predictions_path.name,
            "predictions_sha256": sha256_file(predictions_path),
        }

    comparisons: dict[str, Any] = {}
    baseline = detector_names[0]
    for candidate in detector_names[1:]:
        key = f"{candidate}_vs_{baseline}"
        comparisons[key] = {
            "accuracy": paired_bootstrap_comparison(
                all_rows[baseline],
                all_rows[candidate],
                "correct",
                resamples=resamples,
                seed=seed,
            ),
            "mcnemar": mcnemar_exact(
                [bool(row["correct"]) for row in all_rows[baseline]],
                [bool(row["correct"]) for row in all_rows[candidate]],
            ),
        }

    readme_path = output_dir / "README.md"
    readme_path.write_text(_readme(methods, comparisons), encoding="utf-8")

    report = {
        "schema_version": REPORT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "study_profile": "external_fever_binary_transfer_diagnostic",
        "source_audit": source_audit,
        "source_manifest_sha256": sha256_file(data_dir / "manifest.json"),
        "config_file": config_file,
        "config_sha256": sha256_file(output_dir / config_file) if config_file else None,
        "readme_sha256": sha256_file(readme_path),
        "methods": methods,
        "paired_comparisons": comparisons,
        "interpretation": {
            "binary_labels_inherited_from_human_annotated_fever": True,
            "typed_buckets_are_machine_seeded": True,
            "typed_bucket_publication_gold": False,
            "full_far_pipeline_evaluated": False,
            "externally_held_blind_test": False,
            "publication_ready_main_result": False,
            "allowed_claim": (
                "visible external-slice binary conflict-detection transfer diagnostic"
            ),
        },
    }
    write_json(output_dir / "report.json", report)
    audit = verify_evaluation(data_dir, output_dir)
    if not audit["valid"]:
        raise ValueError(f"created FEVER evaluation failed verification: {audit['errors']}")
    return report


def verify_evaluation(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        source_audit = validate_source(data_dir)
        if not source_audit["valid"]:
            errors.extend(source_audit["errors"])
        questions = read_jsonl(data_dir / "questions.jsonl")
        expected_labels = {
            str(row["id"]): str(row["source_metadata"]["fever_label"]) for row in questions
        }
        report = _json(output_dir / "report.json")
        if report.get("schema_version") != REPORT_VERSION:
            errors.append("unsupported FEVER evaluation report")
        if report.get("source_manifest_sha256") != sha256_file(data_dir / "manifest.json"):
            errors.append("FEVER evaluation points to a different source manifest")
        if report.get("source_audit") != source_audit:
            errors.append("stored FEVER source audit is stale or modified")
        interpretation = report.get("interpretation", {})
        required_flags = {
            "binary_labels_inherited_from_human_annotated_fever": True,
            "typed_buckets_are_machine_seeded": True,
            "typed_bucket_publication_gold": False,
            "full_far_pipeline_evaluated": False,
            "externally_held_blind_test": False,
            "publication_ready_main_result": False,
        }
        for key, expected in required_flags.items():
            if interpretation.get(key) is not expected:
                errors.append(f"unsafe or missing interpretation flag: {key}")
        expected_files = {"report.json"}
        readme_path = output_dir / "README.md"
        expected_files.add(readme_path.name)
        if sha256_file(readme_path) != report.get("readme_sha256"):
            errors.append("FEVER evaluation README fingerprint mismatch")
        config_file = report.get("config_file")
        if config_file:
            config_path = output_dir / str(config_file)
            expected_files.add(config_path.name)
            if sha256_file(config_path) != report.get("config_sha256"):
                errors.append("FEVER evaluation config fingerprint mismatch")
        all_rows: dict[str, list[dict[str, Any]]] = {}
        for method, summary in report.get("methods", {}).items():
            path = output_dir / str(summary["predictions_file"])
            expected_files.add(path.name)
            if path.is_symlink():
                errors.append(f"{method}: predictions must not be a symlink")
                continue
            if sha256_file(path) != summary.get("predictions_sha256"):
                errors.append(f"{method}: predictions fingerprint mismatch")
            rows = read_jsonl(path)
            all_rows[str(method)] = rows
            if len(rows) != 100 or len({row.get("sample_id") for row in rows}) != 100:
                errors.append(f"{method}: predictions are incomplete or duplicated")
            if {str(row.get("sample_id")) for row in rows} != set(expected_labels):
                errors.append(f"{method}: prediction IDs differ from FEVER source")
            for row in rows:
                sample_id = str(row.get("sample_id"))
                label = expected_labels.get(sample_id)
                expected_conflict = label == "REFUTES"
                predicted_conflicts = row.get("predicted_conflicts", [])
                predicted_types = sorted(
                    {
                        str(conflict.get("conflict_type"))
                        for conflict in predicted_conflicts
                        if isinstance(conflict, dict)
                    }
                )
                predicted_conflict = bool(predicted_conflicts)
                if (
                    row.get("upstream_fever_label") != label
                    or row.get("category") != label
                    or row.get("gold_binary_conflict") is not expected_conflict
                    or row.get("predicted_binary_conflict") is not predicted_conflict
                    or row.get("predicted_conflict_types") != predicted_types
                    or float(row.get("correct", -1.0))
                    != float(expected_conflict == predicted_conflict)
                ):
                    errors.append(f"{method}: inconsistent prediction row {sample_id}")
                    break
            if _metrics(rows) != summary.get("metrics"):
                errors.append(f"{method}: stored metrics do not match predictions")
            interval = summary.get("accuracy_ci", {})
            recomputed_interval = stratified_bootstrap_ci(
                rows,
                "correct",
                resamples=int(interval.get("resamples", 0)),
                confidence=float(interval.get("confidence", 0.0)),
                seed=int(interval.get("seed", 0)),
                strata_key="category",
            )
            if recomputed_interval != interval:
                errors.append(f"{method}: stored confidence interval does not match predictions")
        for name, comparison in report.get("paired_comparisons", {}).items():
            if "_vs_" not in name:
                errors.append(f"invalid paired comparison name: {name}")
                continue
            candidate, baseline = name.split("_vs_", 1)
            if candidate not in all_rows or baseline not in all_rows:
                errors.append(f"paired comparison references unknown method: {name}")
                continue
            interval = comparison.get("accuracy", {})
            recomputed_comparison = paired_bootstrap_comparison(
                all_rows[baseline],
                all_rows[candidate],
                "correct",
                resamples=int(interval.get("resamples", 0)),
                confidence=float(interval.get("confidence", 0.0)),
                seed=int(interval.get("seed", 0)),
            )
            recomputed_mcnemar = mcnemar_exact(
                [bool(row["correct"]) for row in all_rows[baseline]],
                [bool(row["correct"]) for row in all_rows[candidate]],
            )
            if recomputed_comparison != interval or recomputed_mcnemar != comparison.get("mcnemar"):
                errors.append(f"stored paired comparison does not match predictions: {name}")
        actual_files = {path.name for path in output_dir.iterdir() if path.is_file()}
        if actual_files != expected_files:
            errors.append("FEVER evaluation file set is incomplete or contains extras")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": AUDIT_VERSION,
        "valid": not errors,
        "errors": errors,
        "publication_ready_main_result": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument(
        "--data-dir", type=Path, default=Path("bench/external/fever_pair_candidates_v1")
    )
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--detector", action="append", required=True)
    run.add_argument("--config", type=Path)
    run.add_argument("--resamples", type=int, default=2000)
    run.add_argument("--seed", type=int, default=1729)
    run.add_argument("--overwrite", action="store_true")
    verify = subparsers.add_parser("verify")
    verify.add_argument(
        "--data-dir", type=Path, default=Path("bench/external/fever_pair_candidates_v1")
    )
    verify.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        result = evaluate(
            args.data_dir,
            args.output_dir,
            detector_names=args.detector,
            config_path=args.config,
            resamples=args.resamples,
            seed=args.seed,
            overwrite=args.overwrite,
        )
    else:
        result = verify_evaluation(args.data_dir, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "verify" and not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
