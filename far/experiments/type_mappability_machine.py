"""Run and verify the machine-only P6-M ontology-stability audit."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from statistics import mean
from typing import Any

from far.bench.annotations import cohen_kappa
from far.bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.bench.build.jury_consensus import fleiss_kappa
from far.experiments.runner import (
    _implementation_sha256,
    _llm_runtime_identity,
    _source_revision,
    build_generator,
    load_config,
    release_generator,
)
from far.experiments.type_mappability import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    DATASET_ORDER,
    MACHINE_PRELABEL_RESPONSE_SCHEMA,
    MAPPABILITY_LABELS,
    TYPE_NAMES,
    _annotation_items,
    _association,
    _bootstrap_mean,
    _mapping_weight,
    _score_deltas,
    _stable_sha,
    _stratum_key,
    validate_annotation,
)
from far.paths import repository_root

ROOT = repository_root()
PROTOCOL_PATH = ROOT / "docs" / "PREREG_TYPE_MAPPABILITY_MACHINE_2026-07-13.md"
PROTOCOL_SHA256 = "63488c9cdd83f6da4aa110ca8ee836c793b12ddbffd01011961053c9c08b400e"
PROFILE = "machine_ontology_stability_audit"
VIEW_IDS = ("view_a", "view_b")
P6M_MAX_ATTEMPTS = 5
JUROR_SPECS = {
    "J1": {
        "family": "mistral",
        "provider": "ollama",
        "model": "mistral:7b-instruct",
    },
    "J2": {"family": "glm", "provider": "ollama", "model": "glm4:9b"},
    "J3": {"family": "meta", "provider": "ollama", "model": "llama3.1:8b"},
}
P6M_RESPONSE_SCHEMA: dict[str, Any] = copy.deepcopy(MACHINE_PRELABEL_RESPONSE_SCHEMA)
for _branch in P6M_RESPONSE_SCHEMA["oneOf"]:
    _mapped_types = _branch["properties"]["mapped_types"]
    _mapped_types["maxItems"] = min(int(_mapped_types.get("maxItems", len(TYPE_NAMES))), 7)
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
_SYSTEM_PROMPTS = {
    "view_a": (
        "Independently classify ontology mappability using only the supplied closed evidence. "
        "Do not use memorized world knowledge. Return exactly one JSON object."
    ),
    "view_b": (
        "Judge whether the frozen ontology can express the decisive conflict, relying only on "
        "the visible closed evidence. Ignore outside knowledge and return one JSON object only."
    ),
}
_RETRY = (
    "Your preceding response violated the frozen JSON schema. Correct only that schema error "
    "and return exactly one JSON object without markdown."
)


def _protocol_audit() -> dict[str, Any]:
    valid = PROTOCOL_PATH.is_file() and sha256_file(PROTOCOL_PATH) == PROTOCOL_SHA256
    return {
        "valid": valid,
        "protocol_sha256": PROTOCOL_SHA256,
        "error": None if valid else "P6-M protocol fingerprint mismatch",
    }


def _source(packet_dir: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], str]:
    audit = _protocol_audit()
    if audit["valid"] is not True:
        raise ValueError(str(audit["error"]))
    manifest, items = _annotation_items(packet_dir)
    manifest_path = packet_dir / "packet_manifest.json"
    return manifest, items, sha256_file(manifest_path)


def _ordered_evidence(item: dict[str, Any], view_id: str) -> list[dict[str, Any]]:
    if view_id not in VIEW_IDS:
        raise ValueError("unsupported P6-M view")
    ordered = sorted(
        item["evidence"],
        key=lambda evidence: hashlib.sha256(
            (f"{PROTOCOL_SHA256}:{item['sample_id']}:{evidence['evidence_id']}").encode()
        ).hexdigest(),
    )
    return ordered if view_id == "view_a" else list(reversed(ordered))


def _prompt(item: dict[str, Any], view_id: str) -> str:
    evidence = _ordered_evidence(item, view_id)
    type_guide = "\n".join(f"- {name}: {_TYPE_GUIDE[name]}" for name in TYPE_NAMES)
    if view_id == "view_a":
        task = (
            "Classify the sample as clean, partial, or unmappable. Clean requires exactly one "
            "decisive mapped type and no missing concept. Partial requires mapped type(s) plus "
            "a missing decisive concept. Unmappable requires no mapped types and a missing concept."
        )
    else:
        task = (
            "Assess coverage by the frozen ontology. Use clean only when one ontology type fully "
            "determines the conflict; use partial when covered in part but a key relation is "
            "missing; use unmappable when none of the seven types expresses the decisive relation."
        )
    return (
        f"{task}\n\nFrozen type guide:\n{type_guide}\n\n"
        "Required JSON fields: mappability, mapped_types, missing_concept, rationale.\n"
        "List each mapped type at most once and never emit more than seven mapped types.\n"
        "Keep missing_concept to a short phrase and rationale to at most two concise sentences.\n"
        "For insufficient evidence use unmappable with no mapped types and "
        "missing_concept=insufficient_visible_evidence. counter_evidence is not a generic "
        "fallback when a more specific type applies.\n\n"
        f"Question:\n{item['question']}\n\n"
        f"Initial answer:\n{item['initial_answer']}\n\n"
        f"Reference answers:\n{json.dumps(item['reference_answers'], ensure_ascii=False)}\n\n"
        f"Closed evidence ({view_id}):\n{json.dumps(evidence, ensure_ascii=False)}"
    )


_PROMPT_FINGERPRINT_ITEM = {
    "sample_id": "{sample_id}",
    "question": "{question}",
    "initial_answer": "{initial_answer}",
    "reference_answers": ["{reference_answer}"],
    "evidence": [
        {
            "evidence_id": "{evidence_id_a}",
            "title": "{title_a}",
            "text": "{text_a}",
            "source": "{source_a}",
            "date": "{date_a}",
        },
        {
            "evidence_id": "{evidence_id_b}",
            "title": "{title_b}",
            "text": "{text_b}",
            "source": "{source_b}",
            "date": "{date_b}",
        },
    ],
}
PROMPT_TEMPLATE_SHA256 = _stable_sha(
    {
        "prompts": {view_id: _prompt(_PROMPT_FINGERPRINT_ITEM, view_id) for view_id in VIEW_IDS},
        "system_prompts": _SYSTEM_PROMPTS,
        "generation_response_schema": P6M_RESPONSE_SCHEMA,
        "validation_response_schema": MACHINE_PRELABEL_RESPONSE_SCHEMA,
        "view_rule": "sha256_order_then_reverse",
        "retry": _RETRY,
        "max_attempts": P6M_MAX_ATTEMPTS,
    }
)


def _retry_prompt(base_prompt: str, previous: str, error: str) -> str:
    return (
        f"{base_prompt}\n\n{_RETRY}\nValidation error: {error}\n"
        f"Previous invalid response:\n{previous}"
    )


def _parse_p6m_response(response: str, *, sample_id: str) -> dict[str, Any]:
    stripped = response.strip()
    decoder = json.JSONDecoder()
    for index, character in enumerate(stripped):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return validate_annotation(value, sample_id=sample_id)
    raise ValueError(f"{sample_id}: P6-M response does not contain a valid JSON object")


def _validate_failure_log(
    rows: list[dict[str, Any]],
    items: dict[str, dict[str, Any]],
    *,
    juror_id: str,
    model_family: str,
) -> None:
    for sequence, row in enumerate(rows, start=1):
        sample_id = str(row.get("sample_id", ""))
        view_id = str(row.get("view_id", ""))
        prompt = str(row.get("prompt", ""))
        response = str(row.get("raw_response", ""))
        if (
            row.get("schema_version") != "far-p6m-failed-attempt-v1"
            or row.get("sequence") != sequence
            or sample_id not in items
            or view_id not in VIEW_IDS
            or row.get("juror_id") != juror_id
            or row.get("model_family") != model_family
            or row.get("context_sha256") != items[sample_id]["context_sha256"]
            or row.get("attempt") not in range(1, P6M_MAX_ATTEMPTS + 1)
            or row.get("prompt_sha256") != hashlib.sha256(prompt.encode()).hexdigest()
            or row.get("raw_response_sha256") != hashlib.sha256(response.encode()).hexdigest()
        ):
            raise ValueError("P6-M failed-attempt log provenance is invalid")
        try:
            _parse_p6m_response(response, sample_id=sample_id)
        except ValueError as exc:
            if row.get("validation_error") != str(exc):
                raise ValueError("P6-M failed-attempt error changed") from exc
        else:
            raise ValueError("P6-M failed-attempt log contains a valid response")


def _validate_runtime(
    config: dict[str, Any], juror_id: str
) -> tuple[dict[str, str], dict[str, Any]]:
    spec = JUROR_SPECS.get(juror_id)
    if spec is None:
        raise ValueError("juror_id must be J1, J2, or J3")
    llm = config.get("llm")
    if not isinstance(llm, dict):
        raise ValueError("P6-M config requires an llm mapping")
    actual = {
        "family": str(llm.get("model_family", "")).strip().lower(),
        "provider": str(llm.get("provider", "")).strip().lower(),
        "model": str(llm.get("model", "")).strip(),
    }
    if actual != spec:
        raise ValueError(f"{juror_id} differs from the frozen P6-M identity: {actual}")
    if float(llm.get("temperature", -1.0)) != 0.0:
        raise ValueError("P6-M requires temperature=0")
    runtime = _llm_runtime_identity(config)
    if (
        runtime.get("enabled") is not True
        or runtime.get("provider") != spec["provider"]
        or runtime.get("model") != spec["model"]
    ):
        raise ValueError("P6-M runtime differs from the frozen identity")
    if spec["provider"] == "ollama":
        ollama = runtime.get("ollama_model")
        if (
            not isinstance(ollama, dict)
            or ollama.get("model") != spec["model"]
            or len(str(ollama.get("digest", ""))) != 64
        ):
            raise ValueError("P6-M Ollama runtime lacks an immutable model digest")
    return spec, runtime


def _attempts_valid(
    attempts: Any,
    item: dict[str, Any],
    view_id: str,
) -> dict[str, Any]:
    if not isinstance(attempts, list) or not attempts or len(attempts) > P6M_MAX_ATTEMPTS:
        raise ValueError(f"{item['sample_id']}:{view_id}: invalid attempt chain")
    base_prompt = _prompt(item, view_id)
    prompt = base_prompt
    parsed: dict[str, Any] | None = None
    for index, attempt in enumerate(attempts, start=1):
        if not isinstance(attempt, dict) or attempt.get("attempt") != index:
            raise ValueError(f"{item['sample_id']}:{view_id}: invalid attempt number")
        response = str(attempt.get("raw_response", ""))
        if attempt.get("prompt_sha256") != hashlib.sha256(prompt.encode("utf-8")).hexdigest():
            raise ValueError(f"{item['sample_id']}:{view_id}: prompt fingerprint mismatch")
        if (
            attempt.get("raw_response_sha256")
            != hashlib.sha256(response.encode("utf-8")).hexdigest()
        ):
            raise ValueError(f"{item['sample_id']}:{view_id}: response fingerprint mismatch")
        try:
            candidate = _parse_p6m_response(response, sample_id=str(item["sample_id"]))
        except ValueError as exc:
            if attempt.get("valid") is not False or attempt.get("validation_error") != str(exc):
                raise ValueError(f"{item['sample_id']}:{view_id}: invalid failure record") from exc
            if index == len(attempts):
                raise ValueError(
                    f"{item['sample_id']}:{view_id}: attempt chain ends invalid"
                ) from exc
            prompt = _retry_prompt(base_prompt, response, str(exc))
        else:
            if attempt.get("valid") is not True or attempt.get("validation_error") is not None:
                raise ValueError(f"{item['sample_id']}:{view_id}: invalid success record")
            if index != len(attempts):
                raise ValueError(f"{item['sample_id']}:{view_id}: attempts continue after success")
            parsed = candidate
    if parsed is None:
        raise ValueError(f"{item['sample_id']}:{view_id}: no valid annotation")
    return parsed


def annotate_juror(
    packet_dir: Path,
    config_path: Path,
    output_dir: Path,
    *,
    juror_id: str,
    overwrite: bool = False,
    resume: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    if overwrite and resume:
        raise ValueError("overwrite and resume cannot both be true")
    _, items, source_sha = _source(packet_dir)
    config = load_config(config_path)
    spec, runtime = _validate_runtime(config, juror_id)
    revision = _source_revision()
    if revision.get("git_dirty") is not False or not str(revision.get("git_commit", "")):
        raise ValueError("P6-M model execution requires a clean committed Git revision")
    identity = {
        "schema_version": "far-p6m-juror-identity-v1",
        "study_profile": PROFILE,
        "juror_id": juror_id,
        "model_family": spec["family"],
        "provider": spec["provider"],
        "model": spec["model"],
        "config_sha256": sha256_file(config_path),
        "llm_runtime": runtime,
        "implementation_sha256": _implementation_sha256(),
        "source_revision": revision,
        "source_packet_manifest_sha256": source_sha,
        "protocol_sha256": PROTOCOL_SHA256,
        "prompt_template_sha256": PROMPT_TEMPLATE_SHA256,
    }
    if output_dir.exists() and overwrite:
        marker = output_dir / "juror_manifest.json"
        if not marker.is_file():
            raise ValueError("refusing to overwrite a directory without a P6-M manifest")
        shutil.rmtree(output_dir)
    elif output_dir.exists() and any(output_dir.iterdir()) and not resume:
        raise FileExistsError(f"{output_dir} exists; pass --overwrite or --resume")
    elif (
        output_dir.exists()
        and any(output_dir.iterdir())
        and resume
        and not (output_dir / "run_identity.json").is_file()
    ):
        raise ValueError("refusing to resume a directory without a P6-M run identity")
    output_dir.mkdir(parents=True, exist_ok=True)
    identity_path = output_dir / "run_identity.json"
    if identity_path.is_file():
        if json.loads(identity_path.read_text(encoding="utf-8")) != identity:
            raise ValueError("P6-M resume identity differs from the existing run")
    else:
        write_json(identity_path, identity)
    rows_path = output_dir / f"annotations_{juror_id}.jsonl"
    failures_path = output_dir / "failed_attempts.jsonl"
    existing_rows = read_jsonl(rows_path) if rows_path.is_file() else []
    failure_rows = read_jsonl(failures_path) if failures_path.is_file() else []
    _validate_failure_log(
        failure_rows,
        items,
        juror_id=juror_id,
        model_family=spec["family"],
    )
    failure_sequence = len(failure_rows)
    completed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in existing_rows:
        sample_id = str(row.get("sample_id", ""))
        view_id = str(row.get("view_id", ""))
        key = (sample_id, view_id)
        if key in completed or sample_id not in items or view_id not in VIEW_IDS:
            raise ValueError("P6-M checkpoint has invalid sample/view keys")
        if (
            row.get("schema_version") != "far-p6m-juror-annotation-v1"
            or row.get("juror_id") != juror_id
            or row.get("model_family") != spec["family"]
            or row.get("context_sha256") != items[sample_id]["context_sha256"]
            or row.get("human_annotator") is not False
            or row.get("publication_gold") is not False
        ):
            raise ValueError(f"{sample_id}:{view_id}: P6-M checkpoint provenance mismatch")
        parsed = _attempts_valid(row.get("attempts"), items[sample_id], view_id)
        if parsed != row.get("annotation"):
            raise ValueError(f"{sample_id}:{view_id}: annotation differs from raw response")
        completed[key] = row
    ordered_ids = sorted(items)
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        ordered_ids = ordered_ids[:limit]
    generator = build_generator(config)
    if generator is None:
        raise ValueError("P6-M annotation requires an enabled generator")
    try:
        with (
            rows_path.open("a", encoding="utf-8") as handle,
            failures_path.open("a", encoding="utf-8") as failure_handle,
        ):
            for sample_id in ordered_ids:
                item = items[sample_id]
                for view_id in VIEW_IDS:
                    key = (sample_id, view_id)
                    if key in completed:
                        continue
                    base_prompt = _prompt(item, view_id)
                    prompt = base_prompt
                    attempts: list[dict[str, Any]] = []
                    annotation: dict[str, Any] | None = None
                    for attempt_number in range(1, P6M_MAX_ATTEMPTS + 1):
                        response = generator.complete(
                            prompt,
                            system_prompt=_SYSTEM_PROMPTS[view_id],
                            temperature=0.0,
                            max_tokens=int(config.get("llm", {}).get("max_tokens", 1200)),
                            response_format=P6M_RESPONSE_SCHEMA,
                        ).strip()
                        attempt = {
                            "attempt": attempt_number,
                            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                            "raw_response": response,
                            "raw_response_sha256": hashlib.sha256(
                                response.encode("utf-8")
                            ).hexdigest(),
                        }
                        try:
                            annotation = _parse_p6m_response(response, sample_id=sample_id)
                        except ValueError as exc:
                            attempt.update({"valid": False, "validation_error": str(exc)})
                            attempts.append(attempt)
                            failure_sequence += 1
                            failure_row = {
                                "schema_version": "far-p6m-failed-attempt-v1",
                                "sequence": failure_sequence,
                                "sample_id": sample_id,
                                "view_id": view_id,
                                "context_sha256": item["context_sha256"],
                                "juror_id": juror_id,
                                "model_family": spec["family"],
                                "prompt": prompt,
                                **attempt,
                            }
                            failure_handle.write(
                                json.dumps(failure_row, ensure_ascii=False, sort_keys=True) + "\n"
                            )
                            failure_handle.flush()
                            os.fsync(failure_handle.fileno())
                            print(
                                f"p6m: invalid {juror_id} {sample_id} {view_id} "
                                f"attempt={attempt_number}: {exc}"
                            )
                            if attempt_number == P6M_MAX_ATTEMPTS:
                                raise ValueError(
                                    f"{sample_id}:{view_id}: invalid after "
                                    f"{P6M_MAX_ATTEMPTS} attempts"
                                ) from exc
                            prompt = _retry_prompt(base_prompt, response, str(exc))
                        else:
                            attempt.update({"valid": True, "validation_error": None})
                            attempts.append(attempt)
                            break
                    if annotation is None:
                        raise ValueError(f"{sample_id}:{view_id}: no annotation")
                    row = {
                        "schema_version": "far-p6m-juror-annotation-v1",
                        "sample_id": sample_id,
                        "view_id": view_id,
                        "context_sha256": item["context_sha256"],
                        "juror_id": juror_id,
                        "model_family": spec["family"],
                        "annotation": annotation,
                        "attempts": attempts,
                        "human_annotator": False,
                        "publication_gold": False,
                    }
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                    completed[key] = row
                    print(f"p6m: completed {juror_id} {sample_id} {view_id}")
    finally:
        release_generator(generator)
    expected_keys = {(sample_id, view_id) for sample_id in items for view_id in VIEW_IDS}
    complete = set(completed) == expected_keys
    manifest = {
        "schema_version": "far-p6m-juror-manifest-v1",
        "study_profile": PROFILE,
        "protocol_sha256": PROTOCOL_SHA256,
        "prompt_template_sha256": PROMPT_TEMPLATE_SHA256,
        "source_packet_manifest_sha256": source_sha,
        "juror_id": juror_id,
        "model_family": spec["family"],
        "provider": spec["provider"],
        "model": spec["model"],
        "config_sha256": identity["config_sha256"],
        "samples": len({sample_id for sample_id, _ in completed}),
        "views_per_sample": len(VIEW_IDS),
        "rows": len(completed),
        "expected_samples": len(items),
        "expected_rows": len(items) * len(VIEW_IDS),
        "complete": complete,
        "annotation_file": rows_path.name,
        "annotation_sha256": sha256_file(rows_path),
        "failed_attempt_file": failures_path.name,
        "failed_attempts": failure_sequence,
        "failed_attempt_sha256": sha256_file(failures_path),
        "run_identity_sha256": sha256_file(identity_path),
        "qwen_prelabels_used": False,
        "human_annotator": False,
        "human_annotation_replaced": False,
        "human_iaa_computed": False,
        "publication_gold": False,
        "test_accessed": False,
    }
    write_json(output_dir / "juror_manifest.json", manifest)
    return manifest


def _load_juror(
    directory: Path,
    items: dict[str, dict[str, Any]],
    source_sha: str,
) -> tuple[dict[str, Any], dict[str, dict[str, dict[str, Any]]]]:
    manifest = json.loads((directory / "juror_manifest.json").read_text(encoding="utf-8"))
    juror_id = str(manifest.get("juror_id", ""))
    spec = JUROR_SPECS.get(juror_id)
    if (
        manifest.get("schema_version") != "far-p6m-juror-manifest-v1"
        or manifest.get("study_profile") != PROFILE
        or manifest.get("protocol_sha256") != PROTOCOL_SHA256
        or manifest.get("prompt_template_sha256") != PROMPT_TEMPLATE_SHA256
        or manifest.get("source_packet_manifest_sha256") != source_sha
        or manifest.get("complete") is not True
        or manifest.get("samples") != len(items)
        or manifest.get("expected_samples") != len(items)
        or manifest.get("expected_rows") != len(items) * len(VIEW_IDS)
        or manifest.get("rows") != len(items) * len(VIEW_IDS)
        or manifest.get("views_per_sample") != len(VIEW_IDS)
        or spec is None
        or manifest.get("model_family") != spec["family"]
        or manifest.get("provider") != spec["provider"]
        or manifest.get("model") != spec["model"]
        or len(str(manifest.get("config_sha256", ""))) != 64
        or not isinstance(manifest.get("failed_attempts"), int)
        or int(manifest.get("failed_attempts", -1)) < 0
        or manifest.get("qwen_prelabels_used") is not False
        or manifest.get("human_annotator") is not False
        or manifest.get("human_annotation_replaced") is not False
        or manifest.get("human_iaa_computed") is not False
        or manifest.get("publication_gold") is not False
        or manifest.get("test_accessed") is not False
    ):
        raise ValueError(f"{directory}: invalid P6-M juror manifest")
    annotation_file = str(manifest.get("annotation_file", ""))
    if not annotation_file or Path(annotation_file).name != annotation_file:
        raise ValueError(f"{directory}: invalid P6-M annotation filename")
    failed_attempt_file = str(manifest.get("failed_attempt_file", ""))
    if not failed_attempt_file or Path(failed_attempt_file).name != failed_attempt_file:
        raise ValueError(f"{directory}: invalid P6-M failed-attempt filename")
    annotations_path = directory / annotation_file
    failures_path = directory / failed_attempt_file
    identity_path = directory / "run_identity.json"
    if (
        sha256_file(annotations_path) != manifest.get("annotation_sha256")
        or sha256_file(failures_path) != manifest.get("failed_attempt_sha256")
        or sha256_file(identity_path) != manifest.get("run_identity_sha256")
    ):
        raise ValueError(f"{directory}: P6-M juror fingerprint mismatch")
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    runtime = identity.get("llm_runtime")
    if (
        identity.get("schema_version") != "far-p6m-juror-identity-v1"
        or identity.get("study_profile") != PROFILE
        or identity.get("juror_id") != juror_id
        or identity.get("model_family") != spec["family"]
        or identity.get("provider") != spec["provider"]
        or identity.get("model") != spec["model"]
        or identity.get("config_sha256") != manifest.get("config_sha256")
        or identity.get("source_packet_manifest_sha256") != source_sha
        or identity.get("protocol_sha256") != PROTOCOL_SHA256
        or identity.get("prompt_template_sha256") != PROMPT_TEMPLATE_SHA256
        or not isinstance(runtime, dict)
        or runtime.get("enabled") is not True
        or runtime.get("provider") != spec["provider"]
        or runtime.get("model") != spec["model"]
        or identity.get("source_revision", {}).get("git_dirty") is not False
        or not str(identity.get("source_revision", {}).get("git_commit", ""))
        or not str(identity.get("implementation_sha256", ""))
    ):
        raise ValueError(f"{directory}: invalid P6-M run identity")
    if spec["provider"] == "ollama":
        ollama = runtime.get("ollama_model")
        if (
            not isinstance(ollama, dict)
            or ollama.get("model") != spec["model"]
            or len(str(ollama.get("digest", ""))) != 64
        ):
            raise ValueError(f"{directory}: missing immutable Ollama digest")
    failure_rows = read_jsonl(failures_path)
    if len(failure_rows) != manifest.get("failed_attempts"):
        raise ValueError(f"{directory}: P6-M failed-attempt count mismatch")
    _validate_failure_log(
        failure_rows,
        items,
        juror_id=juror_id,
        model_family=spec["family"],
    )
    rows: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in read_jsonl(annotations_path):
        sample_id = str(row.get("sample_id", ""))
        view_id = str(row.get("view_id", ""))
        if sample_id not in items or view_id not in VIEW_IDS or view_id in rows[sample_id]:
            raise ValueError(f"{directory}: invalid sample/view set")
        if (
            row.get("schema_version") != "far-p6m-juror-annotation-v1"
            or row.get("juror_id") != juror_id
            or row.get("model_family") != spec["family"]
            or row.get("context_sha256") != items[sample_id]["context_sha256"]
            or row.get("human_annotator") is not False
            or row.get("publication_gold") is not False
        ):
            raise ValueError(f"{sample_id}:{view_id}: invalid P6-M row provenance")
        parsed = _attempts_valid(row.get("attempts"), items[sample_id], view_id)
        if parsed != row.get("annotation"):
            raise ValueError(f"{sample_id}:{view_id}: P6-M annotation/raw mismatch")
        rows[sample_id][view_id] = parsed
    if set(rows) != set(items) or any(set(views) != set(VIEW_IDS) for views in rows.values()):
        raise ValueError(f"{directory}: P6-M annotations are incomplete")
    return manifest, dict(rows)


def _decision(annotation: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    return str(annotation["mappability"]), tuple(str(value) for value in annotation["mapped_types"])


def _decision_text(annotation: dict[str, Any]) -> str:
    label, mapped = _decision(annotation)
    return f"{label}|{','.join(mapped)}"


def _entropy(labels: list[str]) -> float | None:
    if not labels:
        return None
    if len(labels) == 1:
        return 0.0
    counts = Counter(labels)
    raw = -sum((count / len(labels)) * math.log2(count / len(labels)) for count in counts.values())
    return raw / math.log2(len(labels))


def _empty_group() -> dict[str, Any]:
    return {
        "samples": 0,
        "counts": {label: 0 for label in MAPPABILITY_LABELS},
        "mapped_type_counts": {name: 0 for name in TYPE_NAMES},
        "proportions": {label: None for label in MAPPABILITY_LABELS},
        "strict_mappability_rate": None,
        "broad_mappability_rate": None,
        "weighted_mappability": None,
        "delta_by_mappability": {
            label: {"estimate": None, "lower": None, "upper": None, "samples": 0}
            for label in MAPPABILITY_LABELS
        },
    }


def _group(
    ids: list[str],
    annotations: dict[str, dict[str, Any]],
    deltas: dict[str, float],
) -> dict[str, Any]:
    if not ids:
        return _empty_group()
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


def compute_result(
    packet_dir: Path,
    juror_dirs: list[Path],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_manifest, items, source_sha = _source(packet_dir)
    if len(juror_dirs) != 3:
        raise ValueError("P6-M requires exactly three juror directories")
    loaded = [_load_juror(directory, items, source_sha) for directory in juror_dirs]
    manifests = [entry[0] for entry in loaded]
    annotations_by_juror = [entry[1] for entry in loaded]
    juror_ids = [str(manifest["juror_id"]) for manifest in manifests]
    families = [str(manifest["model_family"]) for manifest in manifests]
    if set(juror_ids) != set(JUROR_SPECS) or len(set(families)) != 3:
        raise ValueError("P6-M juror IDs/families must be the three frozen distinct identities")
    ordered = sorted(
        zip(juror_ids, manifests, annotations_by_juror, strict=True),
        key=lambda entry: entry[0],
    )
    juror_ids = [entry[0] for entry in ordered]
    manifests = [entry[1] for entry in ordered]
    annotations_by_juror = [entry[2] for entry in ordered]
    ordered_ids = sorted(items)

    stability: dict[str, dict[str, Any]] = {}
    stable_by_juror: dict[str, dict[str, bool]] = {}
    for juror_id, rows in zip(juror_ids, annotations_by_juror, strict=True):
        stable = {
            sample_id: _decision(rows[sample_id]["view_a"]) == _decision(rows[sample_id]["view_b"])
            for sample_id in ordered_ids
        }
        stable_by_juror[juror_id] = stable
        stability[juror_id] = {
            "stable": sum(stable.values()),
            "unstable": len(stable) - sum(stable.values()),
            "rate": sum(stable.values()) / len(stable),
        }

    view_agreement: dict[str, Any] = {}
    for view_id in VIEW_IDS:
        labels = {
            juror_id: [rows[sample_id][view_id]["mappability"] for sample_id in ordered_ids]
            for juror_id, rows in zip(juror_ids, annotations_by_juror, strict=True)
        }
        pairwise = {
            f"{left}__{right}": cohen_kappa(labels[left], labels[right])
            for left, right in combinations(juror_ids, 2)
        }
        type_pairwise: dict[str, dict[str, float]] = {}
        for left, right in combinations(juror_ids, 2):
            key = f"{left}__{right}"
            left_rows = annotations_by_juror[juror_ids.index(left)]
            right_rows = annotations_by_juror[juror_ids.index(right)]
            type_pairwise[key] = {
                name: cohen_kappa(
                    [
                        str(name in left_rows[sample_id][view_id]["mapped_types"])
                        for sample_id in ordered_ids
                    ],
                    [
                        str(name in right_rows[sample_id][view_id]["mapped_types"])
                        for sample_id in ordered_ids
                    ],
                )
                for name in TYPE_NAMES
            }
        view_agreement[view_id] = {
            "mappability_pairwise_cohen_kappa": pairwise,
            "mappability_fleiss_kappa": fleiss_kappa(
                [
                    [labels[juror_id][index] for juror_id in juror_ids]
                    for index in range(len(ordered_ids))
                ]
            ),
            "mapped_type_pairwise_kappas": type_pairwise,
            "mapped_type_pairwise_macro_kappa": {
                pair: mean(values.values()) for pair, values in type_pairwise.items()
            },
        }

    pair_sensitivity: dict[str, Any] = {}
    for left, right in combinations(juror_ids, 2):
        left_rows = annotations_by_juror[juror_ids.index(left)]
        right_rows = annotations_by_juror[juror_ids.index(right)]
        both_stable = [
            sample_id
            for sample_id in ordered_ids
            if stable_by_juror[left][sample_id] and stable_by_juror[right][sample_id]
        ]
        same = sum(
            _decision(left_rows[sample_id]["view_a"]) == _decision(right_rows[sample_id]["view_a"])
            for sample_id in both_stable
        )
        pair_sensitivity[f"{left}__{right}"] = {
            "both_stable": len(both_stable),
            "same_decision": same,
            "same_decision_rate": same / len(both_stable) if both_stable else None,
        }

    consensus_rows: list[dict[str, Any]] = []
    dispositions: Counter[str] = Counter()
    resolved: dict[str, dict[str, Any]] = {}
    for sample_id in ordered_ids:
        stable_votes: dict[str, dict[str, Any]] = {}
        all_views: dict[str, Any] = {}
        for juror_id, rows in zip(juror_ids, annotations_by_juror, strict=True):
            all_views[juror_id] = {view_id: rows[sample_id][view_id] for view_id in VIEW_IDS}
            if stable_by_juror[juror_id][sample_id]:
                stable_votes[juror_id] = rows[sample_id]["view_a"]
        counts = Counter(_decision_text(annotation) for annotation in stable_votes.values())
        winner, votes = counts.most_common(1)[0] if counts else (None, 0)
        if len(stable_votes) == 3 and len(counts) == 1:
            disposition = "unanimous"
        elif votes >= 2:
            disposition = "majority"
        else:
            disposition = "contested"
        dispositions[disposition] += 1
        supporters = (
            sorted(
                juror_id
                for juror_id, annotation in stable_votes.items()
                if _decision_text(annotation) == winner
            )
            if disposition != "contested"
            else []
        )
        consensus_annotation: dict[str, Any] | None = None
        if disposition != "contested":
            representative = stable_votes[supporters[0]]
            consensus_annotation = {
                "mappability": representative["mappability"],
                "mapped_types": representative["mapped_types"],
            }
            resolved[sample_id] = consensus_annotation
        vote_labels = [_decision_text(annotation) for annotation in stable_votes.values()]
        consensus_rows.append(
            {
                "schema_version": "far-p6m-consensus-row-v1",
                "sample_id": sample_id,
                "dataset": items[sample_id]["dataset"],
                "context_sha256": items[sample_id]["context_sha256"],
                "juror_stability": {
                    juror_id: stable_by_juror[juror_id][sample_id] for juror_id in juror_ids
                },
                "stable_votes": {
                    juror_id: {
                        "mappability": annotation["mappability"],
                        "mapped_types": annotation["mapped_types"],
                    }
                    for juror_id, annotation in stable_votes.items()
                },
                "source_annotations": all_views,
                "stable_juror_count": len(stable_votes),
                "vote_entropy": _entropy(vote_labels),
                "disposition": disposition,
                "supporting_jurors": supporters,
                "consensus_annotation": consensus_annotation,
                "machine_consensus_only": True,
                "human_gold": False,
                "publication_gold": False,
            }
        )

    deltas = _score_deltas(items)
    resolved_ids = sorted(resolved)
    by_dataset = {
        dataset: _group(
            [sample_id for sample_id in resolved_ids if items[sample_id]["dataset"] == dataset],
            resolved,
            deltas,
        )
        for dataset in DATASET_ORDER
    }
    grouped_all: dict[str, list[str]] = defaultdict(list)
    grouped_resolved: dict[str, list[str]] = defaultdict(list)
    for sample_id in ordered_ids:
        grouped_all[_stratum_key(items[sample_id])].append(sample_id)
        if sample_id in resolved:
            grouped_resolved[_stratum_key(items[sample_id])].append(sample_id)
    strata: list[dict[str, Any]] = []
    for key in sorted(grouped_all):
        ids = grouped_resolved.get(key, [])
        strata.append(
            {
                "stratum": key,
                "total_samples": len(grouped_all[key]),
                "consensus_samples": len(ids),
                "consensus_coverage": len(ids) / len(grouped_all[key]),
                "mappability_counts": {
                    label: sum(resolved[sample_id]["mappability"] == label for sample_id in ids)
                    for label in MAPPABILITY_LABELS
                },
                "weighted_mappability": (
                    mean(
                        _mapping_weight(str(resolved[sample_id]["mappability"]))
                        for sample_id in ids
                    )
                    if ids
                    else None
                ),
                "mean_delta": mean(deltas[sample_id] for sample_id in ids) if ids else None,
                "external_label_role": "convergent_evidence_not_gold",
            }
        )
    if len(strata) != 6:
        raise ValueError(f"expected six frozen strata, observed {len(strata)}")
    if all(row["consensus_samples"] > 0 for row in strata):
        association = _association(strata)
        association["estimable"] = True
        association["not_estimable_reason"] = None
    else:
        association = {
            "estimable": False,
            "not_estimable_reason": "one_or_more_frozen_strata_have_no_machine_consensus",
            "units": 6,
            "spearman_rho": None,
            "ols_slope": None,
            "ols_intercept": None,
            "ols_r_squared": None,
            "confirmatory_p_value": None,
            "interpretation": "retrospective_descriptive_association",
        }
    result = {
        "schema_version": "far-p6m-result-v1",
        "study_profile": PROFILE,
        "protocol_sha256": PROTOCOL_SHA256,
        "source_packet_manifest_sha256": source_sha,
        "samples": len(items),
        "dataset_counts": source_manifest["dataset_counts"],
        "jurors": [
            {
                "juror_id": manifest["juror_id"],
                "model_family": manifest["model_family"],
                "provider": manifest["provider"],
                "model": manifest["model"],
                "config_sha256": manifest["config_sha256"],
                "run_identity_sha256": manifest["run_identity_sha256"],
                "annotation_sha256": manifest["annotation_sha256"],
                "failed_attempts": manifest["failed_attempts"],
                "failed_attempt_sha256": manifest["failed_attempt_sha256"],
            }
            for manifest in manifests
        ],
        "juror_stability": stability,
        "view_agreement": view_agreement,
        "pair_sensitivity": pair_sensitivity,
        "dispositions": dict(sorted(dispositions.items())),
        "consensus_samples": len(resolved),
        "consensus_coverage": len(resolved) / len(items),
        "by_dataset": by_dataset,
        "combined_consensus": _group(resolved_ids, resolved, deltas),
        "external_label_strata": strata,
        "association": association,
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "consensus_rows_sha256": _stable_sha(consensus_rows),
        "qwen_prelabels_used": False,
        "machine_consensus_only": True,
        "human_annotation_replaced": False,
        "human_iaa_computed": False,
        "human_identity_verified": False,
        "publication_gold": False,
        "retrospective": True,
        "confirmatory_h4": False,
        "causal_analysis": False,
        "test_accessed": False,
    }
    return result, consensus_rows


def _fmt(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.4f}"


def report_text(result: dict[str, Any]) -> str:
    lines = [
        "# P6-M 跨家族机器本体稳定性审计",
        "",
        "> 本报告是机器评审下的 retrospective ontology-stability audit；不替代人工 P6，",
        "> 不报告 human IAA/human gold，不确认 H4。",
        "",
        "## 覆盖与稳定性",
        "",
        f"- Machine consensus: `{result['consensus_samples']}/{result['samples']}` "
        f"(`{result['consensus_coverage']:.4f}`)",
        f"- Dispositions: `{json.dumps(result['dispositions'], sort_keys=True)}`",
    ]
    for juror_id, row in result["juror_stability"].items():
        lines.append(
            f"- {juror_id} dual-view stability: "
            f"`{row['stable']}/{result['samples']}` (`{row['rate']:.4f}`)"
        )
    lines.extend(["", "## 模型面板一致性", ""])
    for view_id in VIEW_IDS:
        row = result["view_agreement"][view_id]
        lines.append(
            f"- {view_id} mappability Fleiss kappa: `{_fmt(row['mappability_fleiss_kappa'])}`"
        )
        lines.append(
            f"- {view_id} pairwise Cohen kappas: "
            f"`{json.dumps(row['mappability_pairwise_cohen_kappa'], sort_keys=True)}`"
        )
    lines.extend(
        [
            "",
            "## 共识层可映射性",
            "",
            "| 数据集 | consensus n | clean | partial | unmappable | weighted |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for dataset in DATASET_ORDER:
        row = result["by_dataset"][dataset]
        counts = row["counts"]
        lines.append(
            f"| {dataset} | {row['samples']} | {counts['clean']} | {counts['partial']} | "
            f"{counts['unmappable']} | {_fmt(row['weighted_mappability'])} |"
        )
    lines.extend(["", "## 外部标签分层 (收敛证据，不是金标)", ""])
    lines.extend(
        f"- `{row['stratum']}`: consensus `{row['consensus_samples']}/{row['total_samples']}`, "
        f"weighted `{_fmt(row['weighted_mappability'])}`, mean delta `{_fmt(row['mean_delta'])}`"
        for row in result["external_label_strata"]
    )
    lines.extend(
        [
            "",
            "## 描述性 association",
            "",
            f"- Estimable: `{str(result['association']['estimable']).lower()}`",
            f"- Spearman rho: `{_fmt(result['association']['spearman_rho'])}`",
            f"- OLS slope: `{_fmt(result['association']['ols_slope'])}`",
            f"- R²: `{_fmt(result['association']['ols_r_squared'])}`",
            "",
            "所有 contested 样本原样保留；没有第四模型仲裁，也没有把机器结果标成人工证据。",
            "",
        ]
    )
    return "\n".join(lines)


def analyze(
    packet_dir: Path,
    juror_dirs: list[Path],
    output_dir: Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass --overwrite")
        marker = output_dir / "manifest.json"
        if not marker.is_file():
            raise ValueError("refusing to overwrite a directory without a P6-M manifest")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result, rows = compute_result(packet_dir, juror_dirs)
    rows_path = output_dir / "consensus_rows.jsonl"
    result_path = output_dir / "type_mappability_machine.json"
    report_path = output_dir / "type_mappability_machine.md"
    write_jsonl(rows_path, rows)
    if result["consensus_rows_sha256"] != _stable_sha(rows):
        raise ValueError("P6-M consensus row stable fingerprint mismatch")
    write_json(result_path, result)
    report_path.write_text(report_text(result), encoding="utf-8")
    manifest = {
        "schema_version": "far-p6m-report-manifest-v1",
        "study_profile": PROFILE,
        "protocol_sha256": PROTOCOL_SHA256,
        "result_sha256": sha256_file(result_path),
        "report_sha256": sha256_file(report_path),
        "consensus_rows_file_sha256": sha256_file(rows_path),
        "human_annotation_replaced": False,
        "human_iaa_computed": False,
        "human_identity_verified": False,
        "publication_gold": False,
        "retrospective": True,
        "confirmatory_h4": False,
        "test_accessed": False,
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def verify_report(
    packet_dir: Path,
    juror_dirs: list[Path],
    report_dir: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        tracked_manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="far-p6m-verify-") as temporary:
            rebuilt_dir = Path(temporary) / "report"
            rebuilt_manifest = analyze(packet_dir, juror_dirs, rebuilt_dir)
            for filename in (
                "type_mappability_machine.json",
                "type_mappability_machine.md",
                "consensus_rows.jsonl",
            ):
                if (rebuilt_dir / filename).read_bytes() != (report_dir / filename).read_bytes():
                    errors.append(f"P6-M {filename} differs from deterministic recomputation")
            if rebuilt_manifest != tracked_manifest:
                errors.append("P6-M manifest differs from deterministic recomputation")
        for field, expected in (
            ("study_profile", PROFILE),
            ("protocol_sha256", PROTOCOL_SHA256),
            ("human_annotation_replaced", False),
            ("human_iaa_computed", False),
            ("human_identity_verified", False),
            ("publication_gold", False),
            ("retrospective", True),
            ("confirmatory_h4", False),
            ("test_accessed", False),
        ):
            if tracked_manifest.get(field) != expected:
                errors.append(f"P6-M manifest has invalid {field}")
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "far-p6m-report-audit-v1",
        "valid": not errors,
        "errors": errors,
        "study_profile": PROFILE,
        "human_annotation_replaced": False,
        "human_iaa_computed": False,
        "human_identity_verified": False,
        "publication_gold": False,
        "retrospective": True,
        "confirmatory_h4": False,
        "test_accessed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    annotate_parser = subparsers.add_parser("annotate")
    annotate_parser.add_argument("--packet-dir", type=Path, required=True)
    annotate_parser.add_argument("--config", type=Path, required=True)
    annotate_parser.add_argument("--output-dir", type=Path, required=True)
    annotate_parser.add_argument("--juror-id", choices=sorted(JUROR_SPECS), required=True)
    annotate_parser.add_argument("--overwrite", action="store_true")
    annotate_parser.add_argument("--resume", action="store_true")
    annotate_parser.add_argument("--limit", type=int)
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--packet-dir", type=Path, required=True)
    analyze_parser.add_argument("--juror-dir", type=Path, action="append", required=True)
    analyze_parser.add_argument("--output-dir", type=Path, required=True)
    analyze_parser.add_argument("--overwrite", action="store_true")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--packet-dir", type=Path, required=True)
    verify_parser.add_argument("--juror-dir", type=Path, action="append", required=True)
    verify_parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "annotate":
        result = annotate_juror(
            args.packet_dir,
            args.config,
            args.output_dir,
            juror_id=args.juror_id,
            overwrite=args.overwrite,
            resume=args.resume,
            limit=args.limit,
        )
    elif args.command == "analyze":
        result = analyze(
            args.packet_dir,
            args.juror_dir,
            args.output_dir,
            overwrite=args.overwrite,
        )
    else:
        result = verify_report(args.packet_dir, args.juror_dir, args.report_dir)
        if result["valid"] is not True:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
