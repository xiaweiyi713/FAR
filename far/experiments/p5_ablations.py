"""Run, finalize, and verify the registered P5 RAMDocs ablations."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from far.adapters.model_assets import resolve_huggingface_snapshot
from far.bench.build.common import read_jsonl, sha256_file, write_json
from far.eval.ramdocs import evaluate_ramdocs
from far.eval.stats import paired_sample_cluster_bootstrap_comparison
from far.experiments.run_ramdocs import run_method
from far.experiments.runner import (
    _llm_runtime_identity,
    _source_revision,
    load_config,
)
from far.paths import benchmark_data_dir, experiment_config_dir, repository_root

ROOT = repository_root()
SCHEMA_VERSION = "far-p5-ramdocs-ablations-v1"
AUDIT_SCHEMA_VERSION = "far-p5-ramdocs-ablations-audit-v1"
PROTOCOL_PATH = ROOT / "docs/PREREG_ORACLE_ATTRIBUTION_AMENDMENT_2026-07-10_P5_ABLATIONS.md"
PROTOCOL_SHA256 = "59207d5e4bd51e448d41c465b2789149e6f26516847757287fbedc039b91d937"
PREREG_TAG = "prereg-p5-ablations-v1"
PREREG_COMMIT = "f135766bbe90deb42f55b420a211516b55c46f65"
CONFIG_SHA256 = "a5e63643acab84ae26fc190d42931ac95b0fa4f84f9bec4aa7c3a70b18c9f6cb"
INITIAL_ANSWERS_SHA256 = "5fbcea9b6b2a6cc1136e87d8bb7a2335feebe8b5e2f5b1f54afcd78a7abbbc6b"
MODEL_DIGEST = "6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7"
DATA_FINGERPRINTS = {
    "manifest.json": "5cd9ff842789afd69fa8e64ff89c0f85eca2f8bc934aa4c694aeec92388074df",
    "corpus.jsonl": "219269fedcdc21c9bd87b045a5afd1e7ce60c22ea21f4c1e8ded9c7658d61496",
    "splits/dev.jsonl": "412e65b77dec89da9358499c39a714876606958373f3ae0f284a5b2fb20d6a9f",
}
METHODS = {
    "full": "far",
    "minus_typed_revision_aggressive": "far_minus_typed_revision_aggressive",
    "flat_claims": "far_flat_claims",
}
HYPOTHESES = {
    "H3": "minus_typed_revision_aggressive",
    "H5": "flat_claims",
}
EQUIVALENCE_BOUNDS = (-0.02, 0.02)
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_CONFIDENCE = 0.90
BOOTSTRAP_SEED = 1729


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _git_ancestor(commit: str) -> bool:
    try:
        completed = subprocess.run(
            ["git", "merge-base", "--is-ancestor", PREREG_COMMIT, commit],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
    except OSError:
        return False
    return completed.returncode == 0


def _input_audit(data_dir: Path, initial_answers: Path, config_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    if not PROTOCOL_PATH.is_file() or sha256_file(PROTOCOL_PATH) != PROTOCOL_SHA256:
        errors.append("P5 amendment fingerprint mismatch")
    if not config_path.is_file() or sha256_file(config_path) != CONFIG_SHA256:
        errors.append("P5 configuration fingerprint mismatch")
    if not initial_answers.is_file() or sha256_file(initial_answers) != INITIAL_ANSWERS_SHA256:
        errors.append("P5 frozen initial-answer fingerprint mismatch")
    for relative, expected in DATA_FINGERPRINTS.items():
        path = data_dir / relative
        if not path.is_file() or sha256_file(path) != expected:
            errors.append(f"P5 RAMDocs fingerprint mismatch: {relative}")
    try:
        manifest = _load(data_dir / "manifest.json")
        manifest_files = manifest.get("files", {})
        if manifest.get("schema_version") != "far-ramdocs-import-v1":
            errors.append("unsupported RAMDocs manifest schema")
        for relative in ("corpus.jsonl", "splits/dev.jsonl"):
            if (
                not isinstance(manifest_files, dict)
                or manifest_files.get(relative) != (DATA_FINGERPRINTS[relative])
            ):
                errors.append(f"RAMDocs manifest fingerprint mismatch: {relative}")
        dev_rows = read_jsonl(data_dir / "splits/dev.jsonl")
        dev_ids_ordered = [str(row["id"]) for row in dev_rows]
        if (
            len(dev_rows) != 350
            or len(set(dev_ids_ordered)) != 350
            or any(row.get("split") != "dev" for row in dev_rows)
        ):
            errors.append("RAMDocs dev split must contain exactly 350 unique dev samples")
        corpus_ids = {str(row["doc_id"]) for row in read_jsonl(data_dir / "corpus.jsonl")}
        if any(not set(map(str, row["document_ids"])).issubset(corpus_ids) for row in dev_rows):
            errors.append("RAMDocs dev sample references a missing corpus document")
        initial_rows = read_jsonl(initial_answers)
        initial_ids = {str(row["sample_id"]) for row in initial_rows}
        dev_ids = set(dev_ids_ordered)
        if len(initial_rows) != 350 or initial_ids != dev_ids:
            errors.append("frozen initial answers do not cover the exact 350-item dev split")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "far-p5-input-audit-v1",
        "valid": not errors,
        "errors": errors,
        "protocol_sha256": PROTOCOL_SHA256,
        "prereg_tag": PREREG_TAG,
        "prereg_commit": PREREG_COMMIT,
        "config_sha256": CONFIG_SHA256,
        "initial_answers_sha256": INITIAL_ANSWERS_SHA256,
        "data_fingerprints": DATA_FINGERPRINTS,
        "samples": 350,
        "split": "dev",
        "test_accessed": False,
    }


def _runtime_audit(config_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    runtime: dict[str, Any] | None = None
    config = load_config(config_path)
    conflict = config.get("conflict_graph", {})
    try:
        nli_path = resolve_huggingface_snapshot(
            str(conflict["nli_model"]),
            str(conflict["nli_revision"]),
            local_files_only=bool(conflict.get("nli_local_files_only", False)),
        )
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        nli_path = None
        errors.append(f"frozen NLI asset unavailable: {exc}")
    llm_config = config.get("llm", {})
    parsed = urlsplit(str(llm_config.get("base_url", "http://localhost:11434")))
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=1.0):
            pass
    except OSError as exc:
        errors.append(f"Ollama runtime unavailable at {host}:{port}: {exc}")
    else:
        try:
            runtime = _llm_runtime_identity(config)
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(f"Ollama runtime unavailable: {exc}")
    observed_digest = (
        runtime.get("ollama_model", {}).get("digest") if isinstance(runtime, dict) else None
    )
    if runtime is not None and observed_digest != MODEL_DIGEST:
        errors.append("Ollama qwen3.5:9b digest does not match the frozen P5 runtime")
    return {
        "schema_version": "far-p5-runtime-audit-v1",
        "valid": not errors,
        "errors": errors,
        "expected_model_digest": MODEL_DIGEST,
        "runtime": runtime,
        "nli_snapshot": nli_path,
    }


def _run_state(output_dir: Path) -> dict[str, Any]:
    states: dict[str, Any] = {}
    for label, method in METHODS.items():
        run_dir = output_dir / "runs" / method
        try:
            manifest = _load(run_dir / "run_manifest.json")
        except (OSError, ValueError, json.JSONDecodeError):
            manifest = None
        states[label] = {
            "method": method,
            "present": run_dir.is_dir(),
            "complete": bool(
                manifest
                and manifest.get("status") == "complete"
                and manifest.get("partial") is False
                and manifest.get("completed") == 350
                and manifest.get("expected") == 350
            ),
            "completed": manifest.get("completed") if manifest else 0,
            "errors": manifest.get("errors") if manifest else None,
        }
    return states


def status(
    data_dir: Path,
    initial_answers: Path,
    config_path: Path,
    output_dir: Path,
    *,
    check_runtime: bool = True,
) -> dict[str, Any]:
    inputs = _input_audit(data_dir, initial_answers, config_path)
    source = _source_revision()
    source_ready = bool(
        source.get("git_commit")
        and source.get("git_dirty") is False
        and _git_ancestor(str(source["git_commit"]))
    )
    runtime = _runtime_audit(config_path) if check_runtime else None
    runs = _run_state(output_dir)
    return {
        "schema_version": "far-p5-status-v1",
        "valid_inputs": inputs["valid"],
        "source_ready": source_ready,
        "source_revision": source,
        "prereg_is_ancestor": bool(source.get("git_commit"))
        and _git_ancestor(str(source["git_commit"])),
        "runtime_ready": runtime.get("valid") if runtime else None,
        "ready_to_run": bool(
            inputs["valid"] and source_ready and runtime and runtime.get("valid") is True
        ),
        "ready_to_finalize": inputs["valid"] and all(item["complete"] for item in runs.values()),
        "inputs": inputs,
        "runtime": runtime,
        "runs": runs,
        "test_accessed": False,
        "publication_gold": False,
    }


def _validate_runs(
    data_dir: Path,
    initial_answers: Path,
    config_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    inputs = _input_audit(data_dir, initial_answers, config_path)
    if inputs["valid"] is not True:
        raise ValueError(f"P5 inputs are invalid: {inputs['errors']}")
    expected_ids = {str(row["id"]) for row in read_jsonl(data_dir / "splits/dev.jsonl")}
    common: dict[str, Any] | None = None
    artifacts: dict[str, Any] = {}
    for label, method in METHODS.items():
        run_dir = output_dir / "runs" / method
        manifest = _load(run_dir / "run_manifest.json")
        identity = _load(run_dir / "run_identity.json")
        expected_files = {
            "checkpoint.jsonl",
            "predictions.jsonl",
            "run_identity.json",
            "run_manifest.json",
        }
        actual_files = {path.name for path in run_dir.iterdir() if path.is_file()}
        if actual_files != expected_files:
            raise ValueError(f"{method}: run file set mismatch")
        if any(
            (
                manifest.get("schema_version") != "far-run-manifest-v1",
                manifest.get("method") != method,
                manifest.get("status") != "complete",
                manifest.get("partial") is not False,
                manifest.get("completed") != 350,
                manifest.get("expected") != 350,
                manifest.get("errors") != 0,
                manifest.get("split") != "dev",
                manifest.get("gold_loaded_by_runner") is not False,
            )
        ):
            raise ValueError(f"{method}: formal run manifest is incomplete or unsafe")
        predictions = read_jsonl(run_dir / "predictions.jsonl")
        prediction_ids = [str(row["sample_id"]) for row in predictions]
        if len(predictions) != 350 or len(set(prediction_ids)) != 350:
            raise ValueError(f"{method}: predictions are not 350 unique samples")
        if set(prediction_ids) != expected_ids:
            raise ValueError(f"{method}: prediction sample IDs differ from RAMDocs dev")
        if sha256_file(run_dir / "checkpoint.jsonl") != sha256_file(run_dir / "predictions.jsonl"):
            raise ValueError(f"{method}: checkpoint and predictions differ")
        if manifest.get("predictions_sha256") != sha256_file(run_dir / "predictions.jsonl"):
            raise ValueError(f"{method}: run manifest prediction fingerprint mismatch")
        expected_identity = {
            "schema_version": "far-ramdocs-run-signature-v1",
            "method": method,
            "split": "dev",
            "limit": None,
            "config_sha256": CONFIG_SHA256,
            "benchmark_manifest_sha256": DATA_FINGERPRINTS["manifest.json"],
            "benchmark_input_sha256": DATA_FINGERPRINTS["splits/dev.jsonl"],
            "corpus_sha256": DATA_FINGERPRINTS["corpus.jsonl"],
            "initial_answers_sha256": INITIAL_ANSWERS_SHA256,
        }
        for key, value in expected_identity.items():
            if identity.get(key) != value:
                raise ValueError(f"{method}: run identity mismatch: {key}")
        source = identity.get("source_revision", {})
        commit = source.get("git_commit") if isinstance(source, dict) else None
        if not commit or source.get("git_dirty") is not False or not _git_ancestor(str(commit)):
            raise ValueError(f"{method}: source is dirty, missing, or predates P5 preregistration")
        digest = identity.get("llm_runtime", {}).get("ollama_model", {}).get("digest")
        if digest != MODEL_DIGEST:
            raise ValueError(f"{method}: frozen Ollama model digest mismatch")
        shared = {
            "source_commit": commit,
            "implementation_sha256": identity.get("implementation_sha256"),
            "llm_runtime": identity.get("llm_runtime"),
            "llm": identity.get("llm"),
        }
        if common is None:
            common = shared
        elif shared != common:
            raise ValueError("P5 runs do not share source, implementation, and LLM runtime")
        if manifest.get("run_signature") != identity.get("run_signature"):
            raise ValueError(f"{method}: run signature mismatch")
        artifacts[label] = {
            "method": method,
            "run_identity_sha256": sha256_file(run_dir / "run_identity.json"),
            "run_manifest_sha256": sha256_file(run_dir / "run_manifest.json"),
            "predictions_sha256": sha256_file(run_dir / "predictions.jsonl"),
        }
    if common is None:
        raise ValueError("P5 has no formal runs")
    return {"common": common, "runs": artifacts}


def _equivalence_verdict(comparison: dict[str, Any]) -> str:
    lower_bound, upper_bound = EQUIVALENCE_BOUNDS
    lower = float(comparison["lower"])
    upper = float(comparison["upper"])
    if lower >= lower_bound and upper <= upper_bound:
        return "equivalent"
    if upper < lower_bound or lower > upper_bound:
        return "not_equivalent"
    return "uncertain"


def _compute_result(
    data_dir: Path,
    initial_answers: Path,
    config_path: Path,
    output_dir: Path,
    evaluation_root: Path,
) -> dict[str, Any]:
    run_audit = _validate_runs(data_dir, initial_answers, config_path, output_dir)
    evaluations: dict[str, Any] = {}
    score_rows: dict[str, list[dict[str, Any]]] = {}
    for label, method in METHODS.items():
        evaluation_dir = evaluation_root / method
        report = evaluate_ramdocs(
            data_dir / "splits/dev.jsonl",
            output_dir / "runs" / method / "predictions.jsonl",
            data_dir / "corpus.jsonl",
            evaluation_dir,
            split="dev",
            allow_partial=False,
        )
        evaluations[label] = {
            "method": method,
            "metrics": report["metrics"],
            "report_sha256": sha256_file(evaluation_dir / "report.json"),
            "scores_sha256": sha256_file(evaluation_dir / "scores.jsonl"),
        }
        score_rows[label] = read_jsonl(evaluation_dir / "scores.jsonl")
    hypotheses: dict[str, Any] = {}
    for hypothesis, ablation in HYPOTHESES.items():
        comparison = paired_sample_cluster_bootstrap_comparison(
            score_rows[ablation],
            score_rows["full"],
            "ramdocs_exact_match",
            resamples=BOOTSTRAP_RESAMPLES,
            confidence=BOOTSTRAP_CONFIDENCE,
            seed=BOOTSTRAP_SEED,
        )
        hypotheses[hypothesis] = {
            "contrast": f"full - {ablation}",
            "equivalence_bounds": list(EQUIVALENCE_BOUNDS),
            "comparison": comparison,
            "verdict": _equivalence_verdict(comparison),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": PROTOCOL_SHA256,
        "prereg_tag": PREREG_TAG,
        "prereg_commit": PREREG_COMMIT,
        "registered_enhancement": True,
        "split": "dev",
        "samples": 350,
        "methods": list(METHODS),
        "model_digest": MODEL_DIGEST,
        "source_commit": run_audit["common"]["source_commit"],
        "implementation_sha256": run_audit["common"]["implementation_sha256"],
        "config_sha256": CONFIG_SHA256,
        "initial_answers_sha256": INITIAL_ANSWERS_SHA256,
        "data_fingerprints": DATA_FINGERPRINTS,
        "run_artifacts": run_audit["runs"],
        "evaluations": evaluations,
        "hypotheses": hypotheses,
        "model_calls_during_finalize": 0,
        "test_accessed": False,
        "publication_gold": False,
        "human_iaa": False,
    }


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# P5 registered RAMDocs ablations",
        "",
        "> Registered enhancement on 350 RAMDocs development items; upstream-labelled, not",
        "> publication-grade human gold, human IAA, held-out, or test evidence.",
        "",
        "| Hypothesis | Contrast | Full EM | Ablation EM | Difference | 90% CI | Verdict |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for hypothesis in ("H3", "H5"):
        item = result["hypotheses"][hypothesis]
        ablation = HYPOTHESES[hypothesis]
        comparison = item["comparison"]
        full_em = result["evaluations"]["full"]["metrics"]["ramdocs_exact_match"]
        ablation_em = result["evaluations"][ablation]["metrics"]["ramdocs_exact_match"]
        lines.append(
            f"| {hypothesis} | `{item['contrast']}` | {full_em:.4f} | {ablation_em:.4f} | "
            f"{comparison['candidate_minus_baseline']:+.4f} | "
            f"[{comparison['lower']:+.4f}, {comparison['upper']:+.4f}] | "
            f"`{item['verdict']}` |"
        )
    lines.extend(
        [
            "",
            "Equivalence requires the complete 90% sample-cluster bootstrap interval to lie",
            "inside `[-0.02, +0.02]`. Crossing either bound is `uncertain`; an interval wholly",
            "outside the bounds is `not_equivalent`. Finalization made zero model calls.",
            "",
            f"Source commit: `{result['source_commit']}`. "
            f"Model digest: `{result['model_digest']}`.",
            "",
        ]
    )
    return "\n".join(lines)


def finalize(
    data_dir: Path,
    initial_answers: Path,
    config_path: Path,
    output_dir: Path,
    report_json: Path,
    report_markdown: Path,
) -> dict[str, Any]:
    evaluation_root = output_dir / "evaluations"
    result = _compute_result(data_dir, initial_answers, config_path, output_dir, evaluation_root)
    write_json(report_json, result)
    report_markdown.parent.mkdir(parents=True, exist_ok=True)
    report_markdown.write_text(_markdown(result), encoding="utf-8")
    return result


def verify(
    data_dir: Path,
    initial_answers: Path,
    config_path: Path,
    output_dir: Path,
    report_json: Path,
    report_markdown: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        observed = _load(report_json)
        with tempfile.TemporaryDirectory(prefix="far-p5-verify-") as temporary:
            evaluation_root = Path(temporary) / "evaluations"
            expected = _compute_result(
                data_dir, initial_answers, config_path, output_dir, evaluation_root
            )
            if observed != expected:
                errors.append("P5 JSON report differs from independent recomputation")
            for method in METHODS.values():
                for name in ("report.json", "scores.jsonl"):
                    tracked = output_dir / "evaluations" / method / name
                    recomputed = evaluation_root / method / name
                    if not tracked.is_file() or tracked.read_bytes() != recomputed.read_bytes():
                        errors.append(f"P5 evaluation differs from recomputation: {method}/{name}")
        if not report_markdown.is_file() or report_markdown.read_text(
            encoding="utf-8"
        ) != _markdown(expected):
            errors.append("P5 Markdown report differs from deterministic rendering")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
        expected = {}
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "valid": not errors,
        "errors": errors,
        "samples": expected.get("samples"),
        "h3_verdict": expected.get("hypotheses", {}).get("H3", {}).get("verdict"),
        "h5_verdict": expected.get("hypotheses", {}).get("H5", {}).get("verdict"),
        "registered_enhancement": True,
        "model_calls": 0,
        "test_accessed": False,
        "publication_gold": False,
    }


def run_all(
    data_dir: Path,
    initial_answers: Path,
    config_path: Path,
    output_dir: Path,
    report_json: Path,
    report_markdown: Path,
) -> dict[str, Any]:
    audit = status(data_dir, initial_answers, config_path, output_dir, check_runtime=True)
    if audit["ready_to_run"] is not True:
        raise ValueError(f"P5 preflight is not ready: {audit}")
    try:
        ignored = (
            subprocess.run(
                ["git", "check-ignore", "-q", str(output_dir)],
                cwd=ROOT,
                check=False,
            ).returncode
            == 0
        )
    except OSError:
        ignored = False
    if not ignored:
        raise ValueError("P5 output directory must be Git-ignored to preserve clean run identities")
    for method in METHODS.values():
        run_method(
            config_path,
            data_dir,
            initial_answers,
            output_dir / "runs" / method,
            method=method,
            split="dev",
            limit=None,
            allow_test=False,
        )
    return finalize(
        data_dir, initial_answers, config_path, output_dir, report_json, report_markdown
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "run-all", "finalize", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument(
            "--data-dir", type=Path, default=benchmark_data_dir() / "external/ramdocs_v1"
        )
        subparser.add_argument(
            "--initial-answers",
            type=Path,
            default=ROOT / "diagnostics/ramdocs_v2/round1/initial_answers/predictions.jsonl",
        )
        subparser.add_argument(
            "--config", type=Path, default=experiment_config_dir() / "ramdocs_qwen.yaml"
        )
        subparser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/p5_ramdocs_v1")
        subparser.add_argument(
            "--report-json", type=Path, default=ROOT / "reports/p5_ramdocs_ablations.json"
        )
        subparser.add_argument(
            "--report-markdown", type=Path, default=ROOT / "reports/p5_ramdocs_ablations.md"
        )
    status_parser = subparsers.choices["status"]
    status_parser.add_argument("--skip-runtime", action="store_true")
    args = parser.parse_args()
    if args.command == "status":
        result = status(
            args.data_dir,
            args.initial_answers,
            args.config,
            args.output_dir,
            check_runtime=not args.skip_runtime,
        )
    elif args.command == "run-all":
        result = run_all(
            args.data_dir,
            args.initial_answers,
            args.config,
            args.output_dir,
            args.report_json,
            args.report_markdown,
        )
    elif args.command == "finalize":
        result = finalize(
            args.data_dir,
            args.initial_answers,
            args.config,
            args.output_dir,
            args.report_json,
            args.report_markdown,
        )
    else:
        result = verify(
            args.data_dir,
            args.initial_answers,
            args.config,
            args.output_dir,
            args.report_json,
            args.report_markdown,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "verify" and result["valid"] is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
