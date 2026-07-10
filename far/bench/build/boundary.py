"""Build and verify pinned dev-only boundary benchmarks for WS3."""

from __future__ import annotations

import argparse
import csv
import json
import random
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from far.bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.paths import repository_root

ROOT = repository_root()
SEED = 2718
WIKI_REVISION = "c20e361f985ed480a659b35d98b49f2311fcd174"
WIKI_RAW_SHA256 = "cef10054f8aad3e36bca95a0873c2cbb0de8ab4d7b716cadacc5da7aa179ff2b"
WIKI_URL = (
    "https://huggingface.co/datasets/ibm-research/Wikipedia_contradict_benchmark/"
    f"resolve/{WIKI_REVISION}/WikiContradict_dataset_v1_rag_qa.csv?download=true"
)
CONFLICTS_REVISION = "81ba921dd684a93db41a7e9dda6b6a7c67348a88"
CONFLICTS_RAW_SHA256 = "14559d5c08fde057d7b46783e3345ee5852d6cf6a750f370dc072a0b957fac54"
CONFLICTS_URL = (
    "https://raw.githubusercontent.com/google-research-datasets/rag_conflicts/"
    f"{CONFLICTS_REVISION}/conflicts.jsonl"
)
WIKI_QUOTAS = {
    ("Explicit", "Different"): 72,
    ("Implicit (reasoning required)", "Different"): 41,
    ("Explicit", "Same"): 24,
    ("Implicit (reasoning required)", "Same"): 13,
}
CONFLICTS_QUOTAS = {
    "Conflict due to outdated information": 62,
    "Conflict due to misinformation": 5,
    "No conflict": 83,
}
RELEASE_FILES = {"tasks.jsonl", "corpus.jsonl", "manifest.json", "README.md"}


def _download(url: str, path: Path) -> None:
    request = Request(url, headers={"User-Agent": "FAR-boundary-import/1.0"})
    with urlopen(request, timeout=120) as response, path.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)


def _raw_path(
    *,
    source_file: Path | None,
    url: str,
    expected_sha256: str,
    temporary: Path,
) -> Path:
    path = source_file or temporary / "source"
    if source_file is None:
        _download(url, path)
    if sha256_file(path) != expected_sha256:
        raise ValueError("boundary source fingerprint mismatch")
    return path


def _sample_groups(
    groups: dict[Any, list[dict[str, Any]]],
    quotas: dict[Any, int],
) -> list[dict[str, Any]]:
    if set(groups) < set(quotas):
        raise ValueError("boundary source lacks a preregistered stratum")
    selected: list[dict[str, Any]] = []
    for offset, (key, quota) in enumerate(quotas.items()):
        values = sorted(groups[key], key=lambda row: str(row["_stable_id"]))
        if len(values) < quota:
            raise ValueError(f"boundary stratum {key!r} has fewer than {quota} rows")
        rng = random.Random(SEED + offset)
        selected.extend(rng.sample(values, quota))
    return sorted(selected, key=lambda row: str(row["_stable_id"]))


def _wiki_transform(raw_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with raw_path.open(encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    if len(source_rows) != 253:
        raise ValueError("WikiContradict source must contain 253 rows")
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(source_rows, start=1):
        stable_id = str(row.get("question_ID") or f"row-{index:04d}")
        normalized = {**row, "_stable_id": f"{stable_id}-{index:04d}"}
        groups[(str(row["contradictType"]), str(row["samepassage"]))].append(normalized)
    selected = _sample_groups(groups, WIKI_QUOTAS)
    tasks: list[dict[str, Any]] = []
    corpus: list[dict[str, Any]] = []
    for index, row in enumerate(selected, start=1):
        sample_id = f"WIKI{index:04d}"
        document_ids = [f"{sample_id}-D1", f"{sample_id}-D2"]
        answers = [str(row["answer1"]).strip(), str(row["answer2"]).strip()]
        if any(not item for item in answers) or answers[0].casefold() == answers[1].casefold():
            raise ValueError("WikiContradict selected row lacks two distinct answers")
        tasks.append(
            {
                "id": sample_id,
                "benchmark": "wikicontradict",
                "split": "dev",
                "question": str(row["question"]).strip(),
                "initial_answer": answers[0],
                "reference_answers": answers,
                "expected_mode": "cover_both_conflicting_answers",
                "conflict_type": "conflict",
                "document_ids": document_ids,
                "strata": {
                    "reasoning": str(row["contradictType"]),
                    "source_relation": str(row["samepassage"]),
                },
                "source_id": str(row["_stable_id"]),
                "label_provenance": "wikicontradict_human_annotation",
            }
        )
        for doc_index, field in enumerate(("context1", "context2"), start=1):
            corpus.append(
                {
                    "doc_id": document_ids[doc_index - 1],
                    "title": str(row["WikipediaArticleTitle"]).strip()
                    or f"WikiContradict {sample_id}",
                    "content": str(row[field]).strip(),
                    "source": "Wikipedia",
                    "url": str(row["url"]).strip() or None,
                    "date": None,
                    "author": "Wikipedia contributors",
                    "license": "MIT dataset release; source text from Wikipedia",
                    "entities": [],
                    "metadata": {
                        "sample_id": sample_id,
                        "answer": answers[doc_index - 1],
                        "side": doc_index,
                    },
                }
            )
    return tasks, corpus


def _conflicts_transform(raw_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_rows = read_jsonl(raw_path)
    if len(source_rows) != 458:
        raise ValueError("Google CONFLICTS source must contain 458 rows")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(source_rows, start=1):
        conflict_type = str(row["conflict_type"])
        answer = str(row.get("correct_answer", "")).strip()
        if conflict_type in CONFLICTS_QUOTAS and answer:
            groups[conflict_type].append({**row, "_stable_id": f"source-{index:04d}"})
    selected = _sample_groups(groups, CONFLICTS_QUOTAS)
    type_map = {
        "Conflict due to outdated information": "temporal",
        "Conflict due to misinformation": "source_reliability",
        "No conflict": "no_conflict",
    }
    tasks: list[dict[str, Any]] = []
    corpus: list[dict[str, Any]] = []
    for index, row in enumerate(selected, start=1):
        sample_id = f"GCON{index:04d}"
        search_results = list(row.get("search_results", []))
        if not search_results:
            raise ValueError("Google CONFLICTS selected row has no search results")
        document_ids: list[str] = []
        for doc_index, document in enumerate(search_results, start=1):
            content = str(document.get("short_text") or document.get("snippet") or "").strip()
            if not content:
                continue
            doc_id = f"{sample_id}-D{doc_index:02d}"
            document_ids.append(doc_id)
            corpus.append(
                {
                    "doc_id": doc_id,
                    "title": str(document.get("title") or f"CONFLICTS {sample_id}"),
                    "content": content,
                    "source": str(row.get("source") or "google_rag_conflicts"),
                    "url": document.get("url"),
                    "date": document.get("date"),
                    "author": None,
                    "license": "Apache-2.0 dataset release",
                    "entities": [],
                    "metadata": {
                        "sample_id": sample_id,
                        "upstream_conflict_type": row["conflict_type"],
                    },
                }
            )
        if not document_ids:
            raise ValueError("Google CONFLICTS selected row has no usable short text")
        answer = str(row["correct_answer"]).strip()
        tasks.append(
            {
                "id": sample_id,
                "benchmark": "google_rag_conflicts",
                "split": "dev",
                "question": str(row["question"]).strip(),
                "initial_answer": answer,
                "reference_answers": [answer],
                "expected_mode": "preserve_correct_answer",
                "conflict_type": type_map[str(row["conflict_type"])],
                "document_ids": document_ids,
                "strata": {
                    "upstream_conflict_type": str(row["conflict_type"]),
                    "source": str(row.get("source") or "unknown"),
                },
                "source_id": str(row["_stable_id"]),
                "label_provenance": "google_conflicts_upstream_annotation",
            }
        )
    return tasks, corpus


def _readme(name: str, source_url: str, license_name: str) -> str:
    return (
        f"# FAR {name} boundary dev import\n\n"
        "This directory is a deterministic 150-item development diagnostic for WS3. "
        "It is not an official test run, human IAA, or publication gold created by FAR.\n\n"
        f"- Source: {source_url}\n"
        f"- Dataset license: {license_name}\n"
        f"- Sampling seed: {SEED}\n"
        "- Held-out/test access: false\n"
    )


def build_boundary(
    kind: str,
    output_dir: Path,
    *,
    source_file: Path | None = None,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"{output_dir} is nonempty")
    if kind == "wiki":
        url = WIKI_URL
        raw_sha = WIKI_RAW_SHA256
        revision = WIKI_REVISION
        name = "WikiContradict"
        license_name = "MIT"
        transform = _wiki_transform
        quotas: dict[Any, int] = WIKI_QUOTAS
    elif kind == "conflicts":
        url = CONFLICTS_URL
        raw_sha = CONFLICTS_RAW_SHA256
        revision = CONFLICTS_REVISION
        name = "Google CONFLICTS"
        license_name = "Apache-2.0"
        transform = _conflicts_transform
        quotas = CONFLICTS_QUOTAS
    else:
        raise ValueError(f"unknown boundary import kind: {kind}")
    with tempfile.TemporaryDirectory(prefix="far-boundary-source-") as temporary:
        raw_path = _raw_path(
            source_file=source_file,
            url=url,
            expected_sha256=raw_sha,
            temporary=Path(temporary),
        )
        tasks, corpus = transform(raw_path)
    if len(tasks) != 150 or len({str(row["id"]) for row in tasks}) != 150:
        raise ValueError("boundary import must contain 150 unique tasks")
    if any(row.get("split") != "dev" for row in tasks):
        raise ValueError("boundary import must be dev-only")
    output_dir.mkdir(parents=True, exist_ok=False)
    write_jsonl(output_dir / "tasks.jsonl", tasks)
    write_jsonl(output_dir / "corpus.jsonl", corpus)
    (output_dir / "README.md").write_text(
        _readme(name, url, license_name),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "far-boundary-import-v1",
        "kind": kind,
        "name": name,
        "source_url": url,
        "source_revision": revision,
        "source_sha256": raw_sha,
        "license": license_name,
        "sampling_seed": SEED,
        "sampling_quotas": {str(key): value for key, value in quotas.items()},
        "samples": 150,
        "documents": len(corpus),
        "split": "dev",
        "task_sha256": sha256_file(output_dir / "tasks.jsonl"),
        "corpus_sha256": sha256_file(output_dir / "corpus.jsonl"),
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def verify_boundary(
    kind: str,
    output_dir: Path,
    *,
    source_file: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="far-boundary-verify-") as temporary:
            rebuilt = Path(temporary) / "release"
            build_boundary(kind, rebuilt, source_file=source_file)
            actual_files = (
                {path.name for path in output_dir.iterdir() if path.is_file()}
                if output_dir.is_dir()
                else set()
            )
            if actual_files != RELEASE_FILES:
                errors.append("boundary release file set is not exact")
            for name in RELEASE_FILES:
                if (output_dir / name).read_bytes() != (rebuilt / name).read_bytes():
                    errors.append(f"boundary artifact differs from recomputation: {name}")
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        tasks = read_jsonl(output_dir / "tasks.jsonl")
        corpus = read_jsonl(output_dir / "corpus.jsonl")
        if manifest.get("samples") != 150 or len(tasks) != 150:
            errors.append("boundary release does not contain 150 tasks")
        if {str(row.get("split")) for row in tasks} != {"dev"}:
            errors.append("boundary release is not dev-only")
        referenced = {str(doc_id) for row in tasks for doc_id in row["document_ids"]}
        observed = {str(row["doc_id"]) for row in corpus}
        if referenced != observed:
            errors.append("boundary task/corpus references are not exact")
        if manifest.get("test_accessed") is not False:
            errors.append("boundary manifest claims test access")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "far-boundary-import-audit-v1",
        "kind": kind,
        "valid": not errors,
        "errors": errors,
        "samples": 150 if not errors else None,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "verify"):
        child = subparsers.add_parser(command)
        child.add_argument("--kind", choices=("wiki", "conflicts"), required=True)
        child.add_argument("--output-dir", type=Path, required=True)
        child.add_argument("--source-file", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        result = build_boundary(args.kind, args.output_dir, source_file=args.source_file)
    else:
        result = verify_boundary(args.kind, args.output_dir, source_file=args.source_file)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "verify" and result.get("valid") is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
