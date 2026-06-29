"""Import VeraRAG's fingerprinted FEVER pair candidates as a non-gold external slice."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl

DEFAULT_SOURCE = Path(
    os.getenv(
        "VERARAG_FEVER_DIR",
        str(Path(__file__).resolve().parents[3] / "VeraRAG/data/external/fever_pair_candidates_v1"),
    )
)
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "external" / "fever_pair_candidates_v1"


def import_slice(source_dir: Path, output_dir: Path) -> dict[str, object]:
    upstream_manifest = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
    if upstream_manifest.get("annotation_protocol", {}).get("machine_seed_is_gold") is not False:
        raise ValueError("FEVER slice must explicitly state that machine seeds are not gold")
    corpus = read_jsonl(source_dir / "corpus.jsonl")
    questions = read_jsonl(source_dir / "questions.jsonl")
    write_jsonl(output_dir / "corpus.jsonl", corpus)
    write_jsonl(output_dir / "questions.jsonl", questions)
    write_json(output_dir / "upstream_manifest.json", upstream_manifest)
    manifest: dict[str, object] = {
        "schema_version": "falsirag-external-slice-v1",
        "dataset_id": "fever-pair-candidates-v1",
        "status": "candidate_pending_independent_annotation",
        "publication_gold": False,
        "counts": {"questions": len(questions), "documents": len(corpus)},
        "licenses": upstream_manifest.get("license", []),
        "upstream": upstream_manifest.get("upstream", {}),
        "fingerprints": {
            "corpus_sha256": sha256_file(output_dir / "corpus.jsonl"),
            "questions_sha256": sha256_file(output_dir / "questions.jsonl"),
            "upstream_manifest_sha256": sha256_file(output_dir / "upstream_manifest.json"),
        },
        "promotion_contract": {
            "minimum_annotators": 2,
            "adjudication_required": True,
            "minimum_binary_kappa": 0.6,
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = import_slice(args.source_dir, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
