"""Generate non-gold weak-supervision labels for blind annotation packets."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from far.bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.bench.schema import VALID_CONFLICT_TYPES, VALID_REVISION_ACTIONS

WEAK_LABEL_VERSION = "falsirag-weak-annotation-v1"

_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?(?:,\d{3})*(?:%|％)?")
_CAUSAL_RE = re.compile(
    r"导致|造成|使得|因为|由于|因此|因而|证明.*有效|caus(?:e|es|ed|al)|because|therefore",
    re.IGNORECASE,
)
_CORRELATION_RE = re.compile(
    r"相关|关联|可能|尚不确定|不能.*证明|correlat|associat|may|might|not prove",
    re.IGNORECASE,
)
_DEFINITION_RE = re.compile(
    r"定义|口径|范围|包含|不包含|计入|未计入|scope|definition|include|exclude",
    re.IGNORECASE,
)
_SOURCE_RELIABILITY_RE = re.compile(
    r"unverified|secondary summary|媒体报道称|有媒体报道|传闻|非官方|低可靠|未经证实",
    re.IGNORECASE,
)
_ENTITY_TOKEN_RE = re.compile(
    r"[A-Z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}(?:公司|大学|空间站|法院|工厂|芯片|电池|处理器|博士|CTO)"
)


def _normalise_number(value: str) -> str:
    return value.replace(",", "").replace("％", "%")


def _numbers(text: str) -> set[str]:
    values = {_normalise_number(match.group(0)) for match in _NUMBER_RE.finditer(text)}
    return {value for value in values if not _YEAR_RE.fullmatch(value)}


def _years(text: str) -> set[str]:
    return {match.group(0) for match in _YEAR_RE.finditer(text)}


def _entities(text: str) -> set[str]:
    return {match.group(0) for match in _ENTITY_TOKEN_RE.finditer(text)}


def _evidence_text(row: dict[str, Any]) -> str:
    return "\n".join(str(item.get("text", "")) for item in row.get("evidence", []))


def _evidence_ids(row: dict[str, Any]) -> list[str]:
    return [str(item.get("evidence_id", "")) for item in row.get("evidence", [])]


def _add_signal(
    signals: list[dict[str, Any]],
    *,
    name: str,
    conflict_type: str,
    revision_action: str,
    confidence: float,
    evidence_ids: list[str],
    rationale: str,
) -> None:
    if conflict_type not in VALID_CONFLICT_TYPES:
        raise ValueError(f"invalid weak conflict type: {conflict_type}")
    if revision_action not in VALID_REVISION_ACTIONS:
        raise ValueError(f"invalid weak revision action: {revision_action}")
    signals.append(
        {
            "name": name,
            "conflict_type": conflict_type,
            "revision_action": revision_action,
            "confidence": confidence,
            "evidence_ids": evidence_ids,
            "rationale": rationale,
        }
    )


def weak_label_row(row: dict[str, Any]) -> dict[str, Any]:
    """Return a conservative weak annotation for one blind packet row."""

    answer = str(row.get("initial_answer", ""))
    claims = " ".join(str(claim.get("claim", "")) for claim in row.get("claims", []))
    answer_and_claims = f"{answer}\n{claims}"
    evidence = _evidence_text(row)
    evidence_ids = _evidence_ids(row)
    signals: list[dict[str, Any]] = []

    answer_years = _years(answer_and_claims)
    evidence_years = _years(evidence)
    if answer_years and evidence_years and answer_years != evidence_years:
        _add_signal(
            signals,
            name="year_mismatch",
            conflict_type="temporal",
            revision_action="correct_temporal",
            confidence=0.82,
            evidence_ids=evidence_ids,
            rationale=(
                f"Answer/claims years {sorted(answer_years)} differ from visible "
                f"evidence years {sorted(evidence_years)}."
            ),
        )

    answer_numbers = _numbers(answer_and_claims)
    evidence_numbers = _numbers(evidence)
    if answer_numbers and evidence_numbers and answer_numbers.isdisjoint(evidence_numbers):
        _add_signal(
            signals,
            name="number_mismatch",
            conflict_type="numerical",
            revision_action="replace_numerical",
            confidence=0.74,
            evidence_ids=evidence_ids,
            rationale=(
                f"Answer/claims numbers {sorted(answer_numbers)[:8]} do not overlap "
                f"visible evidence numbers {sorted(evidence_numbers)[:8]}."
            ),
        )

    if _SOURCE_RELIABILITY_RE.search(answer):
        _add_signal(
            signals,
            name="unverified_source_phrase",
            conflict_type="source_reliability",
            revision_action="prefer_reliable_source",
            confidence=0.68,
            evidence_ids=evidence_ids,
            rationale="The answer explicitly uses unverified or secondary-source phrasing.",
        )

    if _CAUSAL_RE.search(answer_and_claims) and _CORRELATION_RE.search(evidence):
        _add_signal(
            signals,
            name="causal_language_with_qualified_evidence",
            conflict_type="causal",
            revision_action="downgrade_causal_to_correlation",
            confidence=0.64,
            evidence_ids=evidence_ids,
            rationale=(
                "The answer uses causal language while the evidence is qualified/correlational."
            ),
        )

    if _DEFINITION_RE.search(answer_and_claims) and _DEFINITION_RE.search(evidence):
        answer_entities = _entities(answer_and_claims)
        evidence_entities = _entities(evidence)
        if answer_entities != evidence_entities or answer_numbers != evidence_numbers:
            _add_signal(
                signals,
                name="definition_or_scope_marker",
                conflict_type="definition",
                revision_action="clarify_definition",
                confidence=0.55,
                evidence_ids=evidence_ids,
                rationale=(
                    "Definition/scope language appears with different entities or quantities."
                ),
            )

    answer_entities = _entities(answer_and_claims)
    evidence_entities = _entities(evidence)
    if answer_entities and evidence_entities:
        answer_only = answer_entities - evidence_entities
        evidence_only = evidence_entities - answer_entities
        if answer_only and evidence_only:
            _add_signal(
                signals,
                name="entity_set_mismatch",
                conflict_type="entity",
                revision_action="requalify_entity",
                confidence=0.5,
                evidence_ids=evidence_ids,
                rationale=(
                    f"Answer-only entity-like terms {sorted(answer_only)[:6]} differ from "
                    f"evidence-only terms {sorted(evidence_only)[:6]}."
                ),
            )

    if signals:
        best = max(signals, key=lambda item: float(item["confidence"]))
        return {
            "conflict_present": True,
            "conflict_type": best["conflict_type"],
            "revision_action": best["revision_action"],
            "revised_answer_acceptable": True,
            "suggested_revised_answer": "",
            "rationale": best["rationale"],
            "confidence": float(best["confidence"]),
            "needs_human_review": True,
            "abstained": False,
            "signals": signals,
        }
    return {
        "conflict_present": False,
        "conflict_type": "no_conflict",
        "revision_action": "qualify_uncertainty",
        "revised_answer_acceptable": False,
        "suggested_revised_answer": "",
        "rationale": (
            "No weak labeling function fired; this is an abstention, not evidence of no conflict."
        ),
        "confidence": 0.0,
        "needs_human_review": True,
        "abstained": True,
        "signals": [],
    }


def generate_weak_labels(
    packet_dir: Path,
    output_dir: Path,
    *,
    weak_annotator_id: str = "rules_weak_supervision_v1",
    limit: int | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    manifest_path = packet_dir / "packet_manifest.json"
    packet_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_rows = read_jsonl(packet_dir / packet_manifest["adjudication_file"])
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        source_rows = source_rows[:limit]
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass --overwrite to replace it")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    rows = []
    for row in source_rows:
        rows.append(
            {
                "schema_version": WEAK_LABEL_VERSION,
                "sample_id": row["sample_id"],
                "question": row["question"],
                "initial_answer": row["initial_answer"],
                "claims": row["claims"],
                "evidence": row["evidence"],
                "weak_annotator_id": weak_annotator_id,
                "weak_annotation": weak_label_row(row),
                "publication_gold": False,
            }
        )
    output_file = output_dir / "weak_annotations.jsonl"
    write_jsonl(output_file, rows)

    conflict_counts = Counter(
        str(row["weak_annotation"]["conflict_type"])
        for row in rows
        if not row["weak_annotation"]["abstained"]
    )
    abstentions = sum(bool(row["weak_annotation"]["abstained"]) for row in rows)
    result = {
        "schema_version": WEAK_LABEL_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_packet_sha256": sha256_file(manifest_path),
        "source_fingerprints": packet_manifest["source_fingerprints"],
        "samples": len(rows),
        "weak_annotator_id": weak_annotator_id,
        "weak_annotation_file": output_file.name,
        "weak_annotation_sha256": sha256_file(output_file),
        "abstentions": abstentions,
        "non_abstained": len(rows) - abstentions,
        "conflict_type_counts": dict(sorted(conflict_counts.items())),
        "publication_gold": False,
        "can_satisfy_human_annotation_gate": False,
        "required_next_step": (
            "Treat weak labels as machine-only review aids. They can be compared with "
            "LLM preannotations or imported into a review UI, but they are not human "
            "annotations and cannot produce Cohen's kappa."
        ),
    }
    write_json(output_dir / "weak_annotation_manifest.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--weak-annotator-id", default="rules_weak_supervision_v1")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    result = generate_weak_labels(
        args.packet_dir,
        args.output_dir,
        weak_annotator_id=args.weak_annotator_id,
        limit=args.limit,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
