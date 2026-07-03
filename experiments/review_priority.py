"""Build a public review-priority table from machine-consensus audit rows.

The output is a triage aid for scarce future review time. It deliberately does
not relabel examples, expose revised-answer text, or convert machine signals
into human gold.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

PRIORITY_SCHEMA_VERSION = "far-machine-review-priority-v1"

FIELDNAMES = [
    "rank",
    "sample_id",
    "category",
    "priority_score",
    "disposition",
    "non_abstained_signals",
    "exact_joint_matches",
    "reference_conflict_type",
    "reference_revision_action",
    "llm_conflict_type",
    "llm_revision_action",
    "llm_abstained",
    "llm_exact_joint_match",
    "rules_conflict_type",
    "rules_revision_action",
    "rules_abstained",
    "rules_exact_joint_match",
    "requires_claim_limitation",
    "triage_reason",
]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    return rows


def _first_signal(row: dict[str, Any], kind: str) -> dict[str, Any] | None:
    signals = row.get("machine_signals")
    if not isinstance(signals, list):
        return None
    for signal in signals:
        if isinstance(signal, dict) and signal.get("kind") == kind:
            return signal
    return None


def _signal_text(signal: dict[str, Any] | None, key: str) -> str:
    if signal is None:
        return ""
    value = signal.get(key, "")
    return str(value)


def _signal_bool(signal: dict[str, Any] | None, key: str) -> str:
    if signal is None:
        return ""
    return str(bool(signal.get(key))).lower()


def _non_abstained_disagreements(row: dict[str, Any]) -> int:
    reference = row.get("reference", {})
    if not isinstance(reference, dict):
        reference = {}
    expected = (
        str(reference.get("conflict_type", "")),
        str(reference.get("revision_action", "")),
    )
    count = 0
    for signal in row.get("machine_signals", []):
        if not isinstance(signal, dict) or signal.get("abstained"):
            continue
        observed = (
            str(signal.get("conflict_type", "")),
            str(signal.get("revision_action", "")),
        )
        count += observed != expected
    return count


def priority_score(row: dict[str, Any]) -> int:
    """Score rows so strongest machine/reference conflicts sort first."""

    exact_matches = int(row.get("exact_joint_matches", 0))
    non_abstained = int(row.get("non_abstained_signals", 0))
    disagreements = _non_abstained_disagreements(row)
    score = 0
    if row.get("disposition") == "machine_disputed":
        score += 100
    if row.get("requires_claim_limitation"):
        score += 10
    score += max(0, 2 - exact_matches) * 20
    score += non_abstained * 5
    score += disagreements * 3
    return score


def triage_reason(row: dict[str, Any]) -> str:
    non_abstained = int(row.get("non_abstained_signals", 0))
    disagreements = _non_abstained_disagreements(row)
    if row.get("disposition") != "machine_disputed":
        return "machine-confirmed row retained only because confirmed rows were requested"
    if non_abstained >= 2 and disagreements >= 2:
        return "two non-abstaining machine signals disagree with the construction reference"
    if non_abstained == 1 and disagreements == 1:
        return "one non-abstaining machine signal disagrees while the other abstains"
    return "machine audit marks the row disputed; inspect before using as gold"


def build_priority_rows(
    consensus_rows_path: Path,
    *,
    include_confirmed: bool = False,
) -> list[dict[str, str]]:
    """Return deterministic CSV-ready review-priority rows."""

    source_rows = _read_jsonl(consensus_rows_path)
    selected = [
        row
        for row in source_rows
        if include_confirmed or row.get("disposition") == "machine_disputed"
    ]
    selected.sort(
        key=lambda row: (
            -priority_score(row),
            str(row.get("category", "")),
            str(row.get("sample_id", "")),
        )
    )

    output: list[dict[str, str]] = []
    for rank, row in enumerate(selected, start=1):
        reference = row.get("reference", {})
        if not isinstance(reference, dict):
            reference = {}
        llm = _first_signal(row, "llm_preannotation")
        rules = _first_signal(row, "deterministic_weak_label")
        output.append(
            {
                "rank": str(rank),
                "sample_id": str(row.get("sample_id", "")),
                "category": str(row.get("category", "")),
                "priority_score": str(priority_score(row)),
                "disposition": str(row.get("disposition", "")),
                "non_abstained_signals": str(row.get("non_abstained_signals", "")),
                "exact_joint_matches": str(row.get("exact_joint_matches", "")),
                "reference_conflict_type": str(reference.get("conflict_type", "")),
                "reference_revision_action": str(reference.get("revision_action", "")),
                "llm_conflict_type": _signal_text(llm, "conflict_type"),
                "llm_revision_action": _signal_text(llm, "revision_action"),
                "llm_abstained": _signal_bool(llm, "abstained"),
                "llm_exact_joint_match": _signal_bool(llm, "exact_joint_match"),
                "rules_conflict_type": _signal_text(rules, "conflict_type"),
                "rules_revision_action": _signal_text(rules, "revision_action"),
                "rules_abstained": _signal_bool(rules, "abstained"),
                "rules_exact_joint_match": _signal_bool(rules, "exact_joint_match"),
                "requires_claim_limitation": str(
                    bool(row.get("requires_claim_limitation"))
                ).lower(),
                "triage_reason": triage_reason(row),
            }
        )
    return output


def write_priority_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("diagnostics/solo_v1/machine_annotation/machine_consensus_rows.jsonl"),
        help="Machine-consensus rows JSONL.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/solo_human_review_priority.csv"),
        help="CSV review-priority table to write.",
    )
    parser.add_argument(
        "--include-confirmed",
        action="store_true",
        help="Also include machine-confirmed rows after the disputed-row priority set.",
    )
    args = parser.parse_args()
    rows = build_priority_rows(args.input, include_confirmed=args.include_confirmed)
    write_priority_csv(rows, args.output)
    summary = {
        "schema_version": PRIORITY_SCHEMA_VERSION,
        "input": args.input.as_posix(),
        "output": args.output.as_posix(),
        "rows": len(rows),
        "include_confirmed": args.include_confirmed,
        "publication_gold": False,
        "can_satisfy_human_annotation_gate": False,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
