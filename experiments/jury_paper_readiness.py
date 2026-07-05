"""Fail-closed paper gate for the preregistered 2+4 evidence profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bench.build.common import sha256_file, write_json
from bench.build.ramdocs import verify_ramdocs
from experiments.protocol_2plus4 import PROTOCOL_ACTIVE_SHA256, ROOT, verify_active_protocol
from experiments.ramdocs_round2 import verify_round
from experiments.ramdocs_suite import verify_suite

REQUIRED_DISCLOSURES = (
    "cross-family LLM jury",
    "author-blind adjudication",
    "not human inter-annotator agreement",
    "not externally held",
    "refutation and boundary",
    "typed revision",
    "FEVER",
    "RAMDocs",
    "upstream labels",
    "7--9B",
)
FORBIDDEN_CLAIMS = (
    "independent human gold",
    "human inter-annotator agreement confirms",
    "externally held blind test",
    "every FAR component improves",
    "frontier closed-model generality",
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _safe_json(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    try:
        return _json(path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"{label}: {exc}")
        return {}


def audit(
    ramdocs_data: Path,
    ramdocs_dev_suite: Path,
    jury_consensus_report: Path,
    jury_labels_manifest: Path,
    sensitivity_report: Path,
    matrix_report: Path,
    falsirag_test_seal: Path,
    falsirag_test_score: Path,
    ramdocs_test_seal: Path,
    ramdocs_test_score: Path,
    paper_main: Path,
    *,
    ramdocs_round2_dir: Path | None = None,
    ramdocs_round2_config: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    checks: dict[str, bool] = {}
    try:
        verify_active_protocol()
        checks["active_protocol_frozen"] = True
    except ValueError as exc:
        errors.append(str(exc))
        checks["active_protocol_frozen"] = False

    ramdocs_import = verify_ramdocs(ramdocs_data)
    checks["ramdocs_import_valid"] = ramdocs_import.get("valid") is True
    errors.extend(f"RAMDocs import: {item}" for item in ramdocs_import.get("errors", []))

    ramdocs_dev = verify_suite(ramdocs_dev_suite, ramdocs_data)
    checks["ramdocs_dev_suite_valid"] = ramdocs_dev.get("valid") is True
    errors.extend(f"RAMDocs dev: {item}" for item in ramdocs_dev.get("errors", []))
    gate_a_passed = ramdocs_dev.get("gate_a_passed") is True
    if (
        not gate_a_passed
        and ramdocs_round2_dir is not None
        and ramdocs_round2_config is not None
        and (ramdocs_round2_dir / "round_manifest.json").is_file()
    ):
        round2 = verify_round(
            ramdocs_data,
            ramdocs_dev_suite,
            ramdocs_round2_dir,
            ramdocs_round2_config,
        )
        checks["ramdocs_dev_round2_valid"] = round2.get("valid") is True
        errors.extend(f"RAMDocs Round 2: {item}" for item in round2.get("errors", []))
        gate_a_passed = round2.get("valid") is True and round2.get("gate_a_passed") is True
    checks["gate_a_external_passed"] = gate_a_passed
    if not checks["gate_a_external_passed"]:
        errors.append("G-A external validation gate has not passed")

    consensus = _safe_json(jury_consensus_report, errors, "jury consensus")
    checks["gate_k_jury_passed"] = (
        consensus.get("gate_k_passed") is True
        and consensus.get("zero_fallbacks") is True
        and consensus.get("protocol_fingerprint") == PROTOCOL_ACTIVE_SHA256
    )
    if not checks["gate_k_jury_passed"]:
        errors.append("G-K jury agreement gate has not passed without fallbacks")

    labels = _safe_json(jury_labels_manifest, errors, "jury labels")
    labels_path = jury_labels_manifest.parent / str(labels.get("labels_file", "labels.jsonl"))
    labels_fingerprint_valid = labels_path.is_file() and sha256_file(labels_path) == labels.get(
        "labels_sha256"
    )
    checks["gate_s_author_passed"] = labels.get("gate_s_passed") is True
    checks["jury_labels_valid"] = (
        labels.get("jury_gold") is True
        and labels.get("publication_gold") is False
        and labels.get("human_iaa") is False
        and labels.get("protocol_fingerprint") == PROTOCOL_ACTIVE_SHA256
        and labels_fingerprint_valid
    )
    if not checks["gate_s_author_passed"]:
        errors.append("G-S author self-consistency gate has not passed")
    if not checks["jury_labels_valid"]:
        errors.append("compiled jury label layer is missing, stale, or unsafe")

    sensitivity = _safe_json(sensitivity_report, errors, "label sensitivity")
    checks["three_view_label_sensitivity_ready"] = (
        sensitivity.get("schema_version") == "far-jury-label-sensitivity-v1"
        and sensitivity.get("protocol_fingerprint") == PROTOCOL_ACTIVE_SHA256
        and set(sensitivity.get("views", {})) == {"construction", "jury_gold", "unanimous_only"}
        and bool(sensitivity.get("rows"))
    )
    if not checks["three_view_label_sensitivity_ready"]:
        errors.append("construction/jury/unanimous sensitivity report is not ready")

    matrix = _safe_json(matrix_report, errors, "model matrix")
    checks["three_family_matrix_ready"] = (
        matrix.get("three_family_claim_ready") is True
        and matrix.get("typed_answer_gain_same_direction") is True
        and matrix.get("conflict_gain_same_direction") is True
        and matrix.get("label_granularity") in {"six_class", "binary"}
        and matrix.get("protocol_fingerprint") == PROTOCOL_ACTIVE_SHA256
    )
    if not checks["three_family_matrix_ready"]:
        errors.append("three-family jury-gold typed-control matrix is not ready")

    label_granularities = {
        consensus.get("active_label_granularity"),
        labels.get("label_granularity"),
        sensitivity.get("label_granularity"),
        matrix.get("label_granularity"),
    }
    checks["jury_label_granularity_consistent"] = (
        len(label_granularities) == 1
        and next(iter(label_granularities), None) in {"six_class", "binary"}
    )
    if checks["jury_label_granularity_consistent"]:
        granularity = next(iter(label_granularities))
        expected_metric = (
            "conflict_presence_f1" if granularity == "binary" else "typed_conflict_f1"
        )
        checks["jury_conflict_metric_matches_granularity"] = (
            matrix.get("conflict_metric") == expected_metric
            and expected_metric in sensitivity.get("metrics", [])
        )
    else:
        checks["jury_conflict_metric_matches_granularity"] = False
        errors.append(
            "jury consensus, labels, sensitivity, and matrix label-granularity chain "
            "is incomplete or inconsistent"
        )
    if checks["jury_label_granularity_consistent"] and not checks[
        "jury_conflict_metric_matches_granularity"
    ]:
        errors.append("jury conflict metric does not match the active label granularity")

    for target, path, score_path, expected_samples in (
        ("falsirag", falsirag_test_seal, falsirag_test_score, 58),
        ("ramdocs", ramdocs_test_seal, ramdocs_test_score, 150),
    ):
        seal = _safe_json(path, errors, f"{target} one-shot seal")
        score_hash_matches = score_path.is_file() and seal.get(
            "score_manifest_sha256"
        ) == sha256_file(score_path)
        passed = (
            seal.get("schema_version") == "far-one-shot-seal-v1"
            and seal.get("target") == target
            and seal.get("one_shot") is True
            and seal.get("externally_held") is False
            and seal.get("fingerprint_chain_valid") is True
            and seal.get("protocol_fingerprint") == PROTOCOL_ACTIVE_SHA256
            and seal.get("scored_samples") == expected_samples
            and score_hash_matches
        )
        checks[f"{target}_one_shot_complete"] = passed
        if not passed:
            errors.append(f"{target} committed one-shot test chain is incomplete")

    try:
        paper = paper_main.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        errors.append(f"paper: {exc}")
        paper = ""
    missing_disclosures = [phrase for phrase in REQUIRED_DISCLOSURES if phrase not in paper]
    forbidden_found = [phrase for phrase in FORBIDDEN_CLAIMS if phrase.lower() in paper.lower()]
    checks["paper_disclosures_complete"] = not missing_disclosures
    checks["paper_forbidden_claims_absent"] = not forbidden_found
    if missing_disclosures:
        errors.append(f"paper missing mandatory 2+4 disclosures: {missing_disclosures}")
    if forbidden_found:
        errors.append(f"paper contains forbidden claims: {forbidden_found}")

    errors = [item.replace(f"{ROOT.as_posix()}/", "") for item in errors]
    ready = all(checks.values())
    return {
        "schema_version": "far-jury-paper-readiness-v1",
        "study_profile": "cross_family_jury_external_validation_paper",
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "ready": ready,
        "human_gate_replaced_for_this_profile": True,
        "strict_independent_human_profile_ready": False,
        "can_claim_human_iaa": False,
        "can_claim_externally_held_blind": False,
        "checks": checks,
        "errors": list(dict.fromkeys(errors)),
        "missing_disclosures": missing_disclosures,
        "forbidden_claims_found": forbidden_found,
        "evidence": {
            "ramdocs_manifest_sha256": (
                sha256_file(ramdocs_data / "manifest.json")
                if (ramdocs_data / "manifest.json").is_file()
                else None
            ),
            "ramdocs_round2_manifest_sha256": (
                sha256_file(ramdocs_round2_dir / "round_manifest.json")
                if ramdocs_round2_dir is not None
                and (ramdocs_round2_dir / "round_manifest.json").is_file()
                else None
            ),
            "jury_consensus_sha256": (
                sha256_file(jury_consensus_report) if jury_consensus_report.is_file() else None
            ),
            "jury_labels_manifest_sha256": (
                sha256_file(jury_labels_manifest) if jury_labels_manifest.is_file() else None
            ),
            "matrix_report_sha256": sha256_file(matrix_report) if matrix_report.is_file() else None,
            "paper_sha256": sha256_file(paper_main) if paper_main.is_file() else None,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ramdocs-data", type=Path, default=ROOT / "bench/external/ramdocs_v1")
    parser.add_argument(
        "--ramdocs-dev-suite", type=Path, default=ROOT / "diagnostics/ramdocs_v1/dev"
    )
    parser.add_argument(
        "--ramdocs-round2-dir", type=Path, default=ROOT / "diagnostics/ramdocs_v2/dev"
    )
    parser.add_argument(
        "--ramdocs-round2-config",
        type=Path,
        default=ROOT / "experiments/configs/ramdocs_qwen_round2.yaml",
    )
    parser.add_argument(
        "--jury-consensus-report",
        type=Path,
        default=ROOT / "diagnostics/jury_v1/consensus/jury_consensus_report.json",
    )
    parser.add_argument(
        "--jury-labels-manifest",
        type=Path,
        default=ROOT / "bench/labels_jury_v1/manifest.json",
    )
    parser.add_argument(
        "--sensitivity-report",
        type=Path,
        default=ROOT / "diagnostics/jury_v1/qwen_sensitivity/sensitivity_report.json",
    )
    parser.add_argument(
        "--matrix-report",
        type=Path,
        default=ROOT / "diagnostics/jury_v1/model_matrix.json",
    )
    parser.add_argument(
        "--falsirag-test-seal",
        type=Path,
        default=ROOT / "diagnostics/jury_v1/falsirag_test/one_shot_seal.json",
    )
    parser.add_argument(
        "--ramdocs-test-seal",
        type=Path,
        default=ROOT / "diagnostics/ramdocs_v1/test/one_shot_seal.json",
    )
    parser.add_argument(
        "--falsirag-test-score",
        type=Path,
        default=ROOT / "diagnostics/jury_v1/falsirag_test/matrix_family_manifest.json",
    )
    parser.add_argument(
        "--ramdocs-test-score",
        type=Path,
        default=ROOT / "diagnostics/ramdocs_v1/test/suite_manifest.json",
    )
    parser.add_argument("--paper-main", type=Path, default=ROOT / "paper/main.tex")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(
        args.ramdocs_data,
        args.ramdocs_dev_suite,
        args.jury_consensus_report,
        args.jury_labels_manifest,
        args.sensitivity_report,
        args.matrix_report,
        args.falsirag_test_seal,
        args.falsirag_test_score,
        args.ramdocs_test_seal,
        args.ramdocs_test_score,
        args.paper_main,
        ramdocs_round2_dir=args.ramdocs_round2_dir,
        ramdocs_round2_config=args.ramdocs_round2_config,
    )
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not result["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
