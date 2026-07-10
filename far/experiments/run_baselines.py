"""Run all declared baselines with separate resumable run identities."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from far.baselines import (
    CounterRefineStyleBaseline,
    CRAGStyleBaseline,
    MultiQueryRAG,
    ReflectiveRAG,
    SelfRAGStyleBaseline,
    VanillaRAG,
)
from far.experiments.runner import (
    CheckpointWriter,
    build_generator,
    build_retriever,
    build_run_identity,
    generator_sample_scope,
    load_config,
    load_run_inputs,
    select_samples,
)
from far.paths import benchmark_data_dir, experiment_config_dir

BASELINE_NAMES = (
    "vanilla_rag",
    "multi_query_rag",
    "reflective_rag",
    "crag_style_reproduction",
    "self_rag_style_reproduction",
    "counterrefine_style_reproduction",
)


def _build(name: str, retriever: Any, generator: Any, top_k: int) -> Any:
    classes = {
        "vanilla_rag": VanillaRAG,
        "multi_query_rag": MultiQueryRAG,
        "reflective_rag": ReflectiveRAG,
        "crag_style_reproduction": CRAGStyleBaseline,
        "self_rag_style_reproduction": SelfRAGStyleBaseline,
        "counterrefine_style_reproduction": CounterRefineStyleBaseline,
    }
    return classes[name](retriever, generator, top_k)


def run(
    config_path: Path,
    data_dir: Path,
    output_root: Path,
    *,
    methods: tuple[str, ...] = BASELINE_NAMES,
    split: str | None = None,
    limit: int | None = None,
    allow_test: bool = False,
) -> list[dict[str, Any]]:
    config = load_config(config_path)
    selected_split = split or str(config.get("run", {}).get("split", "dev"))
    samples, documents = load_run_inputs(data_dir, selected_split)
    selected = select_samples(
        samples,
        selected_split,
        limit=limit,
        allow_test=allow_test,
    )
    generator = build_generator(config)
    manifests = []
    for method in methods:
        if method not in BASELINE_NAMES:
            raise ValueError(f"unknown baseline: {method}")
        retriever = build_retriever(config, documents)
        baseline = _build(
            method,
            retriever,
            generator,
            int(config.get("run", {}).get("top_k_per_query", 5)),
        )
        identity = build_run_identity(
            config_path,
            config,
            data_dir,
            method,
            split=selected_split,
            limit=limit,
        )
        writer = CheckpointWriter(output_root / method, identity)
        for sample in selected:
            if sample["id"] in writer.completed_ids:
                continue
            started = time.perf_counter()
            with generator_sample_scope(generator):
                prediction = baseline.run(
                    sample["id"], sample["question"], sample["initial_answer"]
                )
            row = prediction.to_dict()
            row["metadata"] = {
                **row["metadata"],
                "elapsed_seconds": time.perf_counter() - started,
            }
            writer.append(row)
        manifests.append(
            writer.finalize(
                {sample["id"] for sample in selected},
                partial=limit is not None,
            )
        )
    return manifests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=experiment_config_dir() / "offline_smoke.yaml",
    )
    parser.add_argument("--data-dir", type=Path, default=benchmark_data_dir())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--method", choices=BASELINE_NAMES, action="append")
    parser.add_argument("--split", choices=("train", "dev", "test"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--allow-test", action="store_true")
    args = parser.parse_args()
    manifests = run(
        args.config,
        args.data_dir,
        args.output_dir,
        methods=tuple(args.method or BASELINE_NAMES),
        split=args.split,
        limit=args.limit,
        allow_test=args.allow_test,
    )
    for manifest in manifests:
        print(f"{manifest['method']}: {manifest['completed']} predictions ({manifest['status']})")


if __name__ == "__main__":
    main()
