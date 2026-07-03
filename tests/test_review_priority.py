from __future__ import annotations

import csv
from pathlib import Path

from experiments.review_priority import FIELDNAMES, build_priority_rows, write_priority_csv

ROOT = Path(__file__).resolve().parents[1]
CONSENSUS_ROWS = ROOT / "diagnostics/solo_v1/machine_annotation/machine_consensus_rows.jsonl"
PRIORITY_CSV = ROOT / "reports/solo_human_review_priority.csv"


def _priority_rows(path: Path = PRIORITY_CSV) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_review_priority_table_matches_tracked_machine_consensus(tmp_path: Path) -> None:
    generated_rows = build_priority_rows(CONSENSUS_ROWS)
    generated = tmp_path / "priority.csv"
    write_priority_csv(generated_rows, generated)

    assert generated.read_text(encoding="utf-8") == PRIORITY_CSV.read_text(encoding="utf-8")


def test_review_priority_table_is_disputed_only_and_stably_ranked() -> None:
    rows = _priority_rows()

    assert len(rows) == 122
    assert list(rows[0]) == FIELDNAMES
    assert [int(row["rank"]) for row in rows] == list(range(1, 123))
    assert {row["disposition"] for row in rows} == {"machine_disputed"}
    assert {row["requires_claim_limitation"] for row in rows} == {"true"}
    assert all(int(row["exact_joint_matches"]) == 0 for row in rows)
    assert all(int(row["priority_score"]) > 0 for row in rows)

    sort_key = [(-int(row["priority_score"]), row["category"], row["sample_id"]) for row in rows]
    assert sort_key == sorted(sort_key)


def test_review_priority_table_does_not_ship_revised_answers_or_gold_claims() -> None:
    text = PRIORITY_CSV.read_text(encoding="utf-8")

    forbidden_fragments = [
        "revised_answer",
        "revised_answer_sha256",
        "publication_gold,true",
        "human_iaa",
        "cohen",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in text
