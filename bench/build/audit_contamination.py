"""Audit benchmark text against explicitly supplied local reference corpora."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _ngrams(text: str, n: int = 5) -> set[str]:
    normalized = _normalize(text)
    return {normalized[index : index + n] for index in range(max(0, len(normalized) - n + 1))}


def _reference_text(row: dict[str, Any]) -> str:
    for key in ("content", "text", "text_span", "question", "claim"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return json.dumps(row, ensure_ascii=False, sort_keys=True)


def audit(
    benchmark_path: Path,
    reference_paths: list[Path],
    *,
    near_duplicate_threshold: float = 0.8,
) -> dict[str, Any]:
    if not reference_paths:
        raise ValueError("at least one explicit reference corpus is required")
    samples = read_jsonl(benchmark_path)
    references = [
        (str(path), index, _reference_text(row))
        for path in reference_paths
        for index, row in enumerate(read_jsonl(path), start=1)
    ]
    reference_features = [
        (path, index, _normalize(text), _ngrams(text)) for path, index, text in references
    ]
    exact_matches: list[dict[str, Any]] = []
    near_matches: list[dict[str, Any]] = []
    for sample in samples:
        fields = {
            "question": sample["question"],
            "initial_answer": sample["initial_answer"],
        }
        for field_name, text in fields.items():
            normalized = _normalize(text)
            grams = _ngrams(text)
            for path, line_number, reference, reference_grams in reference_features:
                if normalized and normalized in reference:
                    exact_matches.append(
                        {
                            "sample_id": sample["id"],
                            "field": field_name,
                            "reference": path,
                            "line": line_number,
                        }
                    )
                    continue
                union = grams | reference_grams
                similarity = len(grams & reference_grams) / len(union) if union else 0.0
                if similarity >= near_duplicate_threshold:
                    near_matches.append(
                        {
                            "sample_id": sample["id"],
                            "field": field_name,
                            "reference": path,
                            "line": line_number,
                            "character_5gram_jaccard": round(similarity, 4),
                        }
                    )
    return {
        "schema_version": "falsirag-contamination-audit-v1",
        "benchmark_sha256": sha256_file(benchmark_path),
        "references": [
            {"path": str(path), "sha256": sha256_file(path)} for path in reference_paths
        ],
        "method": "normalized exact substring plus character-5gram Jaccard",
        "near_duplicate_threshold": near_duplicate_threshold,
        "exact_matches": exact_matches,
        "near_matches": near_matches,
        "conclusion": (
            "potential_overlap_requires_review"
            if exact_matches or near_matches
            else "no_overlap_detected_in_supplied_references"
        ),
        "limitation": "This audit covers only the explicitly supplied reference corpora.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--reference", type=Path, action="append", required=True)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.benchmark, args.reference, near_duplicate_threshold=args.threshold)
    write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
