"""Run RAMDocs initial-answer generation and closed-corpus FAR comparisons."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from baselines import (
    CounterRefineStyleBaseline,
    CRAGStyleBaseline,
    MultiQueryRAG,
    ReflectiveRAG,
    SelfRAGStyleBaseline,
    VanillaRAG,
)
from bench.build.common import read_jsonl, sha256_file, write_json
from experiments.ablations import build_ablation
from experiments.run_far import _detector, _primary_trace
from experiments.runner import (
    ROOT,
    CheckpointWriter,
    _implementation_sha256,
    _llm_runtime_identity,
    _source_revision,
    build_generator,
    generator_sample_scope,
    load_config,
)
from far.adapters import InMemoryRetriever
from far.models import EvidenceDocument

BASELINE_CLASSES = {
    "vanilla_rag": VanillaRAG,
    "multi_query_rag": MultiQueryRAG,
    "reflective_rag": ReflectiveRAG,
    "crag_style_reproduction": CRAGStyleBaseline,
    "self_rag_style_reproduction": SelfRAGStyleBaseline,
    "counterrefine_style_reproduction": CounterRefineStyleBaseline,
}
METHODS = (
    "far",
    "far_minus_typed_conflict",
    "far_minus_refutation_query",
    "far_minus_boundary_query",
    "far_minus_typed_revision",
    *BASELINE_CLASSES,
)


def _documents(data_dir: Path) -> dict[str, list[EvidenceDocument]]:
    grouped: dict[str, list[EvidenceDocument]] = {}
    for row in read_jsonl(data_dir / "corpus.jsonl"):
        metadata = dict(row.get("metadata", {}))
        sample_id = str(metadata["sample_id"])
        grouped.setdefault(sample_id, []).append(
            EvidenceDocument(
                evidence_id=str(row["doc_id"]),
                text=str(row["content"]),
                title=str(row["title"]),
                source=str(row["source"]),
                date=None,
                url=None,
                metadata={},
            )
        )
    return grouped


def _operational_rows(data_dir: Path, split: str) -> list[dict[str, Any]]:
    if split == "dev":
        return [
            {"id": row["id"], "question": row["question"], "split": "dev"}
            for row in read_jsonl(data_dir / "splits" / "dev.jsonl")
        ]
    rows = read_jsonl(data_dir / "splits" / "test_inputs.jsonl")
    if any(set(row) != {"id", "question", "split"} for row in rows):
        raise ValueError("RAMDocs test inputs expose hidden labels")
    return rows


def _select(rows: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    selected = sorted(rows, key=lambda row: str(row["id"]))
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        selected = selected[:limit]
    return selected


def _identity(
    config_path: Path,
    config: dict[str, Any],
    data_dir: Path,
    method: str,
    split: str,
    limit: int | None,
    *,
    initial_answers_path: Path | None = None,
) -> dict[str, Any]:
    input_path = data_dir / "splits" / ("test_inputs.jsonl" if split == "test" else "dev.jsonl")
    stable: dict[str, Any] = {
        "schema_version": "far-ramdocs-run-signature-v1",
        "method": method,
        "split": split,
        "limit": limit,
        "config_sha256": sha256_file(config_path),
        "benchmark_manifest_sha256": sha256_file(data_dir / "manifest.json"),
        "benchmark_input_sha256": sha256_file(input_path),
        "corpus_sha256": sha256_file(data_dir / "corpus.jsonl"),
        "implementation_sha256": _implementation_sha256(),
        "source_revision": _source_revision(),
        "llm": config.get("llm", {}),
        "llm_runtime": _llm_runtime_identity(config),
        "retrieval": {"backend": "per_sample_closed_lexical", "scope": "one RAMDocs item"},
    }
    if initial_answers_path is not None:
        stable["initial_answers_sha256"] = sha256_file(initial_answers_path)
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    return {**stable, "run_signature": hashlib.sha256(encoded).hexdigest()}


def initialize_answers(
    config_path: Path,
    data_dir: Path,
    output_dir: Path,
    *,
    split: str = "dev",
    limit: int | None = None,
    allow_test: bool = False,
) -> dict[str, Any]:
    if split == "test" and not allow_test:
        raise ValueError("RAMDocs test initialization requires --allow-test one-shot authorization")
    config = load_config(config_path)
    rows = _select(_operational_rows(data_dir, split), limit)
    documents = _documents(data_dir)
    generator = build_generator(config)
    identity = _identity(config_path, config, data_dir, "ramdocs_initial_vanilla", split, limit)
    writer = CheckpointWriter(output_dir, identity)
    for row in rows:
        sample_id = str(row["id"])
        if sample_id in writer.completed_ids:
            continue
        sample_documents = documents[sample_id]
        retriever = InMemoryRetriever(sample_documents)
        baseline = VanillaRAG(retriever, generator, top_k=len(sample_documents))
        started = time.perf_counter()
        with generator_sample_scope(generator):
            prediction = baseline.run(
                sample_id,
                str(row["question"]),
                "" if generator is not None else "No evidence-grounded answer was generated.",
            )
        result = prediction.to_dict()
        result["method"] = "ramdocs_initial_vanilla"
        result["metadata"] = {
            **result.get("metadata", {}),
            "elapsed_seconds": time.perf_counter() - started,
            "closed_corpus_documents": len(sample_documents),
        }
        writer.append(result)
    manifest = writer.finalize({str(row["id"]) for row in rows}, partial=limit is not None)
    manifest.update(
        {
            "study_profile": "ramdocs_external_upstream_labeled",
            "allow_test": allow_test,
            "gold_loaded_by_runner": False,
        }
    )
    write_json(output_dir / "run_manifest.json", manifest)
    return manifest


def _far_prediction(
    method: str,
    question: str,
    initial_answer: str,
    documents: list[EvidenceDocument],
    config: dict[str, Any],
    generator: Any,
) -> dict[str, Any]:
    ablation = "full" if method == "far" else method.removeprefix("far_")
    retriever = InMemoryRetriever(documents)
    pipeline = build_ablation(
        ablation,
        retriever,
        conflict_detector=_detector(config, documents),
        text_generator=generator,
        top_k_per_query=min(len(documents), int(config.get("run", {}).get("top_k_per_query", 5))),
    )
    result = pipeline.run(question, initial_answer)
    primary = _primary_trace(result.revision_trace)
    return {
        "answer": result.revised_answer,
        "evidence_ids": list(
            dict.fromkeys(
                evidence.evidence_id
                for claim_evidence in result.evidence_map.values()
                for evidence in claim_evidence
            )
        ),
        "predicted_conflict_types": list(
            dict.fromkeys(
                conflict.conflict_type.value
                for conflicts in result.conflicts.values()
                for conflict in conflicts
            )
        ),
        "revision_action": primary.action.value,
        "metadata": {
            "primary_revision_trace": primary.to_dict(),
            "claim_graph": result.claim_graph.to_dict(),
            "revision_trace": [item.to_dict() for item in result.revision_trace],
            "retrieval_trace": [item.to_dict() for item in result.retrieval_trace],
        },
    }


def run_method(
    config_path: Path,
    data_dir: Path,
    initial_answers_path: Path,
    output_dir: Path,
    *,
    method: str,
    split: str = "dev",
    limit: int | None = None,
    allow_test: bool = False,
) -> dict[str, Any]:
    if method not in METHODS:
        raise ValueError(f"unknown RAMDocs method: {method}")
    if split == "test" and not allow_test:
        raise ValueError("RAMDocs test run requires --allow-test one-shot authorization")
    config = load_config(config_path)
    rows = _select(_operational_rows(data_dir, split), limit)
    initial_rows = {str(row["sample_id"]): row for row in read_jsonl(initial_answers_path)}
    expected_ids = {str(row["id"]) for row in rows}
    if set(initial_rows) != expected_ids:
        raise ValueError("initial-answer bundle does not exactly match selected RAMDocs inputs")
    documents = _documents(data_dir)
    generator = build_generator(config)
    identity = _identity(
        config_path,
        config,
        data_dir,
        method,
        split,
        limit,
        initial_answers_path=initial_answers_path,
    )
    writer = CheckpointWriter(output_dir, identity)
    for row in rows:
        sample_id = str(row["id"])
        if sample_id in writer.completed_ids:
            continue
        question = str(row["question"])
        initial_answer = str(initial_rows[sample_id]["answer"])
        sample_documents = documents[sample_id]
        started = time.perf_counter()
        with generator_sample_scope(generator):
            if method.startswith("far"):
                prediction = _far_prediction(
                    method, question, initial_answer, sample_documents, config, generator
                )
            else:
                retriever = InMemoryRetriever(sample_documents)
                baseline: Any = BASELINE_CLASSES[method](
                    retriever,
                    generator,
                    min(
                        len(sample_documents),
                        int(config.get("run", {}).get("top_k_per_query", 5)),
                    ),
                )
                prediction = baseline.run(sample_id, question, initial_answer).to_dict()
        metadata = dict(prediction.get("metadata", {}))
        metadata.update(
            {
                "elapsed_seconds": time.perf_counter() - started,
                "closed_corpus_documents": len(sample_documents),
            }
        )
        writer.append(
            {
                **prediction,
                "sample_id": sample_id,
                "method": method,
                "metadata": metadata,
            }
        )
    manifest = writer.finalize(expected_ids, partial=limit is not None)
    manifest.update(
        {
            "study_profile": "ramdocs_external_upstream_labeled",
            "allow_test": allow_test,
            "gold_loaded_by_runner": False,
        }
    )
    write_json(output_dir / "run_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("initialize")
    run_parser = subparsers.add_parser("run")
    for subparser in (init_parser, run_parser):
        subparser.add_argument(
            "--config", type=Path, default=ROOT / "experiments/configs/ramdocs_qwen.yaml"
        )
        subparser.add_argument("--data-dir", type=Path, default=ROOT / "bench/external/ramdocs_v1")
        subparser.add_argument("--output-dir", type=Path, required=True)
        subparser.add_argument("--split", choices=("dev", "test"), default="dev")
        subparser.add_argument("--limit", type=int)
        subparser.add_argument("--allow-test", action="store_true")
    run_parser.add_argument("--initial-answers", type=Path, required=True)
    run_parser.add_argument("--method", choices=METHODS, required=True)
    args = parser.parse_args()
    if args.command == "initialize":
        result = initialize_answers(
            args.config,
            args.data_dir,
            args.output_dir,
            split=args.split,
            limit=args.limit,
            allow_test=args.allow_test,
        )
    else:
        result = run_method(
            args.config,
            args.data_dir,
            args.initial_answers,
            args.output_dir,
            method=args.method,
            split=args.split,
            limit=args.limit,
            allow_test=args.allow_test,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
