"""Blind double-annotation, adjudication, and inter-annotator agreement tools."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

from far.bench.build.common import read_jsonl, sha256_file, stable_rank, write_json, write_jsonl
from far.bench.schema import VALID_CONFLICT_TYPES, VALID_REVISION_ACTIONS

PACKET_VERSION = "falsirag-annotation-packet-v1"
_REVIEW_VISIBLE_FIELDS = (
    "schema_version",
    "sample_id",
    "question",
    "initial_answer",
    "claims",
    "evidence",
    "annotator_id",
)
_ADJUDICATION_VISIBLE_FIELDS = _REVIEW_VISIBLE_FIELDS[:-1]
_REVIEW_HANDOFF_FIELDS = {*_REVIEW_VISIBLE_FIELDS, "annotation"}


def _validate_annotator_id(value: str) -> str:
    if not value or not value.replace("-", "").replace("_", "").isalnum():
        raise ValueError("annotator IDs may contain only letters, digits, hyphens, and underscores")
    return value


def _visible_row(
    sample: dict[str, Any],
    corpus: dict[str, dict[str, Any]],
    annotator_id: str,
) -> dict[str, Any]:
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for evidence in (*sample["gold_evidence"], *sample["counter_evidence"]):
        document = corpus[evidence["doc_id"]]
        evidence_by_id[evidence["evidence_id"]] = {
            "evidence_id": evidence["evidence_id"],
            "title": document["title"],
            "source": document["source"],
            "date": document.get("date"),
            "text": evidence["text_span"],
        }
    ordered_evidence = sorted(
        evidence_by_id.values(),
        key=lambda row: stable_rank(1729, annotator_id, sample["id"], row["evidence_id"]),
    )
    evidence = []
    for index, row in enumerate(ordered_evidence):
        visible = dict(row)
        visible["evidence_id"] = f"EVIDENCE_{chr(ord('A') + index)}"
        evidence.append(visible)
    return {
        "schema_version": PACKET_VERSION,
        "sample_id": sample["id"],
        "question": sample["question"],
        "initial_answer": sample["initial_answer"],
        "claims": [
            {"claim_id": claim["claim_id"], "claim": claim["claim"]} for claim in sample["claims"]
        ],
        "evidence": evidence,
        "annotator_id": annotator_id,
        "annotation": {
            "conflict_present": None,
            "conflict_type": "",
            "revision_action": "",
            "revised_answer_acceptable": None,
            "rationale": "",
        },
    }


def build_annotation_packet(
    data_dir: Path,
    output_dir: Path,
    annotator_ids: list[str],
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    if len(annotator_ids) < 2:
        raise ValueError("at least two independent annotators are required")
    annotator_ids = [_validate_annotator_id(value) for value in annotator_ids]
    if len(set(annotator_ids)) != len(annotator_ids):
        raise ValueError("annotator IDs must be unique")
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass overwrite=True to replace it")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    samples = read_jsonl(data_dir / "falsirag_bench.jsonl")
    corpus = {row["doc_id"]: row for row in read_jsonl(data_dir / "corpus.jsonl")}
    files: dict[str, str] = {}
    for annotator_id in annotator_ids:
        rows = [_visible_row(sample, corpus, annotator_id) for sample in samples]
        rows.sort(key=lambda row: stable_rank(1729, annotator_id, row["sample_id"]))
        filename = f"annotations_{annotator_id}.jsonl"
        write_jsonl(output_dir / filename, rows)
        files[annotator_id] = filename
    adjudication_rows = []
    for sample in samples:
        row = _visible_row(sample, corpus, "adjudicator")
        row.pop("annotator_id")
        row["adjudicator_id"] = ""
        row["gold_annotation"] = row.pop("annotation")
        row["gold_annotation"]["revised_answer"] = ""
        adjudication_rows.append(row)
    write_jsonl(output_dir / "adjudications.jsonl", adjudication_rows)
    manifest = {
        "schema_version": PACKET_VERSION,
        "source_fingerprints": {
            "benchmark_sha256": sha256_file(data_dir / "falsirag_bench.jsonl"),
            "corpus_sha256": sha256_file(data_dir / "corpus.jsonl"),
        },
        "samples": len(samples),
        "annotator_ids": annotator_ids,
        "annotation_files": files,
        "adjudication_file": "adjudications.jsonl",
        "blind_fields_omitted": [
            "category",
            "split",
            "conflict_type",
            "expected_revision",
            "source_metadata",
            "annotation_status",
            "evidence roles",
        ],
    }
    write_json(output_dir / "packet_manifest.json", manifest)
    (output_dir / "README.md").write_text(
        "# FalsiRAG annotation packet\n\n"
        "Annotators must work independently. Fill every `annotation` field without consulting "
        "machine seeds or another annotator. The adjudicator completes `gold_annotation` only "
        "after both annotation files are frozen. Conflict types and revision actions follow "
        "`bench/schema.py`.\n",
        encoding="utf-8",
    )
    return manifest


def cohen_kappa(left: list[str], right: list[str]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("kappa requires non-empty aligned labels")
    observed = sum(a == b for a, b in zip(left, right, strict=True)) / len(left)
    left_counts = Counter(left)
    right_counts = Counter(right)
    labels = set(left_counts) | set(right_counts)
    expected = sum(
        (left_counts[label] / len(left)) * (right_counts[label] / len(right)) for label in labels
    )
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def _agreement_summary(
    by_annotator: dict[str, dict[str, dict[str, Any]]],
    sample_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    pair_reports: list[dict[str, Any]] = []
    for left_id, right_id in combinations(sorted(by_annotator), 2):
        ordered_ids = sorted(sample_ids)
        left = by_annotator[left_id]
        right = by_annotator[right_id]
        pair_reports.append(
            {
                "annotators": [left_id, right_id],
                "conflict_presence_kappa": cohen_kappa(
                    [str(left[item]["conflict_present"]) for item in ordered_ids],
                    [str(right[item]["conflict_present"]) for item in ordered_ids],
                ),
                "conflict_type_kappa": cohen_kappa(
                    [str(left[item]["conflict_type"]) for item in ordered_ids],
                    [str(right[item]["conflict_type"]) for item in ordered_ids],
                ),
                "revision_action_kappa": cohen_kappa(
                    [str(left[item]["revision_action"]) for item in ordered_ids],
                    [str(right[item]["revision_action"]) for item in ordered_ids],
                ),
            }
        )
    mean_kappas = {
        key: sum(float(report[key]) for report in pair_reports) / len(pair_reports)
        for key in (
            "conflict_presence_kappa",
            "conflict_type_kappa",
            "revision_action_kappa",
        )
    }
    return pair_reports, mean_kappas


def _validated_annotation(row: dict[str, Any], field: str) -> dict[str, Any]:
    if row.get("draft_from_machine_preannotation") and not row.get("human_reviewed"):
        raise ValueError(
            f"{row.get('sample_id')}: machine preannotation drafts require human_reviewed=true"
        )
    annotation = row.get(field)
    if not isinstance(annotation, dict):
        raise ValueError(f"{row.get('sample_id')}: missing {field}")
    present = annotation.get("conflict_present")
    if not isinstance(present, bool):
        raise ValueError(f"{row.get('sample_id')}: conflict_present must be boolean")
    conflict_type = annotation.get("conflict_type")
    if present and conflict_type not in VALID_CONFLICT_TYPES:
        raise ValueError(f"{row.get('sample_id')}: invalid conflict type")
    if not present:
        conflict_type = "no_conflict"
    action = annotation.get("revision_action")
    if action not in VALID_REVISION_ACTIONS:
        raise ValueError(f"{row.get('sample_id')}: invalid revision action")
    acceptable = annotation.get("revised_answer_acceptable")
    if not isinstance(acceptable, bool):
        raise ValueError(f"{row.get('sample_id')}: revised_answer_acceptable must be boolean")
    rationale = annotation.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError(f"{row.get('sample_id')}: rationale must be non-empty")
    return {**annotation, "conflict_type": conflict_type, "rationale": rationale.strip()}


def _packet_file(packet_dir: Path, filename: str) -> Path:
    path = (packet_dir / filename).resolve()
    try:
        path.relative_to(packet_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"annotation packet file escapes packet directory: {filename}") from exc
    if not path.is_file():
        raise FileNotFoundError(f"annotation packet file is missing: {filename}")
    return path


def _rows_by_id(
    rows: list[dict[str, Any]], *, expected: int, role: str
) -> dict[str, dict[str, Any]]:
    sample_ids = [str(row.get("sample_id", "")) for row in rows]
    if len(rows) != expected:
        raise ValueError(f"{role} file has {len(rows)} rows; expected {expected}")
    if any(not sample_id for sample_id in sample_ids):
        raise ValueError(f"{role} file contains a row without sample_id")
    if len(set(sample_ids)) != len(sample_ids):
        raise ValueError(f"{role} file contains duplicate sample IDs")
    return dict(zip(sample_ids, rows, strict=True))


def _assert_visible_unchanged(
    row: dict[str, Any],
    expected: dict[str, Any],
    fields: tuple[str, ...],
    *,
    role: str,
) -> None:
    changed = [field for field in fields if row.get(field) != expected.get(field)]
    if changed:
        raise ValueError(f"{row.get('sample_id')}: {role} modified blind packet fields: {changed}")


def install_review_file(
    packet_dir: Path,
    review_file: Path,
    *,
    reviewer_id: str,
) -> dict[str, Any]:
    """Install one completed reviewer file without replacing other packet artifacts."""

    reviewer_id = _validate_annotator_id(reviewer_id)
    manifest = json.loads((packet_dir / "packet_manifest.json").read_text(encoding="utf-8"))
    annotation_files = manifest.get("annotation_files", {})
    if reviewer_id not in annotation_files:
        raise ValueError(f"reviewer is not declared by this packet: {reviewer_id}")
    target = _packet_file(packet_dir, str(annotation_files[reviewer_id]))
    template_rows = _rows_by_id(
        read_jsonl(target), expected=int(manifest["samples"]), role=f"{reviewer_id} template"
    )
    if any(
        row.get("annotation", {}).get("conflict_present") is not None
        for row in template_rows.values()
    ):
        raise FileExistsError(f"reviewer file is already completed: {target.name}")
    imported_rows = _rows_by_id(
        read_jsonl(review_file),
        expected=int(manifest["samples"]),
        role=f"{reviewer_id} import",
    )
    if set(imported_rows) != set(template_rows):
        raise ValueError("imported reviewer file has a different sample set")
    for sample_id, row in imported_rows.items():
        _assert_visible_unchanged(
            row,
            template_rows[sample_id],
            _REVIEW_VISIBLE_FIELDS,
            role=reviewer_id,
        )
        _validated_annotation(row, "annotation")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=packet_dir)
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        shutil.copy2(review_file, temporary_path)
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)
    return {
        "schema_version": "falsirag-installed-review-v1",
        "reviewer_id": reviewer_id,
        "samples": len(imported_rows),
        "source_review_sha256": sha256_file(review_file),
        "installed_file": target.name,
        "installed_sha256": sha256_file(target),
    }


def build_reviewer_handoff(
    packet_dir: Path,
    output_dir: Path,
    *,
    reviewer_id: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Build a minimal, reviewer-specific handoff directory and ZIP archive."""

    reviewer_id = _validate_annotator_id(reviewer_id)
    manifest_path = packet_dir / "packet_manifest.json"
    packet_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    annotation_files = packet_manifest.get("annotation_files", {})
    if reviewer_id not in annotation_files:
        raise ValueError(f"reviewer is not declared by this packet: {reviewer_id}")
    source = _packet_file(packet_dir, str(annotation_files[reviewer_id]))
    rows = _rows_by_id(
        read_jsonl(source),
        expected=int(packet_manifest["samples"]),
        role=f"{reviewer_id} handoff",
    )
    for sample_id, row in rows.items():
        extra_fields = sorted(set(row) - _REVIEW_HANDOFF_FIELDS)
        if extra_fields:
            raise ValueError(f"{sample_id}: reviewer handoff row contains extra fields")
        if row.get("annotator_id") != reviewer_id:
            raise ValueError(f"{sample_id}: reviewer handoff row belongs to another reviewer")
        annotation = row.get("annotation")
        if not isinstance(annotation, dict):
            raise ValueError(f"{sample_id}: reviewer handoff row is missing annotation object")
        if annotation.get("conflict_present") is not None:
            raise ValueError("reviewer handoff can only be built from a blank reviewer template")
        if (
            any(
                str(annotation.get(field, "")).strip()
                for field in ("conflict_type", "revision_action", "rationale")
            )
            or annotation.get("revised_answer_acceptable") is not None
        ):
            raise ValueError("reviewer handoff can only be built from a blank reviewer template")

    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass overwrite=True to replace it")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    annotation_name = source.name
    destination = output_dir / annotation_name
    shutil.copy2(source, destination)
    copied_files = [annotation_name]
    packet_readme = packet_dir / "README.md"
    if packet_readme.is_file():
        shutil.copy2(packet_readme, output_dir / "PACKET_README.md")
        copied_files.append("PACKET_README.md")
    instructions = (
        f"# FalsiRAG reviewer handoff: {reviewer_id}\n\n"
        "You received a reviewer-specific blind packet. Work independently. Do not "
        "search the web, inspect benchmark gold/source files, use machine "
        "preannotations, or consult another reviewer.\n\n"
        f"Fill every `annotation` object in `{annotation_name}`. Each rationale must "
        "cite visible evidence IDs such as `EVIDENCE_A`. Return only the completed "
        "JSONL file to the annotation owner.\n\n"
        "The annotation owner will install the returned file with "
        "`python -m far.bench.build.annotate_packet install-review` and will verify "
        "packet fingerprints before adjudication.\n"
    )
    (output_dir / "REVIEWER_INSTRUCTIONS.md").write_text(instructions, encoding="utf-8")
    copied_files.append("REVIEWER_INSTRUCTIONS.md")

    file_hashes = {relative: sha256_file(output_dir / relative) for relative in copied_files}
    result = {
        "schema_version": "falsirag-reviewer-handoff-v1",
        "reviewer_id": reviewer_id,
        "samples": len(rows),
        "source_packet_sha256": sha256_file(manifest_path),
        "source_annotation_file_sha256": sha256_file(source),
        "files": file_hashes,
        "archive_file": f"{output_dir.name}.zip",
        "archive_sha256": "",
        "safety": {
            "single_reviewer_only": True,
            "blank_template_only": True,
            "machine_predictions_included": False,
            "other_reviewer_files_included": False,
            "packet_manifest_included": False,
        },
    }
    manifest_destination = output_dir / "handoff_manifest.json"
    write_json(manifest_destination, result)
    copied_files.append("handoff_manifest.json")

    archive_path = output_dir.parent / f"{output_dir.name}.zip"
    if archive_path.exists():
        if not overwrite:
            raise FileExistsError(f"{archive_path} exists; pass overwrite=True to replace it")
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(copied_files):
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (output_dir / relative).read_bytes())
    result["archive_sha256"] = sha256_file(archive_path)
    write_json(manifest_destination, result)
    return result


def install_adjudication_file(
    packet_dir: Path,
    adjudication_file: Path,
    *,
    adjudicator_id: str | None = None,
) -> dict[str, Any]:
    """Install one completed adjudication file without replacing frozen evidence."""

    if adjudicator_id is not None:
        adjudicator_id = _validate_annotator_id(adjudicator_id)
    manifest = json.loads((packet_dir / "packet_manifest.json").read_text(encoding="utf-8"))
    target = _packet_file(packet_dir, str(manifest["adjudication_file"]))
    template_rows = _rows_by_id(
        read_jsonl(target), expected=int(manifest["samples"]), role="adjudication template"
    )
    if any(
        row.get("gold_annotation", {}).get("conflict_present") is not None
        or str(row.get("adjudicator_id", "")).strip()
        for row in template_rows.values()
    ):
        raise FileExistsError(f"adjudication file is already completed: {target.name}")
    imported_rows = _rows_by_id(
        read_jsonl(adjudication_file),
        expected=int(manifest["samples"]),
        role="adjudication import",
    )
    if set(imported_rows) != set(template_rows):
        raise ValueError("imported adjudication file has a different sample set")
    observed_adjudicator_ids: set[str] = set()
    for sample_id, row in imported_rows.items():
        _assert_visible_unchanged(
            row,
            template_rows[sample_id],
            _ADJUDICATION_VISIBLE_FIELDS,
            role="adjudicator",
        )
        row_adjudicator_id = str(row.get("adjudicator_id", "")).strip()
        if not row_adjudicator_id:
            raise ValueError(f"{sample_id}: adjudicator_id must be non-empty")
        observed_adjudicator_ids.add(row_adjudicator_id)
        gold = _validated_annotation(row, "gold_annotation")
        revised_answer = gold.get("revised_answer")
        if gold["conflict_present"] and (
            not isinstance(revised_answer, str) or not revised_answer.strip()
        ):
            raise ValueError(f"{sample_id}: conflicting adjudication requires revised_answer")
        if (
            not gold["conflict_present"]
            and isinstance(revised_answer, str)
            and revised_answer.strip()
        ):
            raise ValueError(f"{sample_id}: no-conflict adjudication must not set revised_answer")
    if len(observed_adjudicator_ids) != 1:
        raise ValueError("adjudication import requires one consistent adjudicator_id")
    observed_adjudicator_id = next(iter(observed_adjudicator_ids))
    if adjudicator_id is not None and observed_adjudicator_id != adjudicator_id:
        raise ValueError("adjudication import belongs to a different adjudicator")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=packet_dir)
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        shutil.copy2(adjudication_file, temporary_path)
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)
    return {
        "schema_version": "falsirag-installed-adjudication-v1",
        "adjudicator_id": observed_adjudicator_id,
        "samples": len(imported_rows),
        "source_adjudication_sha256": sha256_file(adjudication_file),
        "installed_file": target.name,
        "installed_sha256": sha256_file(target),
    }


def _field_status(
    rows: dict[str, dict[str, Any]],
    *,
    field: str,
    adjudication: bool = False,
) -> dict[str, Any]:
    completed = 0
    blank = 0
    invalid: list[dict[str, str]] = []
    conflict_positive = 0
    no_conflict_with_revised_answer = 0
    for sample_id, row in rows.items():
        annotation = row.get(field)
        if not isinstance(annotation, dict) or annotation.get("conflict_present") is None:
            blank += 1
            continue
        try:
            validated = _validated_annotation(row, field)
            if adjudication:
                revised_answer = validated.get("revised_answer")
                if validated["conflict_present"]:
                    conflict_positive += 1
                    if not isinstance(revised_answer, str) or not revised_answer.strip():
                        raise ValueError(
                            f"{sample_id}: conflicting adjudication requires revised_answer"
                        )
                elif isinstance(revised_answer, str) and revised_answer.strip():
                    no_conflict_with_revised_answer += 1
                    raise ValueError(
                        f"{sample_id}: no-conflict adjudication must not set revised_answer"
                    )
        except ValueError as exc:
            invalid.append({"sample_id": sample_id, "error": str(exc)})
            continue
        completed += 1
    return {
        "completed": completed,
        "blank": blank,
        "invalid": len(invalid),
        "invalid_preview": invalid[:10],
        "conflict_positive": conflict_positive if adjudication else None,
        "no_conflict_with_revised_answer": (
            no_conflict_with_revised_answer if adjudication else None
        ),
    }


def annotation_packet_status(packet_dir: Path, *, data_dir: Path | None = None) -> dict[str, Any]:
    """Summarize reviewer/adjudication packet progress without compiling it."""

    packet_manifest_path = packet_dir / "packet_manifest.json"
    packet_manifest = json.loads(packet_manifest_path.read_text(encoding="utf-8"))
    expected_count = int(packet_manifest["samples"])
    source_fingerprint_status: dict[str, Any] = {"checked": False}
    sample_by_id: dict[str, dict[str, Any]] = {}
    corpus: dict[str, dict[str, Any]] = {}
    if data_dir is not None:
        expected_fingerprints = {
            "benchmark_sha256": sha256_file(data_dir / "falsirag_bench.jsonl"),
            "corpus_sha256": sha256_file(data_dir / "corpus.jsonl"),
        }
        source_fingerprint_status = {
            "checked": True,
            "matches": packet_manifest.get("source_fingerprints") == expected_fingerprints,
            "packet": packet_manifest.get("source_fingerprints"),
            "data_dir": expected_fingerprints,
        }
        samples = read_jsonl(data_dir / "falsirag_bench.jsonl")
        sample_by_id = {str(row["id"]): row for row in samples}
        corpus = {row["doc_id"]: row for row in read_jsonl(data_dir / "corpus.jsonl")}

    reviewers: dict[str, dict[str, Any]] = {}
    reviewer_errors: list[str] = []
    annotation_files = packet_manifest.get("annotation_files", {})
    for reviewer_id, filename in sorted(annotation_files.items()):
        reviewer_status: dict[str, Any] = {
            "file": str(filename),
            "exists": False,
            "file_sha256": "",
            "rows": 0,
            "completed": 0,
            "blank": expected_count,
            "invalid": 0,
            "invalid_preview": [],
            "sample_set_matches": None,
            "visible_fields_match": None,
            "complete": False,
            "errors": [],
        }
        try:
            path = _packet_file(packet_dir, str(filename))
            reviewer_status["exists"] = True
            reviewer_status["file_sha256"] = sha256_file(path)
            rows_by_id = _rows_by_id(
                read_jsonl(path), expected=expected_count, role=str(reviewer_id)
            )
            reviewer_status["rows"] = len(rows_by_id)
            if sample_by_id:
                reviewer_status["sample_set_matches"] = set(rows_by_id) == set(sample_by_id)
                visible_errors = []
                for sample_id, row in rows_by_id.items():
                    if sample_id not in sample_by_id:
                        visible_errors.append(sample_id)
                        continue
                    expected = _visible_row(sample_by_id[sample_id], corpus, str(reviewer_id))
                    try:
                        _assert_visible_unchanged(
                            row,
                            expected,
                            _REVIEW_VISIBLE_FIELDS,
                            role=str(reviewer_id),
                        )
                    except ValueError:
                        visible_errors.append(sample_id)
                reviewer_status["visible_fields_match"] = not visible_errors
                reviewer_status["visible_field_mismatch_preview"] = visible_errors[:10]
            field_status = _field_status(rows_by_id, field="annotation")
            reviewer_status.update(
                {
                    "completed": field_status["completed"],
                    "blank": field_status["blank"],
                    "invalid": field_status["invalid"],
                    "invalid_preview": field_status["invalid_preview"],
                    "complete": (
                        field_status["completed"] == expected_count
                        and field_status["invalid"] == 0
                        and (
                            reviewer_status["sample_set_matches"] is not False
                            and reviewer_status["visible_fields_match"] is not False
                        )
                    ),
                }
            )
        except Exception as exc:
            message = str(exc)
            reviewer_status["errors"].append(message)
            reviewer_errors.append(f"{reviewer_id}: {message}")
        reviewers[str(reviewer_id)] = reviewer_status

    adjudication_status: dict[str, Any] = {
        "file": str(packet_manifest.get("adjudication_file", "")),
        "exists": False,
        "file_sha256": "",
        "rows": 0,
        "completed": 0,
        "blank": expected_count,
        "invalid": 0,
        "invalid_preview": [],
        "sample_set_matches": None,
        "visible_fields_match": None,
        "adjudicator_ids": [],
        "complete": False,
        "errors": [],
    }
    try:
        path = _packet_file(packet_dir, str(packet_manifest["adjudication_file"]))
        adjudication_status["exists"] = True
        adjudication_status["file_sha256"] = sha256_file(path)
        rows_by_id = _rows_by_id(read_jsonl(path), expected=expected_count, role="adjudication")
        adjudication_status["rows"] = len(rows_by_id)
        if sample_by_id:
            adjudication_status["sample_set_matches"] = set(rows_by_id) == set(sample_by_id)
            visible_errors = []
            for sample_id, row in rows_by_id.items():
                if sample_id not in sample_by_id:
                    visible_errors.append(sample_id)
                    continue
                expected = _visible_row(sample_by_id[sample_id], corpus, "adjudicator")
                expected.pop("annotator_id")
                try:
                    _assert_visible_unchanged(
                        row,
                        expected,
                        _ADJUDICATION_VISIBLE_FIELDS,
                        role="adjudicator",
                    )
                except ValueError:
                    visible_errors.append(sample_id)
            adjudication_status["visible_fields_match"] = not visible_errors
            adjudication_status["visible_field_mismatch_preview"] = visible_errors[:10]
        field_status = _field_status(rows_by_id, field="gold_annotation", adjudication=True)
        adjudicator_ids = sorted(
            {str(row.get("adjudicator_id", "")).strip() for row in rows_by_id.values()} - {""}
        )
        adjudication_status.update(
            {
                "completed": field_status["completed"],
                "blank": field_status["blank"],
                "invalid": field_status["invalid"],
                "invalid_preview": field_status["invalid_preview"],
                "conflict_positive": field_status["conflict_positive"],
                "no_conflict_with_revised_answer": field_status["no_conflict_with_revised_answer"],
                "adjudicator_ids": adjudicator_ids,
                "consistent_adjudicator_id": len(adjudicator_ids) == 1,
                "complete": (
                    field_status["completed"] == expected_count
                    and field_status["invalid"] == 0
                    and len(adjudicator_ids) == 1
                    and (
                        adjudication_status["sample_set_matches"] is not False
                        and adjudication_status["visible_fields_match"] is not False
                    )
                ),
            }
        )
    except Exception as exc:
        adjudication_status["errors"].append(str(exc))

    reviewers_complete = all(row["complete"] for row in reviewers.values()) and len(reviewers) >= 2
    source_matches = source_fingerprint_status.get("matches", True) is not False
    ready_to_export_adjudication_ui = reviewers_complete and source_matches
    ready_to_compile = (
        reviewers_complete
        and adjudication_status["complete"]
        and source_matches
        and not reviewer_errors
        and not adjudication_status["errors"]
    )
    next_steps = []
    if not reviewers_complete:
        next_steps.append("complete and install all reviewer annotation files")
    elif not adjudication_status["complete"]:
        next_steps.append("complete and install adjudications.jsonl")
    if source_fingerprint_status.get("matches") is False:
        next_steps.append("rebuild the packet from the current benchmark/corpus")
    if ready_to_compile:
        next_steps.append("run compile to freeze annotation evidence and compute kappa")

    return {
        "schema_version": "falsirag-annotation-packet-status-v1",
        "packet_dir": str(packet_dir),
        "packet_manifest_sha256": sha256_file(packet_manifest_path),
        "samples": expected_count,
        "source_fingerprints": source_fingerprint_status,
        "reviewers": reviewers,
        "reviewers_complete": reviewers_complete,
        "adjudication": adjudication_status,
        "ready_to_export_adjudication_label_studio": ready_to_export_adjudication_ui,
        "ready_to_compile": ready_to_compile,
        "next_steps": next_steps,
    }


def compile_annotations(
    data_dir: Path,
    packet_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    packet_manifest = json.loads((packet_dir / "packet_manifest.json").read_text(encoding="utf-8"))
    source_fingerprints = packet_manifest["source_fingerprints"]
    if source_fingerprints != {
        "benchmark_sha256": sha256_file(data_dir / "falsirag_bench.jsonl"),
        "corpus_sha256": sha256_file(data_dir / "corpus.jsonl"),
    }:
        raise ValueError("annotation packet does not match the current benchmark")
    annotator_ids = packet_manifest.get("annotator_ids")
    annotation_files = packet_manifest.get("annotation_files")
    if (
        not isinstance(annotator_ids, list)
        or len(set(map(str, annotator_ids))) < 2
        or not isinstance(annotation_files, dict)
        or set(map(str, annotator_ids)) != set(annotation_files)
    ):
        raise ValueError("packet must declare at least two matching unique annotation files")
    samples = read_jsonl(data_dir / "falsirag_bench.jsonl")
    corpus = {row["doc_id"]: row for row in read_jsonl(data_dir / "corpus.jsonl")}
    sample_by_id = {str(row["id"]): row for row in samples}
    expected_count = int(packet_manifest["samples"])
    by_annotator: dict[str, dict[str, dict[str, Any]]] = {}
    for annotator_id, filename in annotation_files.items():
        rows = _rows_by_id(
            read_jsonl(_packet_file(packet_dir, str(filename))),
            expected=expected_count,
            role=str(annotator_id),
        )
        if set(rows) != set(sample_by_id):
            raise ValueError(f"{annotator_id}: annotation sample set does not match benchmark")
        validated: dict[str, dict[str, Any]] = {}
        for sample_id, row in rows.items():
            expected = _visible_row(sample_by_id[sample_id], corpus, str(annotator_id))
            _assert_visible_unchanged(row, expected, _REVIEW_VISIBLE_FIELDS, role=str(annotator_id))
            validated[sample_id] = _validated_annotation(row, "annotation")
        by_annotator[str(annotator_id)] = validated
    sample_ids = set(sample_by_id)
    adjudication_rows = _rows_by_id(
        read_jsonl(_packet_file(packet_dir, str(packet_manifest["adjudication_file"]))),
        expected=expected_count,
        role="adjudication",
    )
    if set(adjudication_rows) != sample_ids:
        raise ValueError("adjudications are incomplete or contain unknown samples")
    adjudicator_ids = {
        str(row.get("adjudicator_id", "")).strip() for row in adjudication_rows.values()
    }
    if "" in adjudicator_ids or len(adjudicator_ids) != 1:
        raise ValueError("adjudication rows require one consistent non-empty adjudicator_id")
    adjudications: dict[str, dict[str, Any]] = {}
    for sample_id, row in adjudication_rows.items():
        expected = _visible_row(sample_by_id[sample_id], corpus, "adjudicator")
        expected.pop("annotator_id")
        _assert_visible_unchanged(row, expected, _ADJUDICATION_VISIBLE_FIELDS, role="adjudicator")
        gold = _validated_annotation(row, "gold_annotation")
        revised_answer = gold.get("revised_answer")
        if gold["conflict_present"] and (
            not isinstance(revised_answer, str) or not revised_answer.strip()
        ):
            raise ValueError(f"{sample_id}: conflicting adjudication requires revised_answer")
        if (
            not gold["conflict_present"]
            and isinstance(revised_answer, str)
            and revised_answer.strip()
        ):
            raise ValueError(f"{sample_id}: no-conflict adjudication must not set revised_answer")
        adjudications[sample_id] = gold

    pair_reports, mean_kappas = _agreement_summary(by_annotator, sample_ids)
    compiled = []
    for sample in samples:
        gold = adjudications[sample["id"]]
        sample["annotation_status"] = "adjudicated"
        sample["conflict_type"] = gold["conflict_type"]
        sample["expected_revision"]["action"] = gold["revision_action"]
        revised_answer = gold.get("revised_answer")
        sample["expected_revision"]["revised_answer"] = (
            revised_answer.strip()
            if isinstance(revised_answer, str) and revised_answer.strip()
            else sample["initial_answer"]
        )
        compiled.append(sample)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("compiled annotation output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "falsirag_bench.jsonl", compiled)
    shutil.copy2(data_dir / "corpus.jsonl", output_dir / "corpus.jsonl")
    shutil.copy2(data_dir / "split_manifest.json", output_dir / "split_manifest.json")
    (output_dir / "splits").mkdir(exist_ok=True)
    for split in ("train", "dev"):
        write_jsonl(
            output_dir / "splits" / f"{split}.jsonl",
            (sample for sample in compiled if sample["split"] == split),
        )
    shutil.copy2(
        data_dir / "splits" / "test_inputs.jsonl",
        output_dir / "splits" / "test_inputs.jsonl",
    )
    evidence_dir = output_dir / "annotation_evidence"
    evidence_dir.mkdir()
    evidence_sources = {
        "packet_manifest.json": packet_dir / "packet_manifest.json",
        **{
            str(filename): _packet_file(packet_dir, str(filename))
            for filename in annotation_files.values()
        },
        str(packet_manifest["adjudication_file"]): _packet_file(
            packet_dir, str(packet_manifest["adjudication_file"])
        ),
    }
    readme_path = packet_dir / "README.md"
    if readme_path.is_file():
        evidence_sources["README.md"] = readme_path
    evidence_files: dict[str, str] = {}
    for relative, source in evidence_sources.items():
        destination = evidence_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        evidence_files[relative] = sha256_file(destination)
    evidence_manifest = {
        "schema_version": "falsirag-annotation-evidence-v1",
        "source_fingerprints": source_fingerprints,
        "annotators": sorted(by_annotator),
        "adjudicator_id": next(iter(adjudicator_ids)),
        "samples": len(compiled),
        "files": dict(sorted(evidence_files.items())),
    }
    evidence_manifest_path = evidence_dir / "evidence_manifest.json"
    write_json(evidence_manifest_path, evidence_manifest)
    report = {
        "schema_version": "falsirag-annotation-report-v1",
        "samples": len(compiled),
        "annotators": sorted(by_annotator),
        "adjudicator_id": next(iter(adjudicator_ids)),
        "annotation_evidence_manifest_sha256": sha256_file(evidence_manifest_path),
        "pairwise": pair_reports,
        "mean_kappas": mean_kappas,
        "minimum_required_kappa": 0.6,
        "agreement_gate_passed": min(mean_kappas.values()) >= 0.6,
        "adjudicated": True,
    }
    write_json(output_dir / "annotation_report.json", report)
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    blockers = ["externally held blind-test protocol"]
    if not report["agreement_gate_passed"]:
        blockers.insert(0, "Cohen's kappa agreement gate did not pass")
    manifest["annotation"] = {
        "status": "adjudicated",
        "machine_seed_is_gold": False,
        "required_annotators": 2,
        "required_adjudication": True,
        "adjudicator_id": next(iter(adjudicator_ids)),
        "evidence": "annotation_evidence/evidence_manifest.json",
        "evidence_manifest_sha256": sha256_file(evidence_manifest_path),
        "report": "annotation_report.json",
        "agreement_gate_passed": report["agreement_gate_passed"],
        "mean_kappas": mean_kappas,
    }
    manifest["publication_ready"] = False
    manifest["publication_blockers"] = blockers
    manifest["fingerprints"] = {
        "corpus_sha256": sha256_file(output_dir / "corpus.jsonl"),
        "benchmark_sha256": sha256_file(output_dir / "falsirag_bench.jsonl"),
        "split_manifest_sha256": sha256_file(output_dir / "split_manifest.json"),
    }
    write_json(output_dir / "manifest.json", manifest)
    validate_annotation_evidence(output_dir)
    return report


def validate_annotation_evidence(data_dir: Path) -> dict[str, Any]:
    """Recompute IAA and adjudication bindings from a compiled evidence archive."""

    evidence_dir = data_dir / "annotation_evidence"
    evidence_manifest_path = evidence_dir / "evidence_manifest.json"
    evidence_manifest = json.loads(evidence_manifest_path.read_text(encoding="utf-8"))
    if evidence_manifest.get("schema_version") != "falsirag-annotation-evidence-v1":
        raise ValueError("unsupported annotation evidence schema")
    files = evidence_manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("annotation evidence file fingerprints are missing")
    observed_files = {
        path.relative_to(evidence_dir).as_posix()
        for path in evidence_dir.rglob("*")
        if path.is_file() and path != evidence_manifest_path
    }
    if observed_files != set(files):
        raise ValueError("annotation evidence archive contains missing or unrecorded files")
    for relative, fingerprint in files.items():
        path = _packet_file(evidence_dir, str(relative))
        if sha256_file(path) != fingerprint:
            raise ValueError(f"annotation evidence fingerprint mismatch: {relative}")

    packet_manifest = json.loads(
        (evidence_dir / "packet_manifest.json").read_text(encoding="utf-8")
    )
    if packet_manifest.get("source_fingerprints") != evidence_manifest.get("source_fingerprints"):
        raise ValueError("packet and evidence manifests disagree on source fingerprints")
    if evidence_manifest["source_fingerprints"].get("corpus_sha256") != sha256_file(
        data_dir / "corpus.jsonl"
    ):
        raise ValueError("annotation evidence points to a different corpus")
    annotation_files = packet_manifest.get("annotation_files")
    annotator_ids = packet_manifest.get("annotator_ids")
    if (
        not isinstance(annotation_files, dict)
        or not isinstance(annotator_ids, list)
        or set(annotation_files) != set(map(str, annotator_ids))
        or len(annotation_files) < 2
    ):
        raise ValueError("archived packet reviewer declarations are invalid")
    expected_count = int(packet_manifest["samples"])
    samples = read_jsonl(data_dir / "falsirag_bench.jsonl")
    sample_by_id = {str(row["id"]): row for row in samples}
    corpus = {row["doc_id"]: row for row in read_jsonl(data_dir / "corpus.jsonl")}
    if expected_count != len(sample_by_id):
        raise ValueError("archived packet sample count differs from compiled benchmark")

    by_annotator: dict[str, dict[str, dict[str, Any]]] = {}
    for annotator_id, filename in annotation_files.items():
        rows = _rows_by_id(
            read_jsonl(_packet_file(evidence_dir, str(filename))),
            expected=expected_count,
            role=str(annotator_id),
        )
        if set(rows) != set(sample_by_id):
            raise ValueError(f"{annotator_id}: archived reviewer sample set mismatch")
        validated: dict[str, dict[str, Any]] = {}
        for sample_id, row in rows.items():
            expected = _visible_row(sample_by_id[sample_id], corpus, str(annotator_id))
            _assert_visible_unchanged(row, expected, _REVIEW_VISIBLE_FIELDS, role=str(annotator_id))
            validated[sample_id] = _validated_annotation(row, "annotation")
        by_annotator[str(annotator_id)] = validated

    adjudication_rows = _rows_by_id(
        read_jsonl(_packet_file(evidence_dir, str(packet_manifest.get("adjudication_file", "")))),
        expected=expected_count,
        role="adjudication",
    )
    if set(adjudication_rows) != set(sample_by_id):
        raise ValueError("archived adjudication sample set mismatch")
    adjudicator_ids = {
        str(row.get("adjudicator_id", "")).strip() for row in adjudication_rows.values()
    }
    if "" in adjudicator_ids or len(adjudicator_ids) != 1:
        raise ValueError("archived adjudication has inconsistent adjudicator IDs")
    adjudications: dict[str, dict[str, Any]] = {}
    for sample_id, row in adjudication_rows.items():
        expected = _visible_row(sample_by_id[sample_id], corpus, "adjudicator")
        expected.pop("annotator_id")
        _assert_visible_unchanged(row, expected, _ADJUDICATION_VISIBLE_FIELDS, role="adjudicator")
        gold = _validated_annotation(row, "gold_annotation")
        revised_answer = gold.get("revised_answer")
        if gold["conflict_present"] and (
            not isinstance(revised_answer, str) or not revised_answer.strip()
        ):
            raise ValueError(f"{sample_id}: conflicting adjudication requires revised_answer")
        if (
            not gold["conflict_present"]
            and isinstance(revised_answer, str)
            and revised_answer.strip()
        ):
            raise ValueError(f"{sample_id}: no-conflict adjudication must not set revised_answer")
        adjudications[sample_id] = gold

    pairwise, mean_kappas = _agreement_summary(by_annotator, set(sample_by_id))
    report = json.loads((data_dir / "annotation_report.json").read_text(encoding="utf-8"))
    checks = {
        "annotators": report.get("annotators") == sorted(by_annotator),
        "adjudicator": report.get("adjudicator_id") == next(iter(adjudicator_ids)),
        "samples": report.get("samples") == expected_count,
        "pairwise": report.get("pairwise") == pairwise,
        "mean_kappas": report.get("mean_kappas") == mean_kappas,
        "evidence": report.get("annotation_evidence_manifest_sha256")
        == sha256_file(evidence_manifest_path),
    }
    failed = sorted(key for key, passed in checks.items() if not passed)
    if failed:
        raise ValueError(f"annotation report differs from archived evidence: {failed}")
    for sample_id, sample in sample_by_id.items():
        gold = adjudications[sample_id]
        if sample.get("annotation_status") != "adjudicated":
            raise ValueError(f"{sample_id}: compiled row is not adjudicated")
        if sample.get("conflict_type") != gold["conflict_type"]:
            raise ValueError(f"{sample_id}: compiled conflict type differs from adjudication")
        if sample.get("expected_revision", {}).get("action") != gold["revision_action"]:
            raise ValueError(f"{sample_id}: compiled revision action differs from adjudication")
        revised_answer = gold.get("revised_answer")
        expected_answer = (
            revised_answer.strip()
            if isinstance(revised_answer, str) and revised_answer.strip()
            else sample["initial_answer"]
        )
        if sample.get("expected_revision", {}).get("revised_answer") != expected_answer:
            raise ValueError(f"{sample_id}: compiled revised answer differs from adjudication")
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    annotation = manifest.get("annotation", {})
    if (
        not isinstance(annotation, dict)
        or annotation.get("evidence_manifest_sha256") != sha256_file(evidence_manifest_path)
        or annotation.get("adjudicator_id") != next(iter(adjudicator_ids))
        or annotation.get("mean_kappas") != mean_kappas
    ):
        raise ValueError("compiled manifest differs from archived annotation evidence")
    return {
        "schema_version": "falsirag-annotation-evidence-validation-v1",
        "valid": True,
        "samples": expected_count,
        "annotators": sorted(by_annotator),
        "adjudicator_id": next(iter(adjudicator_ids)),
        "mean_kappas": mean_kappas,
        "evidence_manifest_sha256": sha256_file(evidence_manifest_path),
    }
