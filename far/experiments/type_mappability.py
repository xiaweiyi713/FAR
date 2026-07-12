"""Prepare and analyze the retrospective P6 type-mappability study."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from far.bench.annotations import cohen_kappa
from far.bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.experiments.runner import (
    _llm_runtime_identity,
    build_generator,
    load_config,
    release_generator,
)
from far.paths import experiment_config_dir, repository_root

ROOT = repository_root()
PROTOCOL_PATH = ROOT / "docs" / "PREREG_TYPE_MAPPABILITY_2026-07-10.md"
PROTOCOL_SHA256 = "57b4a647071945cf98c39b555d5bd249922c538a7eb4e558faa6f22d836c50c3"
PACKET_SCHEMA = "far-type-mappability-packet-v1"
RESULT_SCHEMA = "far-type-mappability-result-v1"
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 1729
MAPPABILITY_LABELS = ("clean", "partial", "unmappable")
TYPE_NAMES = (
    "temporal",
    "entity",
    "numerical",
    "causal",
    "source_reliability",
    "definition",
    "counter_evidence",
)
HUMAN_ROLES = ("reviewer_a", "reviewer_b", "adjudicator")
DATASET_ORDER = ("wikicontradict", "rag_conflicts")
MACHINE_PRELABEL_MAX_ATTEMPTS = 3
MACHINE_PRELABEL_RETRY_INSTRUCTION = (
    "The previous JSON did not satisfy the frozen annotation schema. Correct only the schema "
    "violation described below and return exactly one JSON object with no markdown."
)

DATASETS: dict[str, dict[str, Any]] = {
    "wikicontradict": {
        "path": ROOT / "bench" / "external" / "wikicontradict_v1",
        "tasks_sha256": "a2c264696f6785a2748a8af214843bfd5c8739cc5e77946243910cd1f205b563",
        "corpus_sha256": "f684ab5008628bc7ab41198d649e9b9794586d372e1c2dc767cefd16129e1d46",
        "typed_scores": ROOT
        / "diagnostics/boundary_v1/evaluations/wikicontradict/far/scores.jsonl",
        "typed_scores_sha256": "87cfb1f5baf3513bc0276427f24ac4160f6923a0921075e291fde8ef7e13b56a",
        "untyped_scores": ROOT
        / "diagnostics/boundary_v1/evaluations/wikicontradict"
        / "far_minus_typed_conflict/scores.jsonl",
        "untyped_scores_sha256": "231973bca0f0ca413ce9692a766c2dd53406e5088996620fc124c968c7f155de",
        "expected_selected": 150,
    },
    "rag_conflicts": {
        "path": ROOT / "bench" / "external" / "rag_conflicts_v1",
        "tasks_sha256": "3776cd96b19b1e581d3a4f88d45be8fc73c4d5c153bc876b09cde28d7feb871a",
        "corpus_sha256": "6beb087fb2e181d1ca59ae5d9aa0d0c92b78e3854d3d22dfec809118595bfb5b",
        "typed_scores": ROOT / "diagnostics/boundary_v1/evaluations/rag_conflicts/far/scores.jsonl",
        "typed_scores_sha256": "d64f0924f50ce515ec82cc07fdf9f5dd357d811042a6a2bc6cc674741bb1467e",
        "untyped_scores": ROOT
        / "diagnostics/boundary_v1/evaluations/rag_conflicts/far_minus_typed_conflict/scores.jsonl",
        "untyped_scores_sha256": "4abfb386ca428c859943061031938c7833912607a5477482feb40def617ebbdd",
        "expected_selected": 67,
    },
}

_TYPE_GUIDE = {
    "temporal": "time, date, version, or validity-period conflict for the same fact slot",
    "entity": "entity identity, reference, namesake, or entity-value substitution",
    "numerical": "conflicting comparable measurement, count, ratio, or quantity",
    "causal": "causality denied, downgraded to association, or limited by confounding",
    "source_reliability": "resolution depends on attributable source authority or reliability",
    "definition": "definition, scope, operationalization, or granularity changes meaning",
    "counter_evidence": (
        "explicit direct negation or counterexample to the same proposition when no more "
        "specific type applies"
    ),
}


def _stable_sha(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_protocol_inputs() -> dict[str, Any]:
    errors: list[str] = []
    if not PROTOCOL_PATH.is_file() or sha256_file(PROTOCOL_PATH) != PROTOCOL_SHA256:
        errors.append("type-mappability protocol fingerprint mismatch")
    fingerprints: dict[str, dict[str, str]] = {}
    for dataset in DATASET_ORDER:
        spec = DATASETS[dataset]
        data_dir = Path(spec["path"])
        observed = {
            "tasks_sha256": sha256_file(data_dir / "tasks.jsonl"),
            "corpus_sha256": sha256_file(data_dir / "corpus.jsonl"),
            "typed_scores_sha256": sha256_file(Path(spec["typed_scores"])),
            "untyped_scores_sha256": sha256_file(Path(spec["untyped_scores"])),
        }
        fingerprints[dataset] = observed
        for key, digest in observed.items():
            if digest != spec[key]:
                errors.append(f"{dataset} {key} mismatch")
    return {
        "schema_version": "far-type-mappability-input-audit-v1",
        "valid": not errors,
        "errors": errors,
        "protocol_sha256": PROTOCOL_SHA256,
        "fingerprints": fingerprints,
        "retrospective": True,
        "confirmatory_h4": False,
        "publication_gold": False,
        "test_accessed": False,
    }


def _selected_tasks(dataset: str) -> list[dict[str, Any]]:
    spec = DATASETS[dataset]
    rows = read_jsonl(Path(spec["path"]) / "tasks.jsonl")
    selected = [row for row in rows if str(row.get("conflict_type")) != "no_conflict"]
    if len(selected) != int(spec["expected_selected"]):
        raise ValueError(f"{dataset}: conflict-positive sample count changed")
    if {str(row.get("split")) for row in selected} != {"dev"}:
        raise ValueError(f"{dataset}: selected samples must all be dev")
    ids = [str(row.get("id")) for row in selected]
    if len(set(ids)) != len(ids) or any(not sample_id for sample_id in ids):
        raise ValueError(f"{dataset}: selected task IDs are invalid")
    return sorted(selected, key=lambda row: str(row["id"]))


def _corpus_by_sample(dataset: str) -> dict[str, dict[str, dict[str, Any]]]:
    rows = read_jsonl(Path(DATASETS[dataset]["path"]) / "corpus.jsonl")
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        sample_id = str(row.get("metadata", {}).get("sample_id", ""))
        document_id = str(row.get("doc_id", ""))
        if not sample_id or not document_id or document_id in grouped[sample_id]:
            raise ValueError(f"{dataset}: corpus IDs are invalid")
        grouped[sample_id][document_id] = row
    return grouped


def build_annotation_items() -> list[dict[str, Any]]:
    audit = verify_protocol_inputs()
    if audit["valid"] is not True:
        raise ValueError(f"type-mappability inputs are invalid: {audit['errors']}")
    items: list[dict[str, Any]] = []
    for dataset in DATASET_ORDER:
        corpus = _corpus_by_sample(dataset)
        for task in _selected_tasks(dataset):
            sample_id = str(task["id"])
            document_ids = [str(value) for value in task.get("document_ids", [])]
            if not document_ids or any(
                value not in corpus.get(sample_id, {}) for value in document_ids
            ):
                raise ValueError(f"{sample_id}: annotation evidence is incomplete")
            context = {
                "schema_version": "far-type-mappability-item-v1",
                "sample_id": sample_id,
                "dataset": dataset,
                "question": str(task["question"]),
                "initial_answer": str(task["initial_answer"]),
                "reference_answers": [str(value) for value in task.get("reference_answers", [])],
                "evidence": [
                    {
                        "evidence_id": document_id,
                        "title": str(corpus[sample_id][document_id].get("title", "")),
                        "text": str(corpus[sample_id][document_id].get("content", "")),
                        "source": str(corpus[sample_id][document_id].get("source", "")),
                        "date": corpus[sample_id][document_id].get("date"),
                    }
                    for document_id in document_ids
                ],
            }
            items.append({**context, "context_sha256": _stable_sha(context)})
    if len(items) != 217 or len({str(item["sample_id"]) for item in items}) != 217:
        raise ValueError("type-mappability selection must contain 217 unique samples")
    return items


def _instructions() -> str:
    type_lines = "\n".join(f"- `{name}`: {_TYPE_GUIDE[name]}" for name in TYPE_NAMES)
    return (
        "# P6 type-mappability annotation packet\n\n"
        "Distribute only `items.jsonl` plus one matching reviewer template to each reviewer. "
        "Reviewers work independently without seeing `analysis_index.jsonl`, model prelabels, "
        "another reviewer, or FAR scores.\n\n"
        "## Types\n\n"
        f"{type_lines}\n\n"
        "## Annotation schema\n\n"
        "- clean: exactly one mapped type, empty missing_concept.\n"
        "- partial: one or more mapped types and a non-empty missing_concept.\n"
        "- unmappable: no mapped types and a non-empty missing_concept.\n\n"
        "Every annotation also requires a non-empty rationale. Install completed files with "
        "`falsirag diag type-mappability install`; do not edit packet provenance files.\n\n"
        "## Workflow\n\n"
        "```bash\n"
        "falsirag diag type-mappability prelabel --packet-dir <packet>\n"
        "falsirag diag type-mappability install --packet-dir <packet> --role reviewer_a "
        "--annotator-id <id-a> --input <completed-a.jsonl>\n"
        "falsirag diag type-mappability install --packet-dir <packet> --role reviewer_b "
        "--annotator-id <id-b> --input <completed-b.jsonl>\n"
        "falsirag diag type-mappability install --packet-dir <packet> --role adjudicator "
        "--annotator-id <id-c> --input <completed-adjudication.jsonl>\n"
        "falsirag diag type-mappability status --packet-dir <packet>\n"
        "falsirag diag type-mappability analyze --packet-dir <packet> --output-dir <report-dir>\n"
        "falsirag diag type-mappability verify --packet-dir <packet> --report-dir <report-dir>\n"
        "```\n"
    )


def _prepare_output(path: Path, *, overwrite: bool) -> None:
    if not path.exists():
        path.mkdir(parents=True)
        return
    if not any(path.iterdir()):
        return
    if not overwrite:
        raise FileExistsError("type-mappability packet directory must be empty")
    manifest_path = path / "packet_manifest.json"
    if not manifest_path.is_file():
        raise ValueError("refusing to overwrite a directory not owned by this study")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != PACKET_SCHEMA:
        raise ValueError("refusing to overwrite an incompatible packet")
    shutil.rmtree(path)
    path.mkdir(parents=True)


def prepare_packet(output_dir: Path, *, overwrite: bool = False) -> dict[str, Any]:
    _prepare_output(output_dir, overwrite=overwrite)
    items = build_annotation_items()
    write_jsonl(output_dir / "items.jsonl", items)
    item_by_id = {str(item["sample_id"]): item for item in items}
    analysis_index = [
        {
            "sample_id": str(task["id"]),
            "dataset": dataset,
            "strata": dict(task.get("strata", {})),
            "context_sha256": item_by_id[str(task["id"])]["context_sha256"],
        }
        for dataset in DATASET_ORDER
        for task in _selected_tasks(dataset)
    ]
    write_jsonl(output_dir / "analysis_index.jsonl", analysis_index)
    templates = output_dir / "templates"
    template_rows = [
        {
            "sample_id": item["sample_id"],
            "context_sha256": item["context_sha256"],
            "annotation": None,
        }
        for item in items
    ]
    for role in HUMAN_ROLES:
        write_jsonl(templates / f"{role}.jsonl", template_rows)
    (output_dir / "INSTRUCTIONS.md").write_text(_instructions(), encoding="utf-8")
    immutable_files = {
        "items.jsonl": sha256_file(output_dir / "items.jsonl"),
        "analysis_index.jsonl": sha256_file(output_dir / "analysis_index.jsonl"),
        "templates/reviewer_a.jsonl": sha256_file(templates / "reviewer_a.jsonl"),
        "templates/reviewer_b.jsonl": sha256_file(templates / "reviewer_b.jsonl"),
        "templates/adjudicator.jsonl": sha256_file(templates / "adjudicator.jsonl"),
        "INSTRUCTIONS.md": sha256_file(output_dir / "INSTRUCTIONS.md"),
    }
    manifest = {
        "schema_version": PACKET_SCHEMA,
        "protocol_sha256": PROTOCOL_SHA256,
        "samples": len(items),
        "dataset_counts": {
            dataset: sum(str(item["dataset"]) == dataset for item in items)
            for dataset in DATASET_ORDER
        },
        "mappability_labels": list(MAPPABILITY_LABELS),
        "type_names": list(TYPE_NAMES),
        "immutable_files": immutable_files,
        "input_audit": verify_protocol_inputs(),
        "reviewers_independent": True,
        "analysis_index_hidden_from_reviewers": True,
        "machine_prelabels_hidden_until_adjudication": True,
        "retrospective": True,
        "confirmatory_h4": False,
        "publication_gold": False,
        "test_accessed": False,
    }
    write_json(output_dir / "packet_manifest.json", manifest)
    return manifest


def _annotation_items(packet_dir: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest_path = packet_dir / "packet_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("type-mappability packet manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != PACKET_SCHEMA:
        raise ValueError("unsupported type-mappability packet schema")
    if manifest.get("protocol_sha256") != PROTOCOL_SHA256:
        raise ValueError("packet protocol fingerprint mismatch")
    immutable = manifest.get("immutable_files", {})
    if not isinstance(immutable, dict):
        raise ValueError("packet immutable file map is invalid")
    for relative, digest in immutable.items():
        path = packet_dir / str(relative)
        if not path.is_file() or sha256_file(path) != digest:
            raise ValueError(f"packet immutable file changed: {relative}")
    rows = read_jsonl(packet_dir / "items.jsonl")
    by_id = {str(row.get("sample_id")): row for row in rows}
    if len(rows) != 217 or len(by_id) != 217 or int(manifest.get("samples", -1)) != 217:
        raise ValueError("packet must contain 217 unique annotation items")
    for sample_id, row in by_id.items():
        context = {key: value for key, value in row.items() if key != "context_sha256"}
        if not sample_id or row.get("context_sha256") != _stable_sha(context):
            raise ValueError(f"{sample_id}: annotation context fingerprint mismatch")
    index_rows = read_jsonl(packet_dir / "analysis_index.jsonl")
    index_by_id = {str(row.get("sample_id", "")): row for row in index_rows}
    if len(index_rows) != len(by_id) or set(index_by_id) != set(by_id):
        raise ValueError("packet analysis index sample set is invalid")
    merged: dict[str, dict[str, Any]] = {}
    for sample_id, row in by_id.items():
        index = index_by_id[sample_id]
        if (
            index.get("context_sha256") != row["context_sha256"]
            or index.get("dataset") != row["dataset"]
            or not isinstance(index.get("strata"), dict)
        ):
            raise ValueError(f"{sample_id}: packet analysis index provenance is invalid")
        merged[sample_id] = {**row, "analysis_strata": dict(index["strata"])}
    return manifest, merged


def validate_annotation(value: Any, *, sample_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{sample_id}: annotation must be an object")
    expected = {"mappability", "mapped_types", "missing_concept", "rationale"}
    if set(value) != expected:
        raise ValueError(f"{sample_id}: annotation fields must be {sorted(expected)}")
    label = str(value.get("mappability", ""))
    if label not in MAPPABILITY_LABELS:
        raise ValueError(f"{sample_id}: invalid mappability label")
    raw_types = value.get("mapped_types")
    if not isinstance(raw_types, list) or any(str(item) not in TYPE_NAMES for item in raw_types):
        raise ValueError(f"{sample_id}: mapped_types must use the frozen ontology")
    mapped_types = [name for name in TYPE_NAMES if name in {str(item) for item in raw_types}]
    if len(mapped_types) != len(raw_types):
        raise ValueError(f"{sample_id}: mapped_types must be unique")
    missing = str(value.get("missing_concept", "")).strip()
    rationale = str(value.get("rationale", "")).strip()
    if not rationale:
        raise ValueError(f"{sample_id}: rationale must be non-empty")
    if label == "clean" and (len(mapped_types) != 1 or missing):
        raise ValueError(f"{sample_id}: clean requires one type and no missing concept")
    if label == "partial" and (not mapped_types or not missing):
        raise ValueError(f"{sample_id}: partial requires mapped types and a missing concept")
    if label == "unmappable" and (mapped_types or not missing):
        raise ValueError(f"{sample_id}: unmappable requires no types and a missing concept")
    return {
        "mappability": label,
        "mapped_types": mapped_types,
        "missing_concept": missing,
        "rationale": rationale,
    }


def _source_annotations(
    source_path: Path,
    items: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = read_jsonl(source_path)
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        sample_id = str(row.get("sample_id", ""))
        if not sample_id or sample_id in by_id:
            raise ValueError("annotation source contains a missing or duplicate sample ID")
        if sample_id not in items:
            raise ValueError(f"annotation source contains unknown sample {sample_id}")
        if row.get("context_sha256") not in {None, items[sample_id]["context_sha256"]}:
            raise ValueError(f"{sample_id}: annotation context fingerprint differs")
        by_id[sample_id] = validate_annotation(row.get("annotation"), sample_id=sample_id)
    if set(by_id) != set(items):
        missing = sorted(set(items) - set(by_id))
        raise ValueError(f"annotation source is incomplete; missing {len(missing)} samples")
    return [
        {
            "sample_id": sample_id,
            "context_sha256": items[sample_id]["context_sha256"],
            "annotation": by_id[sample_id],
        }
        for sample_id in sorted(by_id)
    ]


def _completed_path(packet_dir: Path, role: str) -> Path:
    return packet_dir / "completed" / f"{role}.jsonl"


def install_human_annotations(
    packet_dir: Path,
    source_path: Path,
    *,
    role: str,
    annotator_id: str,
) -> dict[str, Any]:
    if role not in HUMAN_ROLES:
        raise ValueError(f"human annotation role must be one of {HUMAN_ROLES}")
    annotator_id = annotator_id.strip()
    if not annotator_id:
        raise ValueError("annotator_id must be non-empty")
    _, items = _annotation_items(packet_dir)
    target = _completed_path(packet_dir, role)
    if target.exists():
        raise FileExistsError(f"{role} annotations are already installed")
    adjudicator_path = _completed_path(packet_dir, "adjudicator")
    if role in {"reviewer_a", "reviewer_b"} and adjudicator_path.exists():
        raise ValueError("reviewer annotations cannot be installed after adjudication")
    if role == "adjudicator":
        for prerequisite in ("reviewer_a", "reviewer_b"):
            if not _completed_path(packet_dir, prerequisite).is_file():
                raise ValueError("adjudication requires both frozen reviewer files")
            _load_installed(packet_dir, items, prerequisite)
        if not _completed_path(packet_dir, "machine_prelabels").is_file():
            raise ValueError("adjudication requires frozen machine prelabels")
        _load_machine(packet_dir, items)
    existing_ids: set[str] = set()
    for other_role in HUMAN_ROLES:
        other = _completed_path(packet_dir, other_role)
        if other.is_file():
            existing_rows = read_jsonl(other)
            existing_ids.update(str(row.get("annotator_id", "")) for row in existing_rows)
    if annotator_id in existing_ids:
        raise ValueError("reviewer and adjudicator IDs must be distinct")
    rows = _source_annotations(source_path, items)
    installed = [{**row, "role": role, "annotator_id": annotator_id} for row in rows]
    write_jsonl(target, installed)
    result: dict[str, Any] = {
        "schema_version": "far-type-mappability-human-install-v1",
        "role": role,
        "annotator_id": annotator_id,
        "samples": len(installed),
        "source_sha256": sha256_file(source_path),
        "installed_sha256": sha256_file(target),
    }
    write_json(packet_dir / "completed" / f"{role}_install.json", result)
    return result


def _load_installed(
    packet_dir: Path,
    items: dict[str, dict[str, Any]],
    role: str,
) -> tuple[str, dict[str, dict[str, Any]]]:
    path = _completed_path(packet_dir, role)
    install_path = packet_dir / "completed" / f"{role}_install.json"
    install = json.loads(install_path.read_text(encoding="utf-8"))
    if (
        install.get("schema_version") != "far-type-mappability-human-install-v1"
        or install.get("role") != role
        or install.get("installed_sha256") != sha256_file(path)
    ):
        raise ValueError(f"{role}: installed file differs from its frozen install manifest")
    rows = read_jsonl(path)
    by_id: dict[str, dict[str, Any]] = {}
    annotator_ids: set[str] = set()
    for row in rows:
        sample_id = str(row.get("sample_id", ""))
        if sample_id not in items or sample_id in by_id:
            raise ValueError(f"{role}: sample set is invalid")
        if (
            row.get("role") != role
            or row.get("context_sha256") != items[sample_id]["context_sha256"]
        ):
            raise ValueError(f"{sample_id}: installed {role} provenance is invalid")
        annotator_ids.add(str(row.get("annotator_id", "")).strip())
        by_id[sample_id] = validate_annotation(row.get("annotation"), sample_id=sample_id)
    if set(by_id) != set(items) or "" in annotator_ids or len(annotator_ids) != 1:
        raise ValueError(f"{role}: installed annotations are incomplete or IDs are inconsistent")
    annotator_id = next(iter(annotator_ids))
    if install.get("annotator_id") != annotator_id:
        raise ValueError(f"{role}: installed annotator ID differs from its manifest")
    return annotator_id, by_id


def packet_status(packet_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    roles: dict[str, Any] = {}
    annotator_ids: list[str] = []
    try:
        manifest, items = _annotation_items(packet_dir)
    except (AttributeError, FileNotFoundError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "schema_version": "far-type-mappability-status-v1",
            "valid_packet": False,
            "errors": [str(exc)],
            "ready_to_analyze": False,
            "retrospective": True,
            "confirmatory_h4": False,
        }
    for role in HUMAN_ROLES:
        path = _completed_path(packet_dir, role)
        state: dict[str, Any] = {"installed": path.is_file(), "complete": False}
        if path.is_file():
            try:
                annotator_id, rows = _load_installed(packet_dir, items, role)
                state.update(
                    {
                        "complete": True,
                        "annotator_id": annotator_id,
                        "samples": len(rows),
                        "sha256": sha256_file(path),
                    }
                )
                annotator_ids.append(annotator_id)
            except (
                AttributeError,
                FileNotFoundError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                state["error"] = str(exc)
                errors.append(str(exc))
        roles[role] = state
    input_audit = verify_protocol_inputs()
    if input_audit["valid"] is not True:
        errors.extend(str(error) for error in input_audit["errors"])
    machine_path = _completed_path(packet_dir, "machine_prelabels")
    machine_identity = packet_dir / "completed" / "machine_identity.json"
    machine_complete = False
    machine_error: str | None = None
    if machine_path.is_file() and machine_identity.is_file():
        try:
            _, machine_rows = _load_machine(packet_dir, items)
            machine_complete = len(machine_rows) == len(items)
        except (
            AttributeError,
            FileNotFoundError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            machine_error = str(exc)
            errors.append(machine_error)
    if len(annotator_ids) != len(set(annotator_ids)):
        errors.append("reviewer and adjudicator IDs are not distinct")
    ready = (
        not errors
        and all(bool(roles[role]["complete"]) for role in HUMAN_ROLES)
        and machine_complete
    )
    return {
        "schema_version": "far-type-mappability-status-v1",
        "valid_packet": True,
        "samples": int(manifest["samples"]),
        "input_audit": input_audit,
        "roles": roles,
        "machine_prelabels": {
            "installed": machine_path.is_file(),
            "identity_installed": machine_identity.is_file(),
            "complete": machine_complete,
            "error": machine_error,
        },
        "errors": errors,
        "ready_to_analyze": ready,
        "human_iaa_computed": False,
        "human_identity_verified": False,
        "retrospective": True,
        "confirmatory_h4": False,
        "publication_gold": False,
        "test_accessed": False,
    }


def _validate_machine_identity(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("machine prelabel identity must be a JSON object")
    required = {
        "model",
        "model_digest",
        "config_sha256",
        "prompt_template_sha256",
    }
    if not required <= set(value):
        raise ValueError(f"machine identity is missing fields: {sorted(required - set(value))}")
    result = {key: str(value[key]).strip() for key in sorted(required)}
    if any(not item for item in result.values()):
        raise ValueError("machine identity fields must be non-empty")
    for field in ("config_sha256", "prompt_template_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", result[field]):
            raise ValueError(f"machine identity {field} must be a SHA-256 digest")
    digest = result["model_digest"].removeprefix("sha256:")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("machine identity model_digest must be immutable SHA-256")
    return result


def install_machine_prelabels(
    packet_dir: Path,
    source_path: Path,
    identity_path: Path,
) -> dict[str, Any]:
    _, items = _annotation_items(packet_dir)
    target = _completed_path(packet_dir, "machine_prelabels")
    target_identity = packet_dir / "completed" / "machine_identity.json"
    if target.exists() or target_identity.exists():
        raise FileExistsError("machine prelabels are already installed")
    if _completed_path(packet_dir, "adjudicator").exists():
        raise ValueError("machine prelabels cannot be installed after adjudication")
    rows = _source_annotations(source_path, items)
    source_by_id = {str(row.get("sample_id", "")): row for row in read_jsonl(source_path)}
    identity = _validate_machine_identity(json.loads(identity_path.read_text(encoding="utf-8")))
    identity_sha = _stable_sha(identity)
    installed: list[dict[str, Any]] = []
    for row in rows:
        sample_id = str(row["sample_id"])
        source = source_by_id[sample_id]
        provenance: dict[str, Any] = {}
        provenance_fields = {
            name
            for name in ("raw_response", "raw_response_sha256", "prompt_sha256")
            if source.get(name) is not None
        }
        if provenance_fields and provenance_fields != {
            "raw_response",
            "raw_response_sha256",
            "prompt_sha256",
        }:
            raise ValueError(f"{sample_id}: machine source provenance must be all-or-none")
        if source.get("raw_response") is not None:
            attempts = _validate_machine_attempts(source, items[sample_id], sample_id=sample_id)
            provenance = {
                "raw_response": source["raw_response"],
                "raw_response_sha256": source["raw_response_sha256"],
                "prompt_sha256": source["prompt_sha256"],
            }
            if source.get("attempts") is not None:
                provenance["attempts"] = attempts
        installed.append(
            {
                **row,
                "role": "machine_prelabel",
                "machine_identity_sha256": identity_sha,
                **provenance,
            }
        )
    write_jsonl(target, installed)
    write_json(target_identity, identity)
    result = {
        "schema_version": "far-type-mappability-machine-install-v1",
        "samples": len(installed),
        "source_sha256": sha256_file(source_path),
        "source_identity_sha256": sha256_file(identity_path),
        "installed_sha256": sha256_file(target),
        "installed_identity_sha256": sha256_file(target_identity),
    }
    write_json(packet_dir / "completed" / "machine_install.json", result)
    return result


def _load_machine(
    packet_dir: Path,
    items: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    identity_path = packet_dir / "completed" / "machine_identity.json"
    prelabels_path = _completed_path(packet_dir, "machine_prelabels")
    install_path = packet_dir / "completed" / "machine_install.json"
    install = json.loads(install_path.read_text(encoding="utf-8"))
    if (
        install.get("schema_version")
        not in {
            "far-type-mappability-machine-install-v1",
            "far-type-mappability-machine-prelabel-v1",
        }
        or install.get("samples") != len(items)
        or install.get("installed_sha256") != sha256_file(prelabels_path)
        or install.get("installed_identity_sha256") != sha256_file(identity_path)
    ):
        raise ValueError("machine files differ from their frozen install manifest")
    identity = _validate_machine_identity(json.loads(identity_path.read_text(encoding="utf-8")))
    identity_sha = _stable_sha(identity)
    rows = read_jsonl(prelabels_path)
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        sample_id = str(row.get("sample_id", ""))
        if sample_id not in items or sample_id in by_id:
            raise ValueError("machine prelabel sample set is invalid")
        if (
            row.get("role") != "machine_prelabel"
            or row.get("context_sha256") != items[sample_id]["context_sha256"]
            or row.get("machine_identity_sha256") != identity_sha
        ):
            raise ValueError(f"{sample_id}: machine prelabel provenance is invalid")
        if row.get("raw_response") is not None:
            _validate_machine_attempts(row, items[sample_id], sample_id=sample_id)
        by_id[sample_id] = validate_annotation(row.get("annotation"), sample_id=sample_id)
    if set(by_id) != set(items):
        raise ValueError("machine prelabels are incomplete")
    return identity, by_id


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


def _parse_machine_response(response: str, *, sample_id: str) -> dict[str, Any]:
    cleaned = _JSON_FENCE.sub("", response.strip())
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{sample_id}: machine prelabel is not valid JSON") from exc
    return validate_annotation(value, sample_id=sample_id)


def _prelabel_prompt(item: dict[str, Any]) -> str:
    evidence = "\n\n".join(
        f"[{row['evidence_id']}] {row['title']}\n{row['text']}" for row in item["evidence"]
    )
    types = "\n".join(f"- {name}: {_TYPE_GUIDE[name]}" for name in TYPE_NAMES)
    return (
        f"Question: {item['question']}\n"
        f"Initial answer: {item['initial_answer']}\n"
        f"Reference answers: {json.dumps(item['reference_answers'], ensure_ascii=False)}\n"
        f"Evidence:\n{evidence}\n\n"
        f"Frozen FAR types:\n{types}\n\n"
        "Classify whether the decisive conflict is cleanly, partially, or not mappable to the "
        "frozen ontology. counter_evidence is only an explicit direct negation/counterexample, "
        "not a catch-all. Return exactly one JSON object with keys mappability, mapped_types, "
        "missing_concept, rationale. clean requires one type and no missing concept; partial "
        "requires at least one type and a missing concept; unmappable requires no types and a "
        "missing concept."
    )


def _prelabel_retry_prompt(
    item: dict[str, Any],
    *,
    previous_response: str,
    validation_error: str,
) -> str:
    return (
        f"{_prelabel_prompt(item)}\n\n"
        f"{MACHINE_PRELABEL_RETRY_INSTRUCTION}\n"
        f"Validation error: {validation_error}\n"
        f"Previous response: {previous_response}"
    )


def _validate_machine_attempts(
    row: dict[str, Any],
    item: dict[str, Any],
    *,
    sample_id: str,
) -> list[dict[str, Any]]:
    attempts = row.get("attempts")
    if attempts is None:
        response = str(row.get("raw_response", ""))
        response_sha = hashlib.sha256(response.encode("utf-8")).hexdigest()
        prompt_sha = hashlib.sha256(_prelabel_prompt(item).encode("utf-8")).hexdigest()
        if row.get("raw_response_sha256") != response_sha:
            raise ValueError(f"{sample_id}: machine response fingerprint mismatch")
        if row.get("prompt_sha256") != prompt_sha:
            raise ValueError(f"{sample_id}: machine prompt fingerprint mismatch")
        if _parse_machine_response(response, sample_id=sample_id) != row.get("annotation"):
            raise ValueError(f"{sample_id}: machine response and annotation differ")
        return []
    if not isinstance(attempts, list) or not 1 <= len(attempts) <= MACHINE_PRELABEL_MAX_ATTEMPTS:
        raise ValueError(f"{sample_id}: machine attempt provenance is invalid")
    prompt = _prelabel_prompt(item)
    parsed: dict[str, Any] | None = None
    for index, attempt in enumerate(attempts, start=1):
        if not isinstance(attempt, dict) or attempt.get("attempt") != index:
            raise ValueError(f"{sample_id}: machine attempt order is invalid")
        response = str(attempt.get("raw_response", ""))
        response_sha = hashlib.sha256(response.encode("utf-8")).hexdigest()
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if attempt.get("raw_response_sha256") != response_sha:
            raise ValueError(f"{sample_id}: machine attempt response fingerprint mismatch")
        if attempt.get("prompt_sha256") != prompt_sha:
            raise ValueError(f"{sample_id}: machine attempt prompt fingerprint mismatch")
        try:
            parsed = _parse_machine_response(response, sample_id=sample_id)
        except ValueError as exc:
            error = str(exc)
            if (
                attempt.get("valid") is not False
                or attempt.get("validation_error") != error
                or index == len(attempts)
            ):
                raise ValueError(f"{sample_id}: invalid machine attempt provenance") from exc
            prompt = _prelabel_retry_prompt(
                item,
                previous_response=response,
                validation_error=error,
            )
        else:
            if (
                attempt.get("valid") is not True
                or attempt.get("validation_error") is not None
                or index != len(attempts)
            ):
                raise ValueError(f"{sample_id}: valid machine attempt provenance is invalid")
    final = attempts[-1]
    if (
        parsed != row.get("annotation")
        or row.get("raw_response") != final.get("raw_response")
        or row.get("raw_response_sha256") != final.get("raw_response_sha256")
        or row.get("prompt_sha256") != final.get("prompt_sha256")
    ):
        raise ValueError(f"{sample_id}: final machine attempt differs from installed annotation")
    return attempts


def prelabel_packet(packet_dir: Path, config_path: Path) -> dict[str, Any]:
    _, items = _annotation_items(packet_dir)
    target = _completed_path(packet_dir, "machine_prelabels")
    target_identity = packet_dir / "completed" / "machine_identity.json"
    if target.exists() or target_identity.exists():
        raise FileExistsError("machine prelabels are already installed")
    if _completed_path(packet_dir, "adjudicator").exists():
        raise ValueError("machine prelabels cannot be generated after adjudication")
    config = load_config(config_path)
    generator = build_generator(config)
    if generator is None:
        raise ValueError("machine prelabeling requires an enabled text generator")
    runtime = _llm_runtime_identity(config)
    model = str(config.get("llm", {}).get("model", ""))
    digest = str(runtime.get("ollama_model", {}).get("digest", ""))
    if not model or not digest:
        raise ValueError("machine prelabel runtime must expose a model and immutable digest")
    prompt_template = {
        "type_guide": _TYPE_GUIDE,
        "schema": list(MAPPABILITY_LABELS),
        "system_prompt": "Classify ontology mappability from only the supplied text.",
        "temperature": 0.0,
        "max_tokens": 500,
        "max_attempts": MACHINE_PRELABEL_MAX_ATTEMPTS,
        "retry_instruction": MACHINE_PRELABEL_RETRY_INSTRUCTION,
    }
    identity = {
        "model": model,
        "model_digest": digest,
        "config_sha256": sha256_file(config_path),
        "prompt_template_sha256": _stable_sha(prompt_template),
    }
    work_identity_path = packet_dir / "machine_prelabel_work_identity.json"
    if work_identity_path.is_file():
        observed_identity = json.loads(work_identity_path.read_text(encoding="utf-8"))
        if observed_identity != identity:
            raise ValueError("machine prelabel checkpoint belongs to a different runtime")
    else:
        write_json(work_identity_path, identity)
    checkpoint_path = packet_dir / "machine_prelabel_checkpoint.jsonl"
    checkpoint_rows = read_jsonl(checkpoint_path) if checkpoint_path.is_file() else []
    completed: dict[str, dict[str, Any]] = {}
    for row in checkpoint_rows:
        sample_id = str(row.get("sample_id", ""))
        if sample_id not in items or sample_id in completed:
            raise ValueError("machine prelabel checkpoint has invalid IDs")
        if row.get("context_sha256") != items[sample_id]["context_sha256"]:
            raise ValueError(f"{sample_id}: machine checkpoint context changed")
        validate_annotation(row.get("annotation"), sample_id=sample_id)
        _validate_machine_attempts(row, items[sample_id], sample_id=sample_id)
        completed[sample_id] = row
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with checkpoint_path.open("a", encoding="utf-8") as handle:
            for sample_id in sorted(items):
                if sample_id in completed:
                    continue
                item = items[sample_id]
                prompt = _prelabel_prompt(item)
                attempts: list[dict[str, Any]] = []
                annotation: dict[str, Any] | None = None
                for attempt_number in range(1, MACHINE_PRELABEL_MAX_ATTEMPTS + 1):
                    print(f"machine_prelabel: start {sample_id} attempt={attempt_number}")
                    response = generator.complete(
                        prompt,
                        system_prompt=str(prompt_template["system_prompt"]),
                        temperature=0.0,
                        max_tokens=500,
                    ).strip()
                    attempt = {
                        "attempt": attempt_number,
                        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                        "raw_response": response,
                        "raw_response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
                    }
                    try:
                        annotation = _parse_machine_response(response, sample_id=sample_id)
                    except ValueError as exc:
                        error = str(exc)
                        attempt.update({"valid": False, "validation_error": error})
                        attempts.append(attempt)
                        print(
                            f"machine_prelabel: invalid {sample_id} "
                            f"attempt={attempt_number}: {error}"
                        )
                        if attempt_number == MACHINE_PRELABEL_MAX_ATTEMPTS:
                            raise ValueError(
                                f"{sample_id}: machine prelabel invalid after "
                                f"{MACHINE_PRELABEL_MAX_ATTEMPTS} attempts"
                            ) from exc
                        prompt = _prelabel_retry_prompt(
                            item,
                            previous_response=response,
                            validation_error=error,
                        )
                    else:
                        attempt.update({"valid": True, "validation_error": None})
                        attempts.append(attempt)
                        break
                if annotation is None:
                    raise ValueError(f"{sample_id}: machine prelabel produced no annotation")
                final_attempt = attempts[-1]
                row = {
                    "sample_id": sample_id,
                    "context_sha256": item["context_sha256"],
                    "annotation": annotation,
                    "raw_response": final_attempt["raw_response"],
                    "raw_response_sha256": final_attempt["raw_response_sha256"],
                    "prompt_sha256": final_attempt["prompt_sha256"],
                    "attempts": attempts,
                }
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
                completed[sample_id] = row
                print(f"machine_prelabel: completed {sample_id} attempts={len(attempts)}")
    finally:
        release_generator(generator)
    if set(completed) != set(items):
        raise ValueError("machine prelabeling did not complete all samples")
    identity_sha = _stable_sha(identity)
    installed = [
        {
            "sample_id": sample_id,
            "context_sha256": items[sample_id]["context_sha256"],
            "annotation": completed[sample_id]["annotation"],
            "role": "machine_prelabel",
            "machine_identity_sha256": identity_sha,
            "raw_response": completed[sample_id]["raw_response"],
            "raw_response_sha256": completed[sample_id]["raw_response_sha256"],
            "prompt_sha256": completed[sample_id]["prompt_sha256"],
            "attempts": completed[sample_id].get("attempts", []),
        }
        for sample_id in sorted(completed)
    ]
    write_jsonl(target, installed)
    write_json(target_identity, identity)
    result = {
        "schema_version": "far-type-mappability-machine-prelabel-v1",
        "samples": len(installed),
        "prelabels_sha256": sha256_file(target),
        "identity_sha256": sha256_file(target_identity),
        "installed_sha256": sha256_file(target),
        "installed_identity_sha256": sha256_file(target_identity),
    }
    write_json(packet_dir / "completed" / "machine_install.json", result)
    return result


def _agreement(
    left: dict[str, dict[str, Any]],
    right: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    ids = sorted(left)
    if set(ids) != set(right):
        raise ValueError("agreement inputs have different sample sets")
    left_labels = [str(left[sample_id]["mappability"]) for sample_id in ids]
    right_labels = [str(right[sample_id]["mappability"]) for sample_id in ids]
    type_kappas = {
        name: cohen_kappa(
            [str(name in left[sample_id]["mapped_types"]) for sample_id in ids],
            [str(name in right[sample_id]["mapped_types"]) for sample_id in ids],
        )
        for name in TYPE_NAMES
    }
    agreements = sum(
        left_label == right_label
        for left_label, right_label in zip(left_labels, right_labels, strict=True)
    )
    return {
        "samples": len(ids),
        "mappability_kappa": cohen_kappa(left_labels, right_labels),
        "mappability_raw_agreement": agreements / len(ids),
        "mappability_disagreements": len(ids) - agreements,
        "mapped_type_kappas": type_kappas,
        "mapped_type_macro_kappa": mean(type_kappas.values()),
    }


def _score_deltas(items: dict[str, dict[str, Any]]) -> dict[str, float]:
    deltas: dict[str, float] = {}
    for dataset in DATASET_ORDER:
        spec = DATASETS[dataset]
        typed_rows = read_jsonl(Path(spec["typed_scores"]))
        untyped_rows = read_jsonl(Path(spec["untyped_scores"]))
        typed = {str(row.get("sample_id")): row for row in typed_rows}
        untyped = {str(row.get("sample_id")): row for row in untyped_rows}
        if len(typed_rows) != 150 or len(untyped_rows) != 150 or set(typed) != set(untyped):
            raise ValueError(f"{dataset}: score pairs are incomplete")
        selected_ids = {
            sample_id for sample_id, item in items.items() if item["dataset"] == dataset
        }
        if not selected_ids <= set(typed):
            raise ValueError(f"{dataset}: scores do not cover selected annotations")
        for sample_id in selected_ids:
            deltas[sample_id] = float(typed[sample_id]["boundary_score"]) - float(
                untyped[sample_id]["boundary_score"]
            )
    if set(deltas) != set(items):
        raise ValueError("score deltas do not align to all annotation items")
    return deltas


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires values")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _bootstrap_mean(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"estimate": None, "lower": None, "upper": None, "samples": 0}
    rng = random.Random(BOOTSTRAP_SEED)
    bootstrapped = [mean(rng.choice(values) for _ in values) for _ in range(BOOTSTRAP_RESAMPLES)]
    return {
        "estimate": mean(values),
        "lower": _percentile(bootstrapped, 0.025),
        "upper": _percentile(bootstrapped, 0.975),
        "samples": len(values),
        "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED,
        "method": "sample-percentile-bootstrap-v1",
    }


def _mapping_weight(label: str) -> float:
    return {"clean": 1.0, "partial": 0.5, "unmappable": 0.0}[label]


def _group_summary(
    ids: list[str],
    annotations: dict[str, dict[str, Any]],
    deltas: dict[str, float],
) -> dict[str, Any]:
    counts = {
        label: sum(annotations[sample_id]["mappability"] == label for sample_id in ids)
        for label in MAPPABILITY_LABELS
    }
    return {
        "samples": len(ids),
        "counts": counts,
        "mapped_type_counts": {
            name: sum(name in annotations[sample_id]["mapped_types"] for sample_id in ids)
            for name in TYPE_NAMES
        },
        "proportions": {label: counts[label] / len(ids) for label in MAPPABILITY_LABELS},
        "strict_mappability_rate": counts["clean"] / len(ids),
        "broad_mappability_rate": (counts["clean"] + counts["partial"]) / len(ids),
        "weighted_mappability": mean(
            _mapping_weight(str(annotations[sample_id]["mappability"])) for sample_id in ids
        ),
        "delta_by_mappability": {
            label: _bootstrap_mean(
                [
                    deltas[sample_id]
                    for sample_id in ids
                    if annotations[sample_id]["mappability"] == label
                ]
            )
            for label in MAPPABILITY_LABELS
        },
    }


def _average_ranks(values: list[float]) -> list[float]:
    ordered = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        average_rank = (start + 1 + end) / 2.0
        for position in range(start, end):
            ranks[ordered[position]] = average_rank
        start = end
    return ranks


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("correlation requires aligned values")
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_scale = sum((value - left_mean) ** 2 for value in left)
    right_scale = sum((value - right_mean) ** 2 for value in right)
    if left_scale == 0.0 or right_scale == 0.0:
        return None
    return numerator / math.sqrt(left_scale * right_scale)


def _association(rows: list[dict[str, Any]]) -> dict[str, Any]:
    x = [float(row["weighted_mappability"]) for row in rows]
    y = [float(row["mean_delta"]) for row in rows]
    x_mean = mean(x)
    y_mean = mean(y)
    denominator = sum((value - x_mean) ** 2 for value in x)
    if denominator == 0.0:
        slope: float | None = None
        intercept: float | None = None
        r_squared: float | None = None
    else:
        slope = (
            sum((left - x_mean) * (right - y_mean) for left, right in zip(x, y, strict=True))
            / denominator
        )
        intercept = y_mean - slope * x_mean
        residual = sum(
            (right - (intercept + slope * left)) ** 2 for left, right in zip(x, y, strict=True)
        )
        total = sum((right - y_mean) ** 2 for right in y)
        r_squared = 1.0 if total == 0.0 and residual == 0.0 else (1.0 - residual / total)
    return {
        "units": len(rows),
        "spearman_rho": _pearson(_average_ranks(x), _average_ranks(y)),
        "ols_slope": slope,
        "ols_intercept": intercept,
        "ols_r_squared": r_squared,
        "confirmatory_p_value": None,
        "interpretation": "retrospective_descriptive_association",
    }


def _stratum_key(item: dict[str, Any]) -> str:
    strata = dict(item["analysis_strata"])
    if item["dataset"] == "wikicontradict":
        projected = {
            "reasoning": strata["reasoning"],
            "source_relation": strata["source_relation"],
        }
    else:
        projected = {"upstream_conflict_type": strata["upstream_conflict_type"]}
    return f"{item['dataset']}:{json.dumps(projected, sort_keys=True)}"


def compute_result(packet_dir: Path) -> dict[str, Any]:
    status = packet_status(packet_dir)
    if status.get("ready_to_analyze") is not True:
        raise ValueError(f"type-mappability packet is not ready: {status.get('errors', [])}")
    manifest, items = _annotation_items(packet_dir)
    reviewer_a_id, reviewer_a = _load_installed(packet_dir, items, "reviewer_a")
    reviewer_b_id, reviewer_b = _load_installed(packet_dir, items, "reviewer_b")
    adjudicator_id, adjudicated = _load_installed(packet_dir, items, "adjudicator")
    machine_identity, machine = _load_machine(packet_dir, items)
    human_ids = {reviewer_a_id, reviewer_b_id, adjudicator_id}
    if len(human_ids) != 3:
        raise ValueError("two reviewers and the adjudicator require distinct IDs")
    deltas = _score_deltas(items)
    ordered_ids = sorted(items)
    by_dataset = {
        dataset: _group_summary(
            [sample_id for sample_id in ordered_ids if items[sample_id]["dataset"] == dataset],
            adjudicated,
            deltas,
        )
        for dataset in DATASET_ORDER
    }
    combined = _group_summary(ordered_ids, adjudicated, deltas)
    grouped: dict[str, list[str]] = defaultdict(list)
    for sample_id in ordered_ids:
        grouped[_stratum_key(items[sample_id])].append(sample_id)
    strata = [
        {
            "stratum": key,
            "samples": len(ids),
            "weighted_mappability": mean(
                _mapping_weight(str(adjudicated[sample_id]["mappability"])) for sample_id in ids
            ),
            "mean_delta": mean(deltas[sample_id] for sample_id in ids),
        }
        for key, ids in sorted(grouped.items())
    ]
    if len(strata) != 6:
        raise ValueError(f"expected six frozen WS3 conflict strata, observed {len(strata)}")
    result: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA,
        "protocol_sha256": PROTOCOL_SHA256,
        "packet_manifest_sha256": sha256_file(packet_dir / "packet_manifest.json"),
        "samples": len(items),
        "dataset_counts": dict(manifest["dataset_counts"]),
        "agreement": {
            "human_human": {
                "annotators": [reviewer_a_id, reviewer_b_id],
                **_agreement(reviewer_a, reviewer_b),
            },
            "model_adjudicated": {
                "machine_identity": machine_identity,
                **_agreement(machine, adjudicated),
            },
            "adjudicator_id": adjudicator_id,
            "identity_independence_self_attested_only": True,
        },
        "by_dataset": by_dataset,
        "combined": combined,
        "strata": strata,
        "association": _association(strata),
        "annotation_files": {
            role: sha256_file(_completed_path(packet_dir, role)) for role in HUMAN_ROLES
        },
        "machine_prelabels_sha256": sha256_file(_completed_path(packet_dir, "machine_prelabels")),
        "machine_identity_sha256": sha256_file(packet_dir / "completed" / "machine_identity.json"),
        "input_audit": verify_protocol_inputs(),
        "misinformation_n5_warning": True,
        "human_annotations_complete": True,
        "human_iaa_computed": True,
        "human_identity_verified": False,
        "retrospective": True,
        "confirmatory_h4": False,
        "causal_analysis": False,
        "publication_gold": False,
        "test_accessed": False,
    }
    if result["input_audit"]["valid"] is not True:
        raise ValueError("type-mappability source inputs changed before analysis")
    return result


def _format_number(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}"


def report_text(result: dict[str, Any]) -> str:
    human = result["agreement"]["human_human"]
    machine = result["agreement"]["model_adjudicated"]
    lines = [
        "# FAR 类型可映射性回顾性分析 (P6)",
        "",
        "> WS3 结果早于 H4 冻结；本报告是 retrospective mechanism analysis，"
        "不确认 H4、因果中介或外部泛化。",
        "",
        "## 标注一致性",
        "",
        f"- Human-human mappability Cohen's kappa: `{_format_number(human['mappability_kappa'])}`",
        f"- Human-human raw agreement: `{_format_number(human['mappability_raw_agreement'])}`",
        f"- Human-human mapped-type macro kappa: "
        f"`{_format_number(human['mapped_type_macro_kappa'])}`",
        f"- Model-adjudicated mappability kappa: `{_format_number(machine['mappability_kappa'])}`",
        "- Reviewer/adjudicator IDs are self-attested identifiers, not independently "
        "verified identities.",
        "",
        "## 数据集可映射性",
        "",
        "| 数据集 | n | clean | partial | unmappable | strict | broad | weighted |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for dataset in DATASET_ORDER:
        row = result["by_dataset"][dataset]
        counts = row["counts"]
        lines.append(
            f"| {dataset} | {row['samples']} | {counts['clean']} | {counts['partial']} | "
            f"{counts['unmappable']} | {row['strict_mappability_rate']:.4f} | "
            f"{row['broad_mappability_rate']:.4f} | {row['weighted_mappability']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Adjudicated mapped-type distribution",
            "",
            "| Type | wikicontradict | rag_conflicts | combined |",
            "|---|---:|---:|---:|",
        ]
    )
    for name in TYPE_NAMES:
        lines.append(
            f"| {name} | {result['by_dataset']['wikicontradict']['mapped_type_counts'][name]} | "
            f"{result['by_dataset']['rag_conflicts']['mapped_type_counts'][name]} | "
            f"{result['combined']['mapped_type_counts'][name]} |"
        )
    lines.extend(
        [
            "",
            "## Adjudicated mappability x typed-untyped delta",
            "",
            "| 范围 | 档位 | n | mean delta | 95% sample-bootstrap CI |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for scope in (*DATASET_ORDER, "combined"):
        row = result["combined"] if scope == "combined" else result["by_dataset"][scope]
        for label in MAPPABILITY_LABELS:
            delta = row["delta_by_mappability"][label]
            lines.append(
                f"| {scope} | {label} | {delta['samples']} | "
                f"{_format_number(delta['estimate'])} | "
                f"[{_format_number(delta['lower'])}, {_format_number(delta['upper'])}] |"
            )
    association = result["association"]
    lines.extend(
        [
            "",
            "## 六个冻结 strata 的描述性 association",
            "",
            f"Spearman rho = `{_format_number(association['spearman_rho'])}`；"
            f"OLS slope = `{_format_number(association['ols_slope'])}`；"
            f"R² = `{_format_number(association['ols_r_squared'])}`。",
            "",
            "不报告确认性 p-value。Google misinformation 仅 n=5；null、正方向或负方向"
            "都不能升级为普遍结论。",
            "",
        ]
    )
    return "\n".join(lines)


def _prepare_report_dir(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("type-mappability report directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)


def analyze(packet_dir: Path, output_dir: Path) -> dict[str, Any]:
    _prepare_report_dir(output_dir)
    result = compute_result(packet_dir)
    write_json(output_dir / "type_mappability.json", result)
    (output_dir / "type_mappability.md").write_text(
        report_text(result),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "far-type-mappability-report-manifest-v1",
        "protocol_sha256": PROTOCOL_SHA256,
        "result_sha256": sha256_file(output_dir / "type_mappability.json"),
        "report_sha256": sha256_file(output_dir / "type_mappability.md"),
        "retrospective": True,
        "confirmatory_h4": False,
        "human_iaa_computed": True,
        "human_identity_verified": False,
        "publication_gold": False,
        "test_accessed": False,
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def verify_report(packet_dir: Path, report_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        expected = compute_result(packet_dir)
        observed = json.loads((report_dir / "type_mappability.json").read_text(encoding="utf-8"))
        expected_text = report_text(expected)
        observed_text = (report_dir / "type_mappability.md").read_text(encoding="utf-8")
        manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
        if observed != expected:
            errors.append("type-mappability JSON differs from deterministic recomputation")
        if observed_text != expected_text:
            errors.append("type-mappability Markdown differs from deterministic recomputation")
        if manifest.get("protocol_sha256") != PROTOCOL_SHA256:
            errors.append("type-mappability report protocol fingerprint mismatch")
        if manifest.get("result_sha256") != sha256_file(report_dir / "type_mappability.json"):
            errors.append("type-mappability result fingerprint mismatch")
        if manifest.get("report_sha256") != sha256_file(report_dir / "type_mappability.md"):
            errors.append("type-mappability Markdown fingerprint mismatch")
        for field, expected_value in (
            ("retrospective", True),
            ("confirmatory_h4", False),
            ("human_iaa_computed", True),
            ("human_identity_verified", False),
            ("publication_gold", False),
            ("test_accessed", False),
        ):
            if manifest.get(field) is not expected_value:
                errors.append(f"type-mappability manifest has invalid {field}")
    except (AttributeError, FileNotFoundError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "far-type-mappability-report-audit-v1",
        "valid": not errors,
        "errors": errors,
        "retrospective": True,
        "confirmatory_h4": False,
        "human_iaa_computed": not errors,
        "human_identity_verified": False,
        "publication_gold": False,
        "test_accessed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument("--overwrite", action="store_true")
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--packet-dir", type=Path, required=True)
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--packet-dir", type=Path, required=True)
    install_parser.add_argument("--input", type=Path, required=True)
    install_parser.add_argument("--role", choices=HUMAN_ROLES, required=True)
    install_parser.add_argument("--annotator-id", required=True)
    install_machine_parser = subparsers.add_parser("install-machine")
    install_machine_parser.add_argument("--packet-dir", type=Path, required=True)
    install_machine_parser.add_argument("--input", type=Path, required=True)
    install_machine_parser.add_argument("--identity", type=Path, required=True)
    prelabel_parser = subparsers.add_parser("prelabel")
    prelabel_parser.add_argument("--packet-dir", type=Path, required=True)
    prelabel_parser.add_argument(
        "--config",
        type=Path,
        default=experiment_config_dir() / "qwen_boundary.yaml",
    )
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--packet-dir", type=Path, required=True)
    analyze_parser.add_argument("--output-dir", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--packet-dir", type=Path, required=True)
    verify_parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_packet(args.output_dir, overwrite=args.overwrite)
    elif args.command == "status":
        result = packet_status(args.packet_dir)
    elif args.command == "install":
        result = install_human_annotations(
            args.packet_dir,
            args.input,
            role=args.role,
            annotator_id=args.annotator_id,
        )
    elif args.command == "install-machine":
        result = install_machine_prelabels(args.packet_dir, args.input, args.identity)
    elif args.command == "prelabel":
        result = prelabel_packet(args.packet_dir, args.config)
    elif args.command == "analyze":
        result = analyze(args.packet_dir, args.output_dir)
    else:
        result = verify_report(args.packet_dir, args.report_dir)
        if result["valid"] is not True:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
