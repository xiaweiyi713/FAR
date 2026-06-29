"""Create a gold-free FalsiRAG test bundle for an external custodian."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from bench.schema import BLIND_TEST_ALLOWED_FIELDS

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1]


def build(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    if data_dir.resolve() == output_dir.resolve():
        raise ValueError("blind bundle output must differ from the source data directory")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("blind bundle output directory must be empty")

    corpus_path = data_dir / "corpus.jsonl"
    test_input_path = data_dir / "splits" / "test_inputs.jsonl"
    test_rows = read_jsonl(test_input_path)
    if not test_rows:
        raise ValueError("blind test input file must not be empty")
    if any(set(row) != BLIND_TEST_ALLOWED_FIELDS for row in test_rows):
        raise ValueError("test_inputs contains fields outside the blind operational schema")
    if any(row.get("split") != "test" for row in test_rows):
        raise ValueError("test_inputs contains a non-test row")
    ids = [str(row["id"]) for row in test_rows]
    if len(set(ids)) != len(ids):
        raise ValueError("test_inputs contains duplicate IDs")

    corpus_rows = read_jsonl(corpus_path)
    public_corpus_fields = (
        "doc_id",
        "title",
        "content",
        "source",
        "date",
        "author",
        "url",
        "license",
    )
    blind_corpus = [
        {field: row[field] for field in public_corpus_fields if field in row} for row in corpus_rows
    ]

    (output_dir / "splits").mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "corpus.jsonl", blind_corpus)
    write_jsonl(output_dir / "splits" / "test_inputs.jsonl", test_rows)
    manifest = {
        "schema_version": "falsirag-blind-bundle-v1",
        "gold_included": False,
        "allowed_test_fields": sorted(BLIND_TEST_ALLOWED_FIELDS),
        "samples": len(test_rows),
        "categories": sorted({str(row["category"]) for row in test_rows}),
        "public_corpus_fields": list(public_corpus_fields),
        "source_corpus_sha256": sha256_file(corpus_path),
        "files": {
            "corpus.jsonl": sha256_file(output_dir / "corpus.jsonl"),
            "splits/test_inputs.jsonl": sha256_file(output_dir / "splits" / "test_inputs.jsonl"),
        },
        "instructions": (
            "Run predictions with --split test --allow-test. Return prediction bundles and "
            "manifests to the trusted scorer; do not request or add gold files here."
        ),
    }
    write_json(output_dir / "blind_bundle_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = build(args.data_dir, args.output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
