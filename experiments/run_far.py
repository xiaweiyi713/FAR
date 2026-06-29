"""Run FAR or one named ablation with resumable, fingerprinted checkpoints."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from experiments.ablations import ABLATION_NAMES, build_ablation
from experiments.runner import (
    ROOT,
    CheckpointWriter,
    build_generator,
    build_retriever,
    build_run_identity,
    load_benchmark,
    load_config,
    select_samples,
)
from far.adapters import HeuristicConflictDetector, VeraConflictDetector


def _detector(config: dict[str, Any]) -> Any:
    name = config.get("run", {}).get("conflict_detector", "heuristic")
    if name == "heuristic":
        return HeuristicConflictDetector()
    if name == "vera":
        return VeraConflictDetector(config)
    raise ValueError(f"unsupported conflict detector: {name}")


def run(
    config_path: Path,
    data_dir: Path,
    output_dir: Path,
    *,
    ablation: str = "full",
    split: str | None = None,
    limit: int | None = None,
    allow_test: bool = False,
) -> dict[str, Any]:
    config = load_config(config_path)
    selected_split = split or str(config.get("run", {}).get("split", "dev"))
    samples, documents = load_benchmark(data_dir)
    selected = select_samples(
        samples,
        selected_split,
        limit=limit,
        allow_test=allow_test,
    )
    method = "far" if ablation == "full" else f"far_{ablation}"
    identity = build_run_identity(
        config_path,
        config,
        data_dir,
        method,
        split=selected_split,
        limit=limit,
    )
    writer = CheckpointWriter(output_dir, identity)
    retriever = build_retriever(config, documents)
    generator = build_generator(config)
    pipeline = build_ablation(
        ablation,
        retriever,
        conflict_detector=_detector(config),
        text_generator=generator,
        top_k_per_query=int(config.get("run", {}).get("top_k_per_query", 5)),
    )
    for sample in selected:
        if sample["id"] in writer.completed_ids:
            continue
        started = time.perf_counter()
        result = pipeline.run(sample["question"], sample["initial_answer"])
        evidence_ids = tuple(
            dict.fromkeys(
                item.evidence_id
                for claim_evidence in result.evidence_map.values()
                for item in claim_evidence
            )
        )
        predicted_conflicts = tuple(
            dict.fromkeys(
                conflict.conflict_type.value
                for claim_conflicts in result.conflicts.values()
                for conflict in claim_conflicts
            )
        )
        changed = next((trace for trace in result.revision_trace if trace.changed), None)
        action = changed.action.value if changed else result.revision_trace[0].action.value
        writer.append(
            {
                "sample_id": sample["id"],
                "method": method,
                "answer": result.revised_answer,
                "evidence_ids": list(evidence_ids),
                "predicted_conflict_types": list(predicted_conflicts),
                "revision_action": action,
                "metadata": {
                    "elapsed_seconds": time.perf_counter() - started,
                    "claim_graph": result.claim_graph.to_dict(),
                    "revision_trace": [item.to_dict() for item in result.revision_trace],
                    "retrieval_trace": [item.to_dict() for item in result.retrieval_trace],
                },
            }
        )
    return writer.finalize(
        {sample["id"] for sample in selected},
        partial=limit is not None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "experiments/configs/offline_smoke.yaml",
    )
    parser.add_argument("--data-dir", type=Path, default=ROOT / "bench")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ablation", choices=ABLATION_NAMES, default="full")
    parser.add_argument("--split", choices=("train", "dev", "test"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--allow-test", action="store_true")
    args = parser.parse_args()
    manifest = run(
        args.config,
        args.data_dir,
        args.output_dir,
        ablation=args.ablation,
        split=args.split,
        limit=args.limit,
        allow_test=args.allow_test,
    )
    print(f"{manifest['method']}: {manifest['completed']} predictions ({manifest['status']})")


if __name__ == "__main__":
    main()
