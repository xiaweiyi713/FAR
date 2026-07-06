from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, cast

from bench.build.boundary import (
    CONFLICTS_QUOTAS,
    WIKI_QUOTAS,
    _conflicts_transform,
    _wiki_transform,
    verify_boundary,
)


def test_wikicontradict_transform_freezes_150_stratified_rows(tmp_path: Path) -> None:
    source = tmp_path / "wiki.csv"
    fields = [
        "question_ID",
        "question",
        "context1",
        "context2",
        "answer1",
        "answer2",
        "contradictType",
        "samepassage",
        "merged_context",
        "ref_answer",
        "WikipediaArticleTitle",
        "url",
    ]
    rows = []
    index = 0
    source_counts = {
        ("Explicit", "Different"): 121,
        ("Implicit (reasoning required)", "Different"): 69,
        ("Explicit", "Same"): 40,
        ("Implicit (reasoning required)", "Same"): 23,
    }
    for (reasoning, relation), count in source_counts.items():
        for _ in range(count):
            index += 1
            rows.append(
                {
                    "question_ID": f"Q{index}",
                    "question": f"Question {index}?",
                    "context1": f"Context A {index}",
                    "context2": f"Context B {index}",
                    "answer1": f"Alpha {index}",
                    "answer2": f"Beta {index}",
                    "contradictType": reasoning,
                    "samepassage": relation,
                    "merged_context": "",
                    "ref_answer": "",
                    "WikipediaArticleTitle": f"Title {index}",
                    "url": "https://example.com",
                }
            )
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tasks: list[dict[str, Any]]
    corpus: list[dict[str, Any]]
    tasks, corpus = _wiki_transform(source)
    assert len(tasks) == 150
    assert len(corpus) == 300
    observed: dict[tuple[str, str], int] = {}
    for row in tasks:
        key = (row["strata"]["reasoning"], row["strata"]["source_relation"])
        observed[key] = observed.get(key, 0) + 1
    assert observed == WIKI_QUOTAS


def test_google_conflicts_transform_uses_only_gold_answer_strata(tmp_path: Path) -> None:
    source = tmp_path / "conflicts.jsonl"
    counts = {
        "Conflict due to outdated information": 62,
        "Conflict due to misinformation": 5,
        "No conflict": 161,
        "Complementary information": 115,
        "Conflicting opinions and research outcomes": 115,
    }
    with source.open("w", encoding="utf-8") as handle:
        index = 0
        for conflict_type, count in counts.items():
            for _ in range(count):
                index += 1
                answer = (
                    f"Answer {index}"
                    if conflict_type
                    in {
                        "Conflict due to outdated information",
                        "Conflict due to misinformation",
                        "No conflict",
                    }
                    else ""
                )
                row = {
                    "source": "synthetic",
                    "question": f"Question {index}?",
                    "search_results": [
                        {
                            "title": "Title",
                            "url": "https://example.com",
                            "date": None,
                            "short_text": f"Evidence {index}",
                        }
                    ],
                    "conflict_type": conflict_type,
                    "correct_answer": answer,
                }
                handle.write(json.dumps(row) + "\n")
    tasks: list[dict[str, Any]]
    corpus: list[dict[str, Any]]
    tasks, corpus = _conflicts_transform(source)
    assert len(tasks) == 150
    assert len(corpus) == 150
    observed: dict[str, int] = {}
    for row in tasks:
        strata = cast(dict[str, str], row["strata"])
        key = strata["upstream_conflict_type"]
        observed[key] = observed.get(key, 0) + 1
    assert observed == CONFLICTS_QUOTAS


def test_boundary_verifier_fails_closed_without_release(tmp_path: Path) -> None:
    audit = verify_boundary("wiki", tmp_path / "missing", source_file=tmp_path / "source")
    assert audit["valid"] is False
    assert audit["test_accessed"] is False
