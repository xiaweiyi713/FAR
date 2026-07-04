"""Run one independent cross-family LLM juror over the frozen blind packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.build.auto_annotate import (
    _extract_json_object,
    _fallback_prediction,
    _normalise_prediction,
)
from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from bench.schema import VALID_REVISION_ACTIONS
from experiments.protocol_2plus4 import (
    PROTOCOL_ACTIVE_SHA256,
    PROTOCOL_ORIGINAL_SHA256,
    SYSTEM_MODEL_FAMILIES,
    verify_active_protocol,
)
from experiments.runner import build_generator, load_config

JURY_TYPES = ("temporal", "entity", "numerical", "causal", "source_reliability")


def _prompt(row: dict[str, Any]) -> str:
    return (
        "Act as one independent juror for a preregistered evidence-conflict benchmark. "
        "Use only the supplied question, answer, claims, and role-masked evidence; do not "
        "use memorized world knowledge. Decide independently and return JSON only. "
        "The construction label, other jurors, and system predictions are hidden.\n\n"
        f"Positive conflict_type values: {list(JURY_TYPES)}. If no evidence conflict exists, "
        "set conflict_present=false and conflict_type=no_conflict.\n"
        f"revision_action values: {sorted(VALID_REVISION_ACTIONS)}.\n"
        "JSON schema: {"
        '"conflict_present": boolean, "conflict_type": string, '
        '"revision_action": string, "revised_answer_acceptable": boolean, '
        '"suggested_revised_answer": string, "rationale": string, "confidence": number}.\n\n'
        f"Question:\n{row['question']}\n\n"
        f"Initial answer:\n{row['initial_answer']}\n\n"
        f"Claims:\n{json.dumps(row['claims'], ensure_ascii=False)}\n\n"
        "Evidence snippets, shuffled and role-masked:\n"
        f"{json.dumps(row['evidence'], ensure_ascii=False)}"
    )


PROMPT_SHA256 = hashlib.sha256(_prompt({
    "question": "{question}",
    "initial_answer": "{initial_answer}",
    "claims": "{claims}",
    "evidence": "{evidence}",
}).encode("utf-8")).hexdigest()


def _is_fallback(row: dict[str, Any]) -> bool:
    return str(row.get("jury_annotation", {}).get("rationale", "")).startswith(
        "Automatic fallback;"
    )


def annotate_juror(
    packet_dir: Path,
    config_path: Path,
    output_dir: Path,
    *,
    juror_id: str,
    model_family: str,
    limit: int | None = None,
    overwrite: bool = False,
    resume: bool = False,
    retry_fallbacks: bool = False,
) -> dict[str, Any]:
    verify_active_protocol()
    family = model_family.strip().lower()
    if not family or family in SYSTEM_MODEL_FAMILIES:
        raise ValueError("juror family must be non-empty and disjoint from system families")
    if overwrite and resume:
        raise ValueError("overwrite and resume cannot both be true")
    if retry_fallbacks and not resume:
        raise ValueError("retry_fallbacks requires resume")
    packet_manifest_path = packet_dir / "packet_manifest.json"
    packet_manifest = json.loads(packet_manifest_path.read_text(encoding="utf-8"))
    source_rows = read_jsonl(packet_dir / str(packet_manifest["adjudication_file"]))
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        source_rows = source_rows[:limit]
    filename = f"jury_annotations_{juror_id}.jsonl"
    output_path = output_dir / filename
    if output_dir.exists() and overwrite:
        manifest_path = output_dir / "jury_annotation_manifest.json"
        if not manifest_path.is_file():
            raise ValueError("refusing to overwrite a directory without a jury manifest")
        shutil.rmtree(output_dir)
    elif output_dir.exists() and any(output_dir.iterdir()) and not resume:
        raise FileExistsError(f"{output_dir} exists; pass --overwrite or --resume")
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_ids = {str(row["sample_id"]) for row in source_rows}
    existing: list[dict[str, Any]] = []
    if resume and output_path.exists():
        seen: set[str] = set()
        for row in read_jsonl(output_path):
            sample_id = str(row.get("sample_id", ""))
            if sample_id in seen or sample_id not in selected_ids:
                raise ValueError("jury resume file has duplicate or unexpected samples")
            if row.get("juror_id") != juror_id or row.get("model_family") != family:
                raise ValueError("jury resume identity mismatch")
            seen.add(sample_id)
            if not (retry_fallbacks and _is_fallback(row)):
                existing.append(row)
        write_jsonl(output_path, existing)
    completed_ids = {str(row["sample_id"]) for row in existing}
    generator = build_generator(load_config(config_path))
    if generator is None:
        raise RuntimeError("jury annotation requires an enabled LLM generator")
    with output_path.open("a" if output_path.exists() else "w", encoding="utf-8") as handle:
        for source in source_rows:
            sample_id = str(source["sample_id"])
            if sample_id in completed_ids:
                continue
            try:
                raw = _extract_json_object(
                    generator.complete(
                        _prompt(source),
                        system_prompt=(
                            "You are an independent conservative benchmark juror. "
                            "Use supplied evidence only and emit schema-valid JSON."
                        ),
                        temperature=0.0,
                        max_tokens=900,
                        response_format="json",
                    )
                )
                annotation = _normalise_prediction(raw, sample_id)
                if annotation["conflict_type"] not in {*JURY_TYPES, "no_conflict"}:
                    raise ValueError(f"{sample_id}: conflict type is outside the jury label space")
            except Exception as exc:
                annotation = _fallback_prediction(exc)
            annotation["needs_human_review"] = False
            output_row = {
                "schema_version": "far-jury-annotation-v1",
                "sample_id": sample_id,
                "juror_id": juror_id,
                "model_family": family,
                "jury_annotation": annotation,
                "publication_gold": False,
            }
            handle.write(json.dumps(output_row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()

    rows = read_jsonl(output_path)
    fallbacks = sum(_is_fallback(row) for row in rows)
    config = load_config(config_path)
    manifest = {
        "schema_version": "far-jury-annotation-manifest-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "juror_id": juror_id,
        "model_family": family,
        "model": str(config.get("llm", {}).get("model", "")),
        "config_sha256": sha256_file(config_path),
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "protocol_original_fingerprint": PROTOCOL_ORIGINAL_SHA256,
        "prompt_sha256": PROMPT_SHA256,
        "source_packet_sha256": sha256_file(packet_manifest_path),
        "samples": len(rows),
        "expected_samples": len(source_rows),
        "complete": len(rows) == len(source_rows),
        "fallbacks": fallbacks,
        "fallback_rate": fallbacks / len(rows) if rows else 1.0,
        "annotation_file": filename,
        "annotation_sha256": sha256_file(output_path),
        "publication_gold": False,
        "human_annotator": False,
    }
    write_json(output_dir / "jury_annotation_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--juror-id", required=True)
    parser.add_argument("--model-family", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-fallbacks", action="store_true")
    args = parser.parse_args()
    result = annotate_juror(
        args.packet_dir,
        args.config,
        args.output_dir,
        juror_id=args.juror_id,
        model_family=args.model_family,
        limit=args.limit,
        overwrite=args.overwrite,
        resume=args.resume,
        retry_fallbacks=args.retry_fallbacks,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
