from __future__ import annotations

import json
from pathlib import Path

from far.bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.experiments.p5_ablations import (
    CONFIG_SHA256,
    DATA_FINGERPRINTS,
    INITIAL_ANSWERS_SHA256,
    METHODS,
    MODEL_DIGEST,
    PREREG_COMMIT,
    finalize,
    status,
    verify,
)
from far.paths import benchmark_data_dir, experiment_config_dir, repository_root

ROOT = repository_root()
DATA_DIR = benchmark_data_dir() / "external/ramdocs_v1"
CONFIG = experiment_config_dir() / "ramdocs_qwen.yaml"
INITIAL_ANSWERS = ROOT / "diagnostics/ramdocs_v2/round1/initial_answers/predictions.jsonl"


def _formal_runs(output_dir: Path) -> None:
    tasks = {str(row["id"]): row for row in read_jsonl(DATA_DIR / "splits/dev.jsonl")}
    sample_ids = sorted(tasks)
    for label, method in METHODS.items():
        rows = []
        for index, sample_id in enumerate(sample_ids):
            task = tasks[sample_id]
            if label == "minus_typed_revision_aggressive" and index < 25:
                answer = "p5 synthetic incorrect answer"
            else:
                answer = "; ".join(map(str, task["gold_answers"]))
            rows.append({"sample_id": sample_id, "method": method, "answer": answer})
        run_dir = output_dir / "runs" / method
        predictions = run_dir / "predictions.jsonl"
        checkpoint = run_dir / "checkpoint.jsonl"
        write_jsonl(predictions, rows)
        checkpoint.write_bytes(predictions.read_bytes())
        signature = f"test-signature-{method}"
        write_json(
            run_dir / "run_identity.json",
            {
                "schema_version": "far-ramdocs-run-signature-v1",
                "method": method,
                "split": "dev",
                "limit": None,
                "config_sha256": CONFIG_SHA256,
                "benchmark_manifest_sha256": DATA_FINGERPRINTS["manifest.json"],
                "benchmark_input_sha256": DATA_FINGERPRINTS["splits/dev.jsonl"],
                "corpus_sha256": DATA_FINGERPRINTS["corpus.jsonl"],
                "initial_answers_sha256": INITIAL_ANSWERS_SHA256,
                "implementation_sha256": "test-p5-implementation",
                "source_revision": {"git_commit": PREREG_COMMIT, "git_dirty": False},
                "llm": {"provider": "ollama", "model": "qwen3.5:9b"},
                "llm_runtime": {
                    "provider": "ollama",
                    "model": "qwen3.5:9b",
                    "ollama_model": {"digest": MODEL_DIGEST},
                },
                "run_signature": signature,
            },
        )
        write_json(
            run_dir / "run_manifest.json",
            {
                "schema_version": "far-run-manifest-v1",
                "method": method,
                "split": "dev",
                "status": "complete",
                "partial": False,
                "completed": 350,
                "expected": 350,
                "errors": 0,
                "gold_loaded_by_runner": False,
                "predictions_sha256": sha256_file(predictions),
                "run_signature": signature,
            },
        )


def test_p5_status_freezes_inputs_without_runtime_probe(tmp_path: Path) -> None:
    audit = status(DATA_DIR, INITIAL_ANSWERS, CONFIG, tmp_path, check_runtime=False)

    assert audit["valid_inputs"] is True
    assert audit["runtime_ready"] is None
    assert audit["ready_to_finalize"] is False
    assert audit["test_accessed"] is False


def test_p5_finalize_and_independent_verifier(tmp_path: Path) -> None:
    output = tmp_path / "p5"
    report_json = tmp_path / "p5.json"
    report_markdown = tmp_path / "p5.md"
    _formal_runs(output)

    result = finalize(
        DATA_DIR,
        INITIAL_ANSWERS,
        CONFIG,
        output,
        report_json,
        report_markdown,
    )
    audit = verify(
        DATA_DIR,
        INITIAL_ANSWERS,
        CONFIG,
        output,
        report_json,
        report_markdown,
    )

    assert result["samples"] == 350
    assert result["hypotheses"]["H3"]["verdict"] == "not_equivalent"
    assert result["hypotheses"]["H5"]["verdict"] == "equivalent"
    assert result["hypotheses"]["H3"]["comparison"]["candidate_minus_baseline"] == 25 / 350
    assert result["hypotheses"]["H3"]["comparison"]["confidence"] == 0.90
    assert all(evaluation["report_sha256"] for evaluation in result["evaluations"].values())
    assert all(
        json.loads(
            (output / "evaluations" / evaluation["method"] / "report.json").read_text(
                encoding="utf-8"
            )
        )["provenance"]["tasks_sha256"]
        == DATA_FINGERPRINTS["splits/dev.jsonl"]
        for evaluation in result["evaluations"].values()
    )
    assert audit == {
        "schema_version": "far-p5-ramdocs-ablations-audit-v1",
        "valid": True,
        "errors": [],
        "samples": 350,
        "h3_verdict": "not_equivalent",
        "h5_verdict": "equivalent",
        "registered_enhancement": True,
        "model_calls": 0,
        "test_accessed": False,
        "publication_gold": False,
    }

    tampered = json.loads(report_json.read_text(encoding="utf-8"))
    tampered["hypotheses"]["H5"]["verdict"] = "uncertain"
    write_json(report_json, tampered)
    assert (
        verify(
            DATA_DIR,
            INITIAL_ANSWERS,
            CONFIG,
            output,
            report_json,
            report_markdown,
        )["valid"]
        is False
    )
