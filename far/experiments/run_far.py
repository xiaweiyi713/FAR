"""Run FAR or one named ablation with resumable, fingerprinted checkpoints."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from far.adapters import (
    HeuristicConflictDetector,
    NLIOnlyConflictDetector,
    VeraConflictDetector,
)
from far.experiments.ablations import ABLATION_NAMES, build_ablation
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
from far.models import EvidenceDocument
from far.paths import benchmark_data_dir, experiment_config_dir
from far.revision import RevisionAction, RevisionTrace

_PRIMARY_ACTION_PRIORITY = {
    RevisionAction.PREFER_RELIABLE_SOURCE: 100,
    RevisionAction.REQUALIFY_ENTITY: 90,
    RevisionAction.CORRECT_TEMPORAL: 80,
    RevisionAction.REPLACE_NUMERICAL: 70,
    RevisionAction.DOWNGRADE_CAUSAL: 60,
    RevisionAction.CLARIFY_DEFINITION: 50,
    RevisionAction.RETRACT: 40,
    RevisionAction.QUALIFY_UNCERTAINTY: 30,
    RevisionAction.KEEP: 0,
}


def _detector(
    config: dict[str, Any],
    documents: list[EvidenceDocument],
    *,
    ablation: str = "full",
) -> Any:
    if ablation == "minus_typed_detection_nli":
        return NLIOnlyConflictDetector(config)
    name = config.get("run", {}).get("conflict_detector", "heuristic")
    if name == "heuristic":
        return HeuristicConflictDetector()
    if name == "vera":
        entity_lexicon = tuple(
            dict.fromkeys(
                str(entity)
                for document in documents
                for entity in document.metadata.get("entities", [])
                if str(entity).strip()
            )
        )
        return VeraConflictDetector(config, entity_lexicon=entity_lexicon)
    raise ValueError(f"unsupported conflict detector: {name}")


def _primary_trace(traces: tuple[RevisionTrace, ...]) -> RevisionTrace:
    """Select the strongest sample-level control while retaining the full trace."""

    changed = tuple(trace for trace in traces if trace.changed)
    if not changed:
        return traces[0]
    return max(
        changed,
        key=lambda trace: (
            trace.confidence,
            _PRIMARY_ACTION_PRIORITY[trace.action],
            -len(trace.conflict_types),
        ),
    )


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
    samples, documents = load_run_inputs(data_dir, selected_split)
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
        conflict_detector=_detector(config, documents, ablation=ablation),
        text_generator=generator,
        top_k_per_query=int(config.get("run", {}).get("top_k_per_query", 5)),
    )
    for sample in selected:
        if sample["id"] in writer.completed_ids:
            print(f"{method}: skip completed {sample['id']}", flush=True)
            continue
        print(f"{method}: start {sample['id']}", flush=True)
        started = time.perf_counter()
        with generator_sample_scope(generator):
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
        primary_trace = _primary_trace(result.revision_trace)
        primary_conflicts = tuple(item.value for item in primary_trace.conflict_types)
        action = primary_trace.action.value
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
                    "primary_conflict_types": list(primary_conflicts),
                    "primary_revision_trace": primary_trace.to_dict(),
                    "claim_graph": result.claim_graph.to_dict(),
                    "revision_trace": [item.to_dict() for item in result.revision_trace],
                    "retrieval_trace": [item.to_dict() for item in result.retrieval_trace],
                },
            }
        )
        print(
            f"{method}: completed {sample['id']} in {time.perf_counter() - started:.2f}s",
            flush=True,
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
        default=experiment_config_dir() / "offline_smoke.yaml",
    )
    parser.add_argument("--data-dir", type=Path, default=benchmark_data_dir())
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
