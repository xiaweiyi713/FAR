"""Run one independent cross-family LLM juror over the frozen blind packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from far.bench.annotations import PACKET_VERSION
from far.bench.build.auto_annotate import (
    _extract_json_object,
    _fallback_prediction,
    _normalise_prediction,
)
from far.bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.bench.schema import VALID_REVISION_ACTIONS
from far.experiments.phase_b_gate import require_phase_b_authorized
from far.experiments.protocol_2plus4 import (
    PROTOCOL_ACTIVE_SHA256,
    PROTOCOL_ORIGINAL_SHA256,
    SYSTEM_MODEL_FAMILIES,
    verify_active_protocol,
)
from far.experiments.runner import (
    _implementation_sha256,
    _llm_runtime_identity,
    _source_revision,
    build_generator,
    load_config,
)

JURY_TYPES = ("temporal", "entity", "numerical", "causal", "source_reliability")
JUROR_SPECS = {
    "J1": {"family": "deepseek", "provider": "deepseek", "model": "deepseek-chat"},
    "J2": {"family": "glm", "provider": "ollama", "model": "glm4:9b"},
    "J3": {"family": "meta", "provider": "ollama", "model": "llama3.1:8b"},
}
BLIND_SOURCE_FIELDS = {
    "schema_version",
    "sample_id",
    "question",
    "initial_answer",
    "claims",
    "evidence",
    "adjudicator_id",
    "gold_annotation",
}


def _load_blind_packet(
    packet_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    manifest_path = packet_dir / "packet_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != PACKET_VERSION:
        raise ValueError("unsupported blind annotation packet schema")
    filename = str(manifest.get("adjudication_file", ""))
    if not filename or Path(filename).name != filename:
        raise ValueError("blind adjudication filename must be a local basename")
    source_path = packet_dir / filename
    rows = read_jsonl(source_path)
    expected = int(manifest.get("samples", -1))
    sample_ids = [str(row.get("sample_id", "")) for row in rows]
    if (
        len(rows) != expected
        or any(not sample_id for sample_id in sample_ids)
        or len(sample_ids) != len(set(sample_ids))
    ):
        raise ValueError("blind adjudication packet is duplicate or incomplete")
    required_omissions = {
        "category",
        "split",
        "conflict_type",
        "expected_revision",
        "source_metadata",
        "annotation_status",
        "evidence roles",
    }
    if not required_omissions.issubset(set(manifest.get("blind_fields_omitted", []))):
        raise ValueError("blind packet does not declare all required hidden fields")
    for row in rows:
        sample_id = str(row["sample_id"])
        if set(row) != BLIND_SOURCE_FIELDS or row.get("schema_version") != PACKET_VERSION:
            raise ValueError(f"{sample_id}: blind packet exposes unexpected fields")
        if str(row.get("adjudicator_id", "")).strip():
            raise ValueError(f"{sample_id}: blind packet already identifies an adjudicator")
        gold = row.get("gold_annotation")
        if not isinstance(gold, dict) or any(
            (
                gold.get("conflict_present") is not None,
                bool(str(gold.get("conflict_type", "")).strip()),
                bool(str(gold.get("revision_action", "")).strip()),
                gold.get("revised_answer_acceptable") is not None,
                bool(str(gold.get("revised_answer", "")).strip()),
                bool(str(gold.get("rationale", "")).strip()),
            )
        ):
            raise ValueError(f"{sample_id}: blind packet contains a populated gold label")
        if any(set(claim) != {"claim_id", "claim"} for claim in row.get("claims", [])):
            raise ValueError(f"{sample_id}: blind packet claim structure is not role-free")
        if any(
            set(evidence) != {"evidence_id", "title", "source", "date", "text"}
            for evidence in row.get("evidence", [])
        ):
            raise ValueError(f"{sample_id}: blind packet evidence exposes hidden metadata")
    return manifest, rows, sha256_file(source_path)


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


PROMPT_SHA256 = hashlib.sha256(
    _prompt(
        {
            "question": "{question}",
            "initial_answer": "{initial_answer}",
            "claims": "{claims}",
            "evidence": "{evidence}",
        }
    ).encode("utf-8")
).hexdigest()


def _is_fallback(row: dict[str, Any]) -> bool:
    return str(row.get("jury_annotation", {}).get("rationale", "")).startswith(
        "Automatic fallback;"
    )


def _validate_juror_identity(
    juror_id: str,
    family: str,
    llm_config: dict[str, Any],
) -> dict[str, str]:
    spec = JUROR_SPECS.get(juror_id)
    if spec is None:
        raise ValueError("juror_id must be one of the three preregistered jurors")
    actual = {
        "family": family,
        "provider": str(llm_config.get("provider", "")).strip().lower(),
        "model": str(llm_config.get("model", "")).strip(),
    }
    if actual != spec:
        raise ValueError(f"{juror_id} identity differs from the preregistered model: {actual}")
    return spec


def _validate_runtime_identity(
    runtime: dict[str, Any],
    spec: dict[str, str],
) -> None:
    if (
        runtime.get("enabled") is not True
        or runtime.get("provider") != spec["provider"]
        or runtime.get("model") != spec["model"]
    ):
        raise ValueError("jury runtime identity differs from the preregistered model")
    if spec["provider"] == "ollama":
        ollama_model = runtime.get("ollama_model")
        if (
            not isinstance(ollama_model, dict)
            or ollama_model.get("model") != spec["model"]
            or len(str(ollama_model.get("digest", ""))) != 64
        ):
            raise ValueError("local jury runtime lacks an immutable Ollama digest")


def annotate_juror(
    packet_dir: Path,
    config_path: Path,
    output_dir: Path,
    gate_data_dir: Path,
    gate_round1_dir: Path,
    gate_round2_dir: Path,
    gate_config_path: Path,
    *,
    juror_id: str,
    model_family: str,
    limit: int | None = None,
    overwrite: bool = False,
    resume: bool = False,
    retry_fallbacks: bool = False,
) -> dict[str, Any]:
    verify_active_protocol()
    phase_b_gate = require_phase_b_authorized(
        gate_data_dir,
        gate_round1_dir,
        gate_round2_dir,
        gate_config_path,
    )
    family = model_family.strip().lower()
    if not family or family in SYSTEM_MODEL_FAMILIES:
        raise ValueError("juror family must be non-empty and disjoint from system families")
    config = load_config(config_path)
    llm_config = config.get("llm", {})
    if not isinstance(llm_config, dict):
        raise TypeError("jury llm configuration must be a mapping")
    configured_family = str(llm_config.get("model_family", "")).strip().lower()
    if configured_family != family:
        raise ValueError("juror family must match llm.model_family in the frozen config")
    if float(llm_config.get("temperature", -1.0)) != 0.0:
        raise ValueError("jury annotation requires temperature=0")
    spec = _validate_juror_identity(juror_id, family, llm_config)
    if overwrite and resume:
        raise ValueError("overwrite and resume cannot both be true")
    if retry_fallbacks and not resume:
        raise ValueError("retry_fallbacks requires resume")
    packet_manifest_path = packet_dir / "packet_manifest.json"
    _, source_rows, source_adjudication_sha256 = _load_blind_packet(packet_dir)
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

    runtime_identity = _llm_runtime_identity(config)
    _validate_runtime_identity(runtime_identity, spec)
    source_revision = _source_revision()
    if source_revision.get("git_dirty") is not False:
        raise ValueError("jury annotation requires a clean Git revision")
    run_identity = {
        "schema_version": "far-jury-run-identity-v1",
        "juror_id": juror_id,
        "model_family": family,
        "config_sha256": sha256_file(config_path),
        "llm_runtime": runtime_identity,
        "implementation_sha256": _implementation_sha256(),
        "source_revision": source_revision,
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "prompt_sha256": PROMPT_SHA256,
        "source_packet_sha256": sha256_file(packet_manifest_path),
        "source_adjudication_sha256": source_adjudication_sha256,
        "phase_b_gate": phase_b_gate,
    }
    identity_path = output_dir / "run_identity.json"
    if resume:
        if not identity_path.is_file():
            raise ValueError("jury resume requires the original run identity")
        existing_identity = json.loads(identity_path.read_text(encoding="utf-8"))
        if existing_identity != run_identity:
            raise ValueError("jury resume identity differs from the original run")
    else:
        write_json(identity_path, run_identity)

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
    generator = build_generator(config)
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
                if annotation["conflict_present"] and not annotation["suggested_revised_answer"]:
                    raise ValueError(f"{sample_id}: conflict-positive jury row needs a revision")
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
    manifest = {
        "schema_version": "far-jury-annotation-manifest-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "juror_id": juror_id,
        "model_family": family,
        "model": str(config.get("llm", {}).get("model", "")),
        "llm_runtime": runtime_identity,
        "config_sha256": sha256_file(config_path),
        "run_identity_sha256": sha256_file(identity_path),
        "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
        "protocol_original_fingerprint": PROTOCOL_ORIGINAL_SHA256,
        "prompt_sha256": PROMPT_SHA256,
        "source_packet_sha256": sha256_file(packet_manifest_path),
        "source_adjudication_sha256": source_adjudication_sha256,
        "phase_b_gate": phase_b_gate,
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


def verify_juror(
    packet_dir: Path,
    config_path: Path,
    output_dir: Path,
    gate_data_dir: Path,
    gate_round1_dir: Path,
    gate_round2_dir: Path,
    gate_config_path: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        verify_active_protocol()
        manifest = json.loads(
            (output_dir / "jury_annotation_manifest.json").read_text(encoding="utf-8")
        )
        config = load_config(config_path)
        llm_config = config.get("llm", {})
        if not isinstance(llm_config, dict):
            raise TypeError("jury llm configuration must be a mapping")
        packet_sha = sha256_file(packet_dir / "packet_manifest.json")
        _, packet_rows, adjudication_sha = _load_blind_packet(packet_dir)
        phase_b_gate = require_phase_b_authorized(
            gate_data_dir,
            gate_round1_dir,
            gate_round2_dir,
            gate_config_path,
        )
        path = output_dir / str(manifest["annotation_file"])
        rows = read_jsonl(path)
        juror_id = str(manifest["juror_id"])
        family = str(manifest["model_family"])
        spec = _validate_juror_identity(juror_id, family.lower(), llm_config)
        identity_path = output_dir / "run_identity.json"
        run_identity = json.loads(identity_path.read_text(encoding="utf-8"))
        runtime_identity = manifest.get("llm_runtime")
        if not isinstance(runtime_identity, dict):
            raise TypeError("jury manifest lacks a runtime identity")
        _validate_runtime_identity(runtime_identity, spec)
        if manifest.get("schema_version") != "far-jury-annotation-manifest-v1":
            errors.append("unsupported jury annotation manifest schema")
        if manifest.get("complete") is not True:
            errors.append("jury annotation manifest is incomplete")
        if (
            manifest.get("publication_gold") is not False
            or manifest.get("human_annotator") is not False
        ):
            errors.append("jury annotation provenance flags are invalid")
        if manifest.get("protocol_fingerprint") != PROTOCOL_ACTIVE_SHA256:
            errors.append("jury annotation uses a stale protocol")
        if manifest.get("prompt_sha256") != PROMPT_SHA256:
            errors.append("jury annotation prompt fingerprint mismatch")
        if manifest.get("source_packet_sha256") != packet_sha:
            errors.append("jury annotation source packet fingerprint mismatch")
        if manifest.get("source_adjudication_sha256") != adjudication_sha:
            errors.append("jury annotation blind-row fingerprint mismatch")
        if manifest.get("phase_b_gate") != phase_b_gate:
            errors.append("jury annotation Phase B authorization differs from verified G-A")
        if manifest.get("config_sha256") != sha256_file(config_path):
            errors.append("jury annotation configuration fingerprint mismatch")
        if manifest.get("run_identity_sha256") != sha256_file(identity_path):
            errors.append("jury annotation run identity fingerprint mismatch")
        expected_identity = {
            "juror_id": juror_id,
            "model_family": family,
            "config_sha256": manifest.get("config_sha256"),
            "llm_runtime": manifest.get("llm_runtime"),
            "protocol_fingerprint": PROTOCOL_ACTIVE_SHA256,
            "prompt_sha256": PROMPT_SHA256,
            "source_packet_sha256": packet_sha,
            "source_adjudication_sha256": adjudication_sha,
            "phase_b_gate": phase_b_gate,
        }
        if run_identity.get("schema_version") != "far-jury-run-identity-v1" or any(
            run_identity.get(key) != value for key, value in expected_identity.items()
        ):
            errors.append("jury annotation run identity content mismatch")
        if (
            not str(run_identity.get("implementation_sha256", "")).strip()
            or run_identity.get("source_revision", {}).get("git_dirty") is not False
            or not str(run_identity.get("source_revision", {}).get("git_commit", "")).strip()
        ):
            errors.append("jury annotation lacks a clean immutable source identity")
        if family.lower() in SYSTEM_MODEL_FAMILIES:
            errors.append("jury annotation family overlaps system families")
        if sha256_file(path) != manifest.get("annotation_sha256"):
            errors.append("jury annotation file fingerprint mismatch")
        ids = [str(row.get("sample_id", "")) for row in rows]
        if (
            len(ids) != len(set(ids))
            or len(rows) != manifest.get("samples")
            or len(rows) != manifest.get("expected_samples")
        ):
            errors.append("jury annotation rows are duplicate or incomplete")
        if set(ids) != {str(row["sample_id"]) for row in packet_rows}:
            errors.append("jury annotation does not cover the current blind packet")
        for row in rows:
            if (
                row.get("schema_version") != "far-jury-annotation-v1"
                or row.get("juror_id") != juror_id
                or row.get("model_family") != family
                or row.get("publication_gold") is not False
            ):
                errors.append("jury annotation row identity or provenance mismatch")
                break
            annotation = row.get("jury_annotation", {})
            normalized = _normalise_prediction(annotation, str(row.get("sample_id", "")))
            if normalized["conflict_type"] not in {*JURY_TYPES, "no_conflict"}:
                errors.append("jury annotation contains an out-of-space conflict type")
                break
            if normalized["conflict_present"] and not normalized["suggested_revised_answer"]:
                errors.append("conflict-positive jury annotation lacks a revision")
                break
        fallbacks = sum(_is_fallback(row) for row in rows)
        if fallbacks != manifest.get("fallbacks"):
            errors.append("jury fallback count mismatch")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "far-jury-annotation-audit-v1",
        "valid": not errors,
        "errors": errors,
        "samples": len(rows) if "rows" in locals() else 0,
        "fallbacks": fallbacks if "fallbacks" in locals() else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--juror-id", required=True)
    parser.add_argument("--model-family", required=True)
    parser.add_argument("--ramdocs-data-dir", type=Path, required=True)
    parser.add_argument("--ramdocs-round1-dir", type=Path, required=True)
    parser.add_argument("--ramdocs-round2-dir", type=Path, required=True)
    parser.add_argument("--ramdocs-config", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-fallbacks", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = (
        verify_juror(
            args.packet_dir,
            args.config,
            args.output_dir,
            args.ramdocs_data_dir,
            args.ramdocs_round1_dir,
            args.ramdocs_round2_dir,
            args.ramdocs_config,
        )
        if args.verify
        else annotate_juror(
            args.packet_dir,
            args.config,
            args.output_dir,
            args.ramdocs_data_dir,
            args.ramdocs_round1_dir,
            args.ramdocs_round2_dir,
            args.ramdocs_config,
            juror_id=args.juror_id,
            model_family=args.model_family,
            limit=args.limit,
            overwrite=args.overwrite,
            resume=args.resume,
            retry_fallbacks=args.retry_fallbacks,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.verify and not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
