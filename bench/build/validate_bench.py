"""Validate FalsiRAG-Bench structure, provenance, splits, and retrieval viability."""

from __future__ import annotations

import argparse
import difflib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json
from bench.schema import BLIND_TEST_ALLOWED_FIELDS, CorpusDocument, FalsiRAGSample
from far.adapters import InMemoryRetriever
from far.claims import ClaimNode, ClaimType
from far.counterfactual import TypedQueryGenerator
from far.evidence_types import EvidenceRequirementAssigner
from far.models import EvidenceDocument

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1]


def _span_is_traceable(span: str, content: str) -> bool:
    if span in content:
        return True
    segments = [item.strip() for item in span.replace("……", "...").replace("…", "...").split("...")]
    cursor = 0
    for segment in segments:
        if not segment:
            continue
        index = content.find(segment, cursor)
        if index < 0:
            return False
        cursor = index + len(segment)
    return bool(segments)


def _claim_type(raw: str) -> ClaimType:
    aliases = {"definitional": ClaimType.DEFINITIONAL, "inferential": ClaimType.INFERENTIAL}
    return aliases.get(raw, ClaimType(raw))


def _corrected_fragments(initial: str, revised: str) -> list[str]:
    matcher = difflib.SequenceMatcher(a=initial, b=revised, autojunk=False)
    return [
        revised[j1:j2]
        for tag, _i1, _i2, j1, j2 in matcher.get_opcodes()
        if tag in {"replace", "insert"} and revised[j1:j2].strip()
    ]


def _semantic_anchors(category: str, initial: str, revised: str) -> list[str]:
    if category in {"numerical_conflict", "multi_source_conflict"}:
        initial_numbers = set(re.findall(r"\d+(?:\.\d+)?", initial))
        revised_numbers = set(re.findall(r"\d+(?:\.\d+)?", revised))
        numeric = sorted(revised_numbers - initial_numbers, key=len, reverse=True)
        if numeric:
            return numeric
    if category in {"temporal_shift", "multi_source_conflict"}:
        initial_years = set(re.findall(r"(?:19|20)\d{2}", initial))
        revised_years = set(re.findall(r"(?:19|20)\d{2}", revised))
        temporal = sorted(revised_years - initial_years)
        if temporal:
            return temporal
    return _corrected_fragments(initial, revised)


def _retrieval_recall(
    samples: list[FalsiRAGSample],
    corpus: dict[str, CorpusDocument],
    top_k: int = 10,
) -> dict[str, Any]:
    retriever = InMemoryRetriever(
        EvidenceDocument(
            evidence_id=document.doc_id,
            text=document.content,
            title=document.title,
            source=document.source,
            date=document.date,
            url=document.url,
            metadata={"synthetic": document.synthetic},
        )
        for document in corpus.values()
    )
    assigner = EvidenceRequirementAssigner()
    generator = TypedQueryGenerator()
    hits = 0
    by_category: dict[str, list[bool]] = defaultdict(list)
    for sample in samples:
        raw_claim = sample.claims[0]
        claim = ClaimNode(
            claim_id=raw_claim["claim_id"],
            text=raw_claim["claim"],
            claim_type=_claim_type(raw_claim["type"]),
        )
        target_ids = {item["doc_id"] for item in sample.counter_evidence}
        retrieved_ids: set[str] = set()
        for query in generator.generate(claim, assigner.assign(claim)):
            retrieved_ids.update(item.evidence_id for item in retriever.retrieve(query.text, top_k))
        hit = bool(target_ids & retrieved_ids)
        hits += hit
        by_category[sample.category.value].append(hit)
    return {
        "top_k_per_query": top_k,
        "queries_per_claim": 3,
        "hits": hits,
        "samples": len(samples),
        "recall": hits / len(samples) if samples else 0.0,
        "by_category": {
            category: sum(values) / len(values) if values else 0.0
            for category, values in sorted(by_category.items())
        },
    }


def validate(data_dir: Path, *, minimum_retrieval_recall: float = 0.8) -> dict[str, Any]:
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    split_manifest = json.loads((data_dir / "split_manifest.json").read_text(encoding="utf-8"))
    corpus_rows = read_jsonl(data_dir / "corpus.jsonl")
    sample_rows = read_jsonl(data_dir / "falsirag_bench.jsonl")
    corpus_documents = [CorpusDocument.from_dict(row) for row in corpus_rows]
    samples = [FalsiRAGSample.from_dict(row) for row in sample_rows]
    corpus = {document.doc_id: document for document in corpus_documents}
    errors: list[str] = []
    if len(corpus) != len(corpus_documents):
        errors.append("corpus document IDs are not unique")
    if len({sample.sample_id for sample in samples}) != len(samples):
        errors.append("sample IDs are not unique")

    untraceable: list[str] = []
    semantically_unanchored: list[str] = []
    for sample in samples:
        for evidence in (*sample.gold_evidence, *sample.counter_evidence):
            document = corpus.get(evidence["doc_id"])
            if document is None:
                errors.append(f"{sample.sample_id}: unknown document {evidence['doc_id']}")
                continue
            if not _span_is_traceable(evidence["text_span"], document.content):
                untraceable.append(f"{sample.sample_id}:{evidence['evidence_id']}")
        counter_text = " ".join(item["text_span"] for item in sample.counter_evidence)
        if sample.category.value == "causal_overclaim":
            if "does not establish" not in counter_text.lower():
                semantically_unanchored.append(sample.sample_id)
        else:
            fragments = _semantic_anchors(
                sample.category.value,
                sample.initial_answer,
                str(sample.expected_revision["revised_answer"]),
            )
            if not fragments or not any(fragment in counter_text for fragment in fragments):
                semantically_unanchored.append(sample.sample_id)
    if untraceable:
        errors.append(f"{len(untraceable)} evidence spans are not traceable to corpus text")
    if semantically_unanchored:
        errors.append(
            f"{len(semantically_unanchored)} counter-evidence rows do not contain "
            "the corrected field"
        )

    category_counts = Counter(sample.category.value for sample in samples)
    split_counts = Counter(sample.split for sample in samples)
    if set(category_counts.values()) != {60} or len(category_counts) != 5:
        errors.append(f"expected five categories with 60 samples each, got {dict(category_counts)}")
    assignments = split_manifest.get("question_assignments", {})
    if assignments != {sample.sample_id: sample.split for sample in samples}:
        errors.append("split manifest assignments do not match benchmark rows")

    group_splits: dict[str, set[str]] = defaultdict(set)
    for sample in samples:
        group = str(sample.source_metadata.get("dependency_group", ""))
        if not group:
            errors.append(f"{sample.sample_id}: missing dependency group")
        group_splits[group].add(sample.split)
    cross_split = {
        group: sorted(splits) for group, splits in group_splits.items() if len(splits) > 1
    }
    if cross_split:
        errors.append(f"{len(cross_split)} dependency groups cross splits")

    expected_fingerprints = manifest.get("fingerprints", {})
    observed_fingerprints = {
        "corpus_sha256": sha256_file(data_dir / "corpus.jsonl"),
        "benchmark_sha256": sha256_file(data_dir / "falsirag_bench.jsonl"),
        "split_manifest_sha256": sha256_file(data_dir / "split_manifest.json"),
    }
    if expected_fingerprints != observed_fingerprints:
        errors.append("manifest fingerprints do not match data files")

    test_rows = read_jsonl(data_dir / "splits" / "test_inputs.jsonl")
    test_ids = {sample.sample_id for sample in samples if sample.split == "test"}
    if {row.get("id") for row in test_rows} != test_ids:
        errors.append("test_inputs IDs do not match the frozen test split")
    if any(set(row) != BLIND_TEST_ALLOWED_FIELDS for row in test_rows):
        errors.append("test_inputs must contain exactly the five allowed operational fields")

    retrieval = _retrieval_recall(samples, corpus)
    if retrieval["recall"] < minimum_retrieval_recall:
        errors.append(
            f"counter-evidence lexical recall {retrieval['recall']:.3f} is below "
            f"{minimum_retrieval_recall:.3f}"
        )
    annotation_counts = Counter(sample.annotation_status.value for sample in samples)
    publication_ready = (
        not errors
        and annotation_counts == {"adjudicated": len(samples)}
        and bool(manifest.get("publication_ready"))
    )
    return {
        "schema_version": "falsirag-validation-report-v1",
        "valid": not errors,
        "publication_ready": publication_ready,
        "candidate_ready": not errors,
        "errors": errors,
        "counts": {
            "samples": len(samples),
            "documents": len(corpus),
            "categories": dict(category_counts),
            "splits": dict(split_counts),
            "annotation_status": dict(annotation_counts),
            "untraceable_evidence": len(untraceable),
            "semantically_unanchored_counter_evidence": len(semantically_unanchored),
            "cross_split_dependency_groups": len(cross_split),
        },
        "fingerprints": observed_fingerprints,
        "counter_evidence_retrieval": retrieval,
        "publication_blockers": manifest.get("publication_blockers", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--minimum-retrieval-recall", type=float, default=0.8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate(
        args.data_dir,
        minimum_retrieval_recall=args.minimum_retrieval_recall,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        write_json(args.output, report)
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
