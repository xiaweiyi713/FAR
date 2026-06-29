"""Generate non-gold LLM preannotations for blind FalsiRAG annotation packets."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.annotations import PACKET_VERSION
from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from bench.schema import VALID_CONFLICT_TYPES, VALID_REVISION_ACTIONS
from far.protocols import TextGenerator

AUTO_PACKET_VERSION = "falsirag-auto-annotation-v1"
LABEL_STUDIO_EXPORT_VERSION = "falsirag-label-studio-export-v1"

LABEL_STUDIO_CONFIG = """<View>
  <Style>
    .falsirag-block { margin-bottom: 1.25em; }
    .falsirag-meta { color: #666; font-size: 0.9em; }
  </Style>
  <Header value="FalsiRAG blind review"/>
  <View className="falsirag-block">
    <Text name="context" value="$context"/>
  </View>
  <Choices name="conflict_presence" toName="context" choice="single" showInLine="true">
    <Choice value="conflict"/>
    <Choice value="no_conflict"/>
  </Choices>
  <Choices name="conflict_type" toName="context" choice="single" showInLine="true">
    <Choice value="temporal"/>
    <Choice value="entity"/>
    <Choice value="numerical"/>
    <Choice value="causal"/>
    <Choice value="source_reliability"/>
    <Choice value="definition"/>
    <Choice value="counter_evidence"/>
    <Choice value="no_conflict"/>
  </Choices>
  <Choices name="revision_action" toName="context" choice="single" showInLine="true">
    <Choice value="correct_temporal"/>
    <Choice value="requalify_entity"/>
    <Choice value="replace_numerical"/>
    <Choice value="downgrade_causal_to_correlation"/>
    <Choice value="prefer_reliable_source"/>
    <Choice value="clarify_definition"/>
    <Choice value="retract"/>
    <Choice value="qualify_uncertainty"/>
  </Choices>
  <Choices name="revised_answer_acceptable" toName="context" choice="single" showInLine="true">
    <Choice value="acceptable"/>
    <Choice value="not_acceptable"/>
  </Choices>
  <TextArea name="suggested_revised_answer" toName="context" rows="4" editable="true"/>
  <TextArea name="rationale" toName="context" rows="5" editable="true"/>
</View>
"""


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


def build_review_draft(
    packet_dir: Path,
    preannotation_dir: Path,
    output_dir: Path,
    *,
    reviewer_id: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Convert machine preannotations into a reviewer-editable draft file.

    The draft is intentionally not referenced by ``packet_manifest.json`` and is
    rejected by ``compile_annotations`` until a human sets ``human_reviewed`` to
    true. This lets LLM suggestions accelerate review without silently becoming
    independent human labels.
    """

    packet_manifest_path = packet_dir / "packet_manifest.json"
    packet_sha256 = sha256_file(packet_manifest_path)
    preannotation_manifest = json.loads(
        (preannotation_dir / "preannotation_manifest.json").read_text(encoding="utf-8")
    )
    if preannotation_manifest.get("source_packet_sha256") != packet_sha256:
        raise ValueError("preannotations do not match the current annotation packet")
    preannotation_file = preannotation_dir / str(preannotation_manifest["preannotation_file"])
    preannotation_rows = read_jsonl(preannotation_file)
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass --overwrite to replace it")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    draft_rows = []
    for row in preannotation_rows:
        suggestion = row["preannotation"]
        present = bool(suggestion["conflict_present"])
        conflict_type = "" if not present else str(suggestion["conflict_type"])
        draft_rows.append(
            {
                "schema_version": PACKET_VERSION,
                "sample_id": row["sample_id"],
                "question": row["question"],
                "initial_answer": row["initial_answer"],
                "claims": row["claims"],
                "evidence": row["evidence"],
                "annotator_id": reviewer_id,
                "annotation": {
                    "conflict_present": present,
                    "conflict_type": conflict_type,
                    "revision_action": suggestion["revision_action"],
                    "revised_answer_acceptable": bool(suggestion["revised_answer_acceptable"]),
                    "rationale": (
                        f"[MACHINE DRAFT — human must verify]\n{suggestion.get('rationale', '')}"
                    ).strip(),
                },
                "suggested_revised_answer": suggestion.get("suggested_revised_answer", ""),
                "machine_confidence": suggestion.get("confidence", 0.0),
                "machine_preannotator_id": row.get("preannotator_id", ""),
                "draft_from_machine_preannotation": True,
                "human_reviewed": False,
            }
        )

    filename = f"draft_annotations_{reviewer_id}.jsonl"
    write_jsonl(output_dir / filename, draft_rows)
    result = {
        "schema_version": "falsirag-review-draft-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_packet_sha256": packet_sha256,
        "source_preannotation_sha256": sha256_file(preannotation_file),
        "reviewer_id": reviewer_id,
        "draft_file": filename,
        "samples": len(draft_rows),
        "human_review_required": True,
        "compile_guard": (
            "compile_annotations rejects these rows while "
            "draft_from_machine_preannotation=true and human_reviewed is false."
        ),
    }
    write_json(output_dir / "review_draft_manifest.json", result)
    return result


def _label_studio_context(row: dict[str, Any]) -> str:
    claims = "\n".join(
        f"- {claim['claim_id']}: {claim['claim']}" for claim in row.get("claims", [])
    )
    evidence = "\n\n".join(
        "\n".join(
            (
                f"### {item['evidence_id']}: {item.get('title', '')}",
                f"source: {item.get('source', '')}",
                f"date: {item.get('date', '')}",
                str(item.get("text", "")),
            )
        )
        for item in row.get("evidence", [])
    )
    return (
        f"## Sample\n{row['sample_id']}\n\n"
        f"## Question\n{row['question']}\n\n"
        f"## Initial answer\n{row['initial_answer']}\n\n"
        f"## Claims\n{claims}\n\n"
        f"## Evidence snippets\n{evidence}\n\n"
        "## Review note\n"
        "Gold labels and evidence roles are hidden. If a prediction is shown, treat it "
        "as a machine draft that must be independently verified."
    )


def _choice_result(field: str, value: str) -> dict[str, Any]:
    return {
        "from_name": field,
        "to_name": "context",
        "type": "choices",
        "value": {"choices": [value]},
    }


def _textarea_result(field: str, value: str) -> dict[str, Any]:
    return {
        "from_name": field,
        "to_name": "context",
        "type": "textarea",
        "value": {"text": [value]},
    }


def _label_studio_prediction(row: dict[str, Any]) -> dict[str, Any]:
    suggestion = row["preannotation"]
    present = bool(suggestion["conflict_present"])
    conflict_type = str(suggestion["conflict_type"] if present else "no_conflict")
    acceptable = "acceptable" if bool(suggestion["revised_answer_acceptable"]) else "not_acceptable"
    result = [
        _choice_result("conflict_presence", "conflict" if present else "no_conflict"),
        _choice_result("conflict_type", conflict_type),
        _choice_result("revision_action", str(suggestion["revision_action"])),
        _choice_result("revised_answer_acceptable", acceptable),
        _textarea_result(
            "suggested_revised_answer", str(suggestion.get("suggested_revised_answer", ""))
        ),
        _textarea_result("rationale", str(suggestion.get("rationale", ""))),
    ]
    return {
        "model_version": str(row.get("preannotator_id", "llm_preannotator")),
        "score": float(suggestion.get("confidence", 0.0)),
        "result": result,
    }


def export_label_studio(
    packet_dir: Path,
    output_dir: Path,
    *,
    preannotation_dir: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Export blind packet rows and optional predictions for Label Studio.

    The export is a review aid only. It keeps FAR's JSONL packet as the source of
    truth and does not relax the independent-human annotation gate.
    """

    packet_manifest_path = packet_dir / "packet_manifest.json"
    packet_manifest = json.loads(packet_manifest_path.read_text(encoding="utf-8"))
    packet_sha256 = sha256_file(packet_manifest_path)
    source_rows = read_jsonl(packet_dir / packet_manifest["adjudication_file"])
    preannotations_by_id: dict[str, dict[str, Any]] = {}
    preannotation_sha256 = ""
    preannotator_id = ""
    if preannotation_dir is not None:
        preannotation_manifest = json.loads(
            (preannotation_dir / "preannotation_manifest.json").read_text(encoding="utf-8")
        )
        if preannotation_manifest.get("source_packet_sha256") != packet_sha256:
            raise ValueError("preannotations do not match the current annotation packet")
        preannotation_file = preannotation_dir / str(preannotation_manifest["preannotation_file"])
        preannotation_sha256 = sha256_file(preannotation_file)
        preannotator_id = str(preannotation_manifest.get("preannotator_id", ""))
        preannotations_by_id = {
            str(row["sample_id"]): row for row in read_jsonl(preannotation_file)
        }

    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass --overwrite to replace it")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    tasks = []
    with_predictions = 0
    for row in source_rows:
        task: dict[str, Any] = {
            "data": {
                "sample_id": row["sample_id"],
                "context": _label_studio_context(row),
            },
            "meta": {
                "schema_version": LABEL_STUDIO_EXPORT_VERSION,
                "source_packet_sha256": packet_sha256,
                "publication_gold": False,
                "human_review_required": True,
            },
        }
        prediction_row = preannotations_by_id.get(str(row["sample_id"]))
        if prediction_row is not None:
            task["predictions"] = [_label_studio_prediction(prediction_row)]
            with_predictions += 1
        tasks.append(task)

    (output_dir / "label_config.xml").write_text(LABEL_STUDIO_CONFIG, encoding="utf-8")
    (output_dir / "tasks.json").write_text(
        json.dumps(tasks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    result = {
        "schema_version": LABEL_STUDIO_EXPORT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_packet_sha256": packet_sha256,
        "source_preannotation_sha256": preannotation_sha256,
        "preannotator_id": preannotator_id,
        "tasks_file": "tasks.json",
        "label_config_file": "label_config.xml",
        "tasks": len(tasks),
        "tasks_with_predictions": with_predictions,
        "publication_gold": False,
        "human_review_required": True,
        "import_note": (
            "Create a Label Studio project with label_config.xml, then import tasks.json. "
            "Predictions are machine drafts for review, not gold labels."
        ),
    }
    write_json(output_dir / "label_studio_manifest.json", result)
    return result


def _label_studio_results_to_annotation(
    sample_id: str,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    choices: dict[str, str] = {}
    text: dict[str, str] = {}
    for item in results:
        field = str(item.get("from_name", ""))
        value = item.get("value", {})
        if item.get("type") == "choices":
            selected = value.get("choices", []) if isinstance(value, dict) else []
            if selected:
                choices[field] = str(selected[0])
        elif item.get("type") == "textarea":
            selected_text = value.get("text", []) if isinstance(value, dict) else []
            if selected_text:
                text[field] = str(selected_text[0])
    presence = choices.get("conflict_presence")
    if presence not in {"conflict", "no_conflict"}:
        raise ValueError(f"{sample_id}: missing conflict_presence annotation")
    conflict_present = presence == "conflict"
    conflict_type = choices.get("conflict_type", "")
    if conflict_present:
        if conflict_type not in VALID_CONFLICT_TYPES:
            raise ValueError(f"{sample_id}: invalid conflict_type annotation")
    else:
        conflict_type = ""
    revision_action = choices.get("revision_action", "")
    if revision_action not in VALID_REVISION_ACTIONS:
        raise ValueError(f"{sample_id}: invalid revision_action annotation")
    acceptable = choices.get("revised_answer_acceptable")
    if acceptable not in {"acceptable", "not_acceptable"}:
        raise ValueError(f"{sample_id}: missing revised_answer_acceptable annotation")
    return {
        "conflict_present": conflict_present,
        "conflict_type": conflict_type,
        "revision_action": revision_action,
        "revised_answer_acceptable": acceptable == "acceptable",
        "rationale": text.get("rationale", ""),
    }


def import_label_studio(
    packet_dir: Path,
    label_studio_json: Path,
    output_dir: Path,
    *,
    reviewer_id: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Convert Label Studio review exports back into FAR annotation JSONL."""

    packet_manifest_path = packet_dir / "packet_manifest.json"
    packet_manifest = json.loads(packet_manifest_path.read_text(encoding="utf-8"))
    packet_sha256 = sha256_file(packet_manifest_path)
    source_rows = {
        str(row["sample_id"]): row
        for row in read_jsonl(packet_dir / packet_manifest["adjudication_file"])
    }
    exported_tasks = json.loads(label_studio_json.read_text(encoding="utf-8"))
    if not isinstance(exported_tasks, list):
        raise ValueError("Label Studio export must be a JSON array of tasks")

    annotations_by_id: dict[str, dict[str, Any]] = {}
    for task in exported_tasks:
        if not isinstance(task, dict):
            raise ValueError("Label Studio task must be an object")
        data = task.get("data", {})
        sample_id = str(data.get("sample_id", ""))
        if sample_id not in source_rows:
            raise ValueError(f"{sample_id}: unknown sample_id in Label Studio export")
        task_sha256 = task.get("meta", {}).get("source_packet_sha256")
        if task_sha256 not in {None, packet_sha256}:
            raise ValueError(f"{sample_id}: Label Studio task came from a different packet")
        annotations = task.get("annotations") or task.get("completions") or []
        if not annotations:
            raise ValueError(f"{sample_id}: missing human Label Studio annotation")
        first_annotation = annotations[0]
        results = first_annotation.get("result", [])
        if not isinstance(results, list):
            raise ValueError(f"{sample_id}: annotation result must be a list")
        annotations_by_id[sample_id] = _label_studio_results_to_annotation(sample_id, results)

    missing = set(source_rows) - set(annotations_by_id)
    if missing:
        preview = ", ".join(sorted(missing)[:5])
        raise ValueError(f"Label Studio export is missing {len(missing)} samples: {preview}")

    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass --overwrite to replace it")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    rows = []
    for sample_id in sorted(source_rows):
        source = dict(source_rows[sample_id])
        source.pop("adjudicator_id", None)
        source.pop("gold_annotation", None)
        source["annotator_id"] = reviewer_id
        source["annotation"] = annotations_by_id[sample_id]
        source["source_tool"] = "label_studio"
        source["human_reviewed"] = True
        rows.append(source)

    filename = f"annotations_{reviewer_id}.jsonl"
    write_jsonl(output_dir / filename, rows)
    result = {
        "schema_version": "falsirag-label-studio-import-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_packet_sha256": packet_sha256,
        "source_label_studio_sha256": sha256_file(label_studio_json),
        "reviewer_id": reviewer_id,
        "annotation_file": filename,
        "samples": len(rows),
        "human_reviewed": True,
        "publication_gold": False,
        "next_step": (
            "Copy or reference this file from packet_manifest.json as one independent "
            "reviewer annotation, then complete the second reviewer and adjudication files."
        ),
    }
    write_json(output_dir / "label_studio_import_manifest.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--packet-dir", type=Path, required=True)
    generate_parser.add_argument("--output-dir", type=Path, required=True)
    generate_parser.add_argument("--config", type=Path)
    generate_parser.add_argument("--preannotator-id", default="llm_preannotator")
    generate_parser.add_argument("--limit", type=int)
    generate_parser.add_argument("--overwrite", action="store_true")
    draft_parser = subparsers.add_parser("draft")
    draft_parser.add_argument("--packet-dir", type=Path, required=True)
    draft_parser.add_argument("--preannotation-dir", type=Path, required=True)
    draft_parser.add_argument("--output-dir", type=Path, required=True)
    draft_parser.add_argument("--reviewer-id", required=True)
    draft_parser.add_argument("--overwrite", action="store_true")
    label_studio_parser = subparsers.add_parser("label-studio")
    label_studio_parser.add_argument("--packet-dir", type=Path, required=True)
    label_studio_parser.add_argument("--preannotation-dir", type=Path)
    label_studio_parser.add_argument("--output-dir", type=Path, required=True)
    label_studio_parser.add_argument("--overwrite", action="store_true")
    label_studio_import_parser = subparsers.add_parser("label-studio-import")
    label_studio_import_parser.add_argument("--packet-dir", type=Path, required=True)
    label_studio_import_parser.add_argument("--label-studio-json", type=Path, required=True)
    label_studio_import_parser.add_argument("--output-dir", type=Path, required=True)
    label_studio_import_parser.add_argument("--reviewer-id", required=True)
    label_studio_import_parser.add_argument("--overwrite", action="store_true")
    # Backward-compatible direct mode from v0.1.0: no subcommand means generate.
    parser.add_argument("--packet-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--preannotator-id", default="llm_preannotator")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.command == "draft":
        result = build_review_draft(
            args.packet_dir,
            args.preannotation_dir,
            args.output_dir,
            reviewer_id=args.reviewer_id,
            overwrite=args.overwrite,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if args.command == "label-studio":
        result = export_label_studio(
            args.packet_dir,
            args.output_dir,
            preannotation_dir=args.preannotation_dir,
            overwrite=args.overwrite,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if args.command == "label-studio-import":
        result = import_label_studio(
            args.packet_dir,
            args.label_studio_json,
            args.output_dir,
            reviewer_id=args.reviewer_id,
            overwrite=args.overwrite,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return

    packet_dir = args.packet_dir
    output_dir = args.output_dir
    if packet_dir is None or output_dir is None:
        parser.error("generate mode requires --packet-dir and --output-dir")

    generator: TextGenerator | None = None
    model_name = ""
    if args.config is not None:
        from experiments.runner import build_generator, load_config

        config = load_config(args.config)
        generator = build_generator(config)
        model_name = str(config.get("llm", {}).get("model", ""))
    result = generate_preannotations(
        packet_dir,
        output_dir,
        generator=generator,
        preannotator_id=args.preannotator_id,
        limit=args.limit,
        overwrite=args.overwrite,
        model_name=model_name,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
