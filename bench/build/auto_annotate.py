"""Generate non-gold LLM preannotations for blind FalsiRAG annotation packets."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from bench.schema import VALID_CONFLICT_TYPES, VALID_REVISION_ACTIONS
from far.protocols import TextGenerator

AUTO_PACKET_VERSION = "falsirag-auto-annotation-v1"


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM response did not contain a JSON object")
    value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("LLM response JSON must be an object")
    return value


def _normalise_prediction(raw: dict[str, Any], sample_id: str) -> dict[str, Any]:
    present = raw.get("conflict_present")
    if not isinstance(present, bool):
        raise ValueError(f"{sample_id}: conflict_present must be boolean")
    conflict_type = str(raw.get("conflict_type", "")).strip()
    if not present:
        conflict_type = "no_conflict"
    elif conflict_type not in VALID_CONFLICT_TYPES:
        raise ValueError(f"{sample_id}: invalid conflict_type {conflict_type!r}")
    action = str(raw.get("revision_action", "")).strip()
    if action not in VALID_REVISION_ACTIONS:
        raise ValueError(f"{sample_id}: invalid revision_action {action!r}")
    acceptable = raw.get("revised_answer_acceptable")
    if not isinstance(acceptable, bool):
        raise ValueError(f"{sample_id}: revised_answer_acceptable must be boolean")
    confidence = raw.get("confidence", 0.5)
    try:
        numeric_confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        numeric_confidence = 0.5
    return {
        "conflict_present": present,
        "conflict_type": conflict_type,
        "revision_action": action,
        "revised_answer_acceptable": acceptable,
        "suggested_revised_answer": str(raw.get("suggested_revised_answer", "")).strip(),
        "rationale": str(raw.get("rationale", "")).strip(),
        "confidence": numeric_confidence,
        "needs_human_review": True,
    }


def _fallback_prediction(error: Exception) -> dict[str, Any]:
    return {
        "conflict_present": True,
        "conflict_type": "counter_evidence",
        "revision_action": "qualify_uncertainty",
        "revised_answer_acceptable": False,
        "suggested_revised_answer": "",
        "rationale": f"Automatic fallback; LLM preannotation failed validation: {error}",
        "confidence": 0.0,
        "needs_human_review": True,
    }


def _prompt(row: dict[str, Any]) -> str:
    return (
        "You are pre-annotating a blind FalsiRAG-Bench item for later human review. "
        "The gold labels are intentionally hidden. Decide whether the initial answer "
        "has an evidence conflict, which conflict type best applies, which revision "
        "action is appropriate, and whether the revised answer would be acceptable. "
        "Return JSON only.\n\n"
        f"Allowed conflict_type values: {sorted(VALID_CONFLICT_TYPES)}. "
        "Use no_conflict only when conflict_present is false.\n"
        f"Allowed revision_action values: {sorted(VALID_REVISION_ACTIONS)}.\n\n"
        "JSON schema: {"
        '"conflict_present": boolean, '
        '"conflict_type": string, '
        '"revision_action": string, '
        '"revised_answer_acceptable": boolean, '
        '"suggested_revised_answer": string, '
        '"rationale": string, '
        '"confidence": number'
        "}.\n\n"
        f"Question:\n{row['question']}\n\n"
        f"Initial answer:\n{row['initial_answer']}\n\n"
        f"Claims:\n{json.dumps(row['claims'], ensure_ascii=False)}\n\n"
        f"Evidence snippets, shuffled and role-masked:\n"
        f"{json.dumps(row['evidence'], ensure_ascii=False)}"
    )


def generate_preannotations(
    packet_dir: Path,
    output_dir: Path,
    *,
    generator: TextGenerator | None,
    preannotator_id: str,
    limit: int | None = None,
    overwrite: bool = False,
    model_name: str = "",
) -> dict[str, Any]:
    manifest_path = packet_dir / "packet_manifest.json"
    packet_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_rows = read_jsonl(packet_dir / packet_manifest["adjudication_file"])
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        source_rows = source_rows[:limit]
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass --overwrite to replace it")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    rows = []
    failures = 0
    for row in source_rows:
        try:
            if generator is None:
                raise RuntimeError("no LLM generator configured")
            raw = _extract_json_object(
                generator.complete(
                    _prompt(row),
                    system_prompt=(
                        "You produce conservative, schema-valid JSON preannotations. "
                        "Do not claim human certainty."
                    ),
                    temperature=0.0,
                    max_tokens=900,
                )
            )
            prediction = _normalise_prediction(raw, str(row["sample_id"]))
        except Exception as exc:
            failures += 1
            prediction = _fallback_prediction(exc)
        rows.append(
            {
                "schema_version": AUTO_PACKET_VERSION,
                "sample_id": row["sample_id"],
                "question": row["question"],
                "initial_answer": row["initial_answer"],
                "claims": row["claims"],
                "evidence": row["evidence"],
                "preannotator_id": preannotator_id,
                "preannotation": prediction,
                "publication_gold": False,
            }
        )

    filename = f"preannotations_{preannotator_id}.jsonl"
    output_path = output_dir / filename
    write_jsonl(output_path, rows)
    result = {
        "schema_version": AUTO_PACKET_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_packet_sha256": sha256_file(manifest_path),
        "source_fingerprints": packet_manifest["source_fingerprints"],
        "samples": len(rows),
        "preannotator_id": preannotator_id,
        "model_name": model_name,
        "preannotation_file": filename,
        "llm_failures": failures,
        "publication_gold": False,
        "can_satisfy_human_annotation_gate": False,
        "required_next_step": (
            "Use these suggestions only as non-gold reviewer aids. Independent human "
            "annotation, adjudication, and Cohen's kappa reporting are still required "
            "for publication claims."
        ),
    }
    write_json(output_dir / "preannotation_manifest.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--preannotator-id", default="llm_preannotator")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    generator: TextGenerator | None = None
    model_name = ""
    if args.config is not None:
        from experiments.runner import build_generator, load_config

        config = load_config(args.config)
        generator = build_generator(config)
        model_name = str(config.get("llm", {}).get("model", ""))
    result = generate_preannotations(
        args.packet_dir,
        args.output_dir,
        generator=generator,
        preannotator_id=args.preannotator_id,
        limit=args.limit,
        overwrite=args.overwrite,
        model_name=model_name,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
