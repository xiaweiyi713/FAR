"""Deterministically import and verify the pinned RAMDocs external benchmark."""

from __future__ import annotations

import argparse
import json
import random
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from experiments.protocol_2plus4 import (
    PROTOCOL_ORIGINAL_SHA256,
    PROTOCOL_PHASE_A_SHA256,
    verify_active_protocol,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "bench" / "external" / "ramdocs_v1"
DATASET_ID = "HanNight/RAMDocs"
UPSTREAM_REVISION = "9c041bfd158c603b615883d9a931b00cbc141494"
UPSTREAM_CODE_COMMIT = "d44454c9ebb0bf513d8236a03decc9fb58704cad"
UPSTREAM_FILENAME = "RAMDocs_test.jsonl"
UPSTREAM_SHA256 = "c67f699c97349f00cf1bd08d1dbf8ca1d0cc38c306715c93a10a4f961dcf28b7"
SPLIT_SEED = 1729
DEV_SAMPLES = 350


def _download(destination: Path) -> None:
    url = (
        f"https://huggingface.co/datasets/{DATASET_ID}/resolve/"
        f"{UPSTREAM_REVISION}/{UPSTREAM_FILENAME}"
    )
    request = Request(url, headers={"User-Agent": "FAR-RAMDocs-import/1.0"})
    with urlopen(request, timeout=60) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _validate_source(path: Path) -> list[dict[str, Any]]:
    if sha256_file(path) != UPSTREAM_SHA256:
        raise ValueError("RAMDocs source fingerprint does not match the pinned revision")
    rows = read_jsonl(path)
    if len(rows) != 500:
        raise ValueError(f"expected 500 RAMDocs rows, found {len(rows)}")
    required = {"question", "documents", "gold_answers", "wrong_answers", "disambig_entity"}
    for index, row in enumerate(rows, start=1):
        if set(row) != required:
            raise ValueError(f"RAMDocs row {index} has unexpected fields")
        if not str(row["question"]).strip() or not row["gold_answers"]:
            raise ValueError(f"RAMDocs row {index} lacks a question or gold answer")
        if not isinstance(row["documents"], list) or not row["documents"]:
            raise ValueError(f"RAMDocs row {index} has no documents")
        for document in row["documents"]:
            if document.get("type") not in {"correct", "misinfo", "noise"}:
                raise ValueError(f"RAMDocs row {index} has an invalid document type")
            if not str(document.get("text", "")).strip():
                raise ValueError(f"RAMDocs row {index} has an empty document")
    return rows


def _split_ids(sample_ids: list[str]) -> tuple[set[str], set[str]]:
    shuffled = list(sample_ids)
    random.Random(SPLIT_SEED).shuffle(shuffled)
    dev = set(shuffled[:DEV_SAMPLES])
    return dev, set(shuffled[DEV_SAMPLES:])


def _card() -> str:
    return """# RAMDocs v1 external evaluation slice

This directory is a deterministic import of `HanNight/RAMDocs` at Hugging Face
revision `9c041bfd158c603b615883d9a931b00cbc141494` (MIT). It contains 500
questions and a locally frozen 350/150 dev/test partition using seed 1729.

RAMDocs is independently published and upstream-labelled, but it is not treated
as independently double-annotated human gold in FAR. Valid answers originate in
AmbigDocs; misinformation documents are constructed by entity/answer replacement
and noise documents are retrieved. The held-out split is locally fingerprinted,
not externally custodied.

Rebuild and verify with:

```bash
uv run falsirag-build-ramdocs build --output-dir bench/external/ramdocs_v1
uv run falsirag-build-ramdocs verify --output-dir bench/external/ramdocs_v1
```
"""


def _licenses() -> str:
    return """# Upstream license record

- Dataset: `HanNight/RAMDocs`
- Pinned revision: `9c041bfd158c603b615883d9a931b00cbc141494`
- Upstream code commit: `d44454c9ebb0bf513d8236a03decc9fb58704cad`
- Declared license: MIT
- Dataset URL: https://huggingface.co/datasets/HanNight/RAMDocs
- Code URL: https://github.com/HanNight/RAMDocs

The imported records retain upstream provenance in `manifest.json`. See the
upstream repositories for the complete MIT license text and dataset card.
"""


def build_ramdocs(
    output_dir: Path,
    *,
    source_file: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Build the pinned external slice without evaluating the held-out labels."""

    verify_active_protocol()
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass --overwrite to replace it")
        manifest_path = output_dir / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError("refusing to overwrite a directory without a RAMDocs manifest")
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("schema_version") != "far-ramdocs-import-v1":
            raise ValueError("refusing to overwrite a directory not owned by this importer")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if source_file is None:
        with tempfile.TemporaryDirectory(prefix="far-ramdocs-") as temporary:
            downloaded = Path(temporary) / UPSTREAM_FILENAME
            _download(downloaded)
            rows = _validate_source(downloaded)
    else:
        rows = _validate_source(source_file)

    sample_ids = [f"RAM{index:04d}" for index in range(1, len(rows) + 1)]
    dev_ids, test_ids = _split_ids(sample_ids)
    corpus: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    type_counts: Counter[str] = Counter()
    for sample_id, row in zip(sample_ids, rows, strict=True):
        document_ids: list[str] = []
        for doc_index, document in enumerate(row["documents"], start=1):
            doc_id = f"{sample_id}-D{doc_index:02d}"
            document_ids.append(doc_id)
            document_type = str(document["type"])
            type_counts[document_type] += 1
            corpus.append(
                {
                    "doc_id": doc_id,
                    "title": f"RAMDocs evidence for {sample_id}",
                    "content": str(document["text"]),
                    "source": "ramdocs_anonymous_document",
                    "url": None,
                    "date": None,
                    "author": "HanNight/RAMDocs",
                    "license": "MIT",
                    "entities": [str(item) for item in row["disambig_entity"]],
                    "metadata": {
                        "sample_id": sample_id,
                        "document_type": document_type,
                        "upstream_answer": str(document.get("answer", "")),
                    },
                }
            )
        split = "dev" if sample_id in dev_ids else "test"
        tasks.append(
            {
                "id": sample_id,
                "question": str(row["question"]),
                "initial_answer": "",
                "split": split,
                "category": (
                    "ambiguity_misinformation"
                    if any(doc["type"] == "misinfo" for doc in row["documents"])
                    else "ambiguity_noise"
                ),
                "document_ids": document_ids,
                "gold_answers": [str(item) for item in row["gold_answers"]],
                "wrong_answers": [str(item) for item in row["wrong_answers"]],
                "disambiguated_entities": [str(item) for item in row["disambig_entity"]],
                "label_provenance": "ramdocs_upstream_answers_and_document_types",
            }
        )

    write_jsonl(output_dir / "corpus.jsonl", corpus)
    write_jsonl(output_dir / "tasks.jsonl", tasks)
    write_jsonl(
        output_dir / "splits" / "dev.jsonl",
        [row for row in tasks if row["split"] == "dev"],
    )
    write_jsonl(
        output_dir / "splits" / "test_inputs.jsonl",
        [
            {"id": row["id"], "question": row["question"], "split": "test"}
            for row in tasks
            if row["split"] == "test"
        ],
    )
    (output_dir / "CARD.md").write_text(_card(), encoding="utf-8")
    (output_dir / "LICENSES.md").write_text(_licenses(), encoding="utf-8")
    files = {
        path.relative_to(output_dir).as_posix(): sha256_file(path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    manifest: dict[str, Any] = {
        "schema_version": "far-ramdocs-import-v1",
        "dataset_id": DATASET_ID,
        "dataset_revision": UPSTREAM_REVISION,
        "upstream_code_commit": UPSTREAM_CODE_COMMIT,
        "upstream_filename": UPSTREAM_FILENAME,
        "upstream_sha256": UPSTREAM_SHA256,
        "license": "MIT",
        "protocol_fingerprint": PROTOCOL_PHASE_A_SHA256,
        "protocol_original_fingerprint": PROTOCOL_ORIGINAL_SHA256,
        "counts": {
            "questions": len(tasks),
            "documents": len(corpus),
            "dev": len(dev_ids),
            "test": len(test_ids),
            "document_types": dict(sorted(type_counts.items())),
        },
        "split": {
            "method": "python-random-shuffle-v1",
            "seed": SPLIT_SEED,
            "dev_samples": DEV_SAMPLES,
            "group_key": "question/sample_id",
            "test_frozen": True,
        },
        "evidence_status": "external_upstream_labeled_not_independent_human_iaa",
        "publication_gold": False,
        "externally_held_blind": False,
        "files": files,
    }
    write_json(output_dir / "manifest.json", manifest)
    audit = verify_ramdocs(output_dir)
    if not audit["valid"]:
        raise ValueError(f"created RAMDocs import is invalid: {audit['errors']}")
    return manifest


def verify_ramdocs(output_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        verify_active_protocol()
    except ValueError as exc:
        errors.append(str(exc))
    try:
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return {
            "schema_version": "far-ramdocs-import-audit-v1",
            "valid": False,
            "errors": [str(exc)],
        }
    if manifest.get("schema_version") != "far-ramdocs-import-v1":
        errors.append("unsupported manifest schema")
    expected_flags = {
        "dataset_revision": UPSTREAM_REVISION,
        "upstream_sha256": UPSTREAM_SHA256,
        "protocol_fingerprint": PROTOCOL_PHASE_A_SHA256,
        "publication_gold": False,
        "externally_held_blind": False,
    }
    for key, expected in expected_flags.items():
        if manifest.get(key) != expected:
            errors.append(f"unsafe or stale manifest field: {key}")
    files = manifest.get("files")
    if not isinstance(files, dict):
        files = {}
        errors.append("manifest has no file fingerprint map")
    actual = {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if set(files) != actual:
        errors.append("RAMDocs file set differs from manifest")
    for name, fingerprint in files.items():
        path = output_dir / name
        if not path.is_file() or path.is_symlink() or sha256_file(path) != fingerprint:
            errors.append(f"RAMDocs file fingerprint mismatch: {name}")
    try:
        tasks = read_jsonl(output_dir / "tasks.jsonl")
        corpus = read_jsonl(output_dir / "corpus.jsonl")
        dev = read_jsonl(output_dir / "splits" / "dev.jsonl")
        test_inputs = read_jsonl(output_dir / "splits" / "test_inputs.jsonl")
        task_ids = [str(row["id"]) for row in tasks]
        if len(tasks) != 500 or len(set(task_ids)) != 500:
            errors.append("RAMDocs tasks must contain 500 unique samples")
        if len(dev) != 350 or len(test_inputs) != 150:
            errors.append("RAMDocs split must contain 350 dev and 150 test samples")
        if any(set(row) != {"id", "question", "split"} for row in test_inputs):
            errors.append("RAMDocs test inputs expose fields beyond id/question/split")
        corpus_ids = {str(row["doc_id"]) for row in corpus}
        if any(not set(map(str, row["document_ids"])).issubset(corpus_ids) for row in tasks):
            errors.append("RAMDocs task references a missing document")
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "far-ramdocs-import-audit-v1",
        "valid": not errors,
        "errors": errors,
        "questions": len(tasks) if "tasks" in locals() else 0,
        "documents": len(corpus) if "corpus" in locals() else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    build_parser.add_argument("--source-file", type=Path)
    build_parser.add_argument("--overwrite", action="store_true")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = (
        build_ramdocs(args.output_dir, source_file=args.source_file, overwrite=args.overwrite)
        if args.command == "build"
        else verify_ramdocs(args.output_dir)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "verify" and not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
