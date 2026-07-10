"""Shared baseline contracts and retrieval/generation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from far.adapters.retrieval import Retriever
from far.models import EvidenceDocument
from far.protocols import TextGenerator


@dataclass(frozen=True)
class BaselinePrediction:
    sample_id: str
    method: str
    answer: str
    evidence_ids: tuple[str, ...]
    predicted_conflict_types: tuple[str, ...] = ()
    revision_action: str | None = None
    trace: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "method": self.method,
            "answer": self.answer,
            "evidence_ids": list(self.evidence_ids),
            "predicted_conflict_types": list(self.predicted_conflict_types),
            "revision_action": self.revision_action,
            "trace": [dict(item) for item in self.trace],
            "metadata": dict(self.metadata),
        }


def retrieve_unique(
    retriever: Retriever,
    queries: list[str],
    *,
    top_k: int,
) -> tuple[EvidenceDocument, ...]:
    by_id: dict[str, EvidenceDocument] = {}
    for query in queries:
        for evidence in retriever.retrieve(query, top_k=top_k):
            previous = by_id.get(evidence.evidence_id)
            if previous is None or evidence.score > previous.score:
                by_id[evidence.evidence_id] = evidence
    return tuple(sorted(by_id.values(), key=lambda item: (-item.score, item.evidence_id)))


def generate_answer(
    generator: TextGenerator | None,
    question: str,
    initial_answer: str,
    evidence: tuple[EvidenceDocument, ...],
    *,
    instruction: str,
) -> str:
    if generator is None:
        return initial_answer
    context = "\n".join(f"[{item.evidence_id}] {item.title}: {item.text}" for item in evidence)
    prompt = (
        f"Question: {question}\nInitial answer: {initial_answer}\n"
        f"Evidence:\n{context}\n\nInstruction: {instruction}\n"
        "Return only the final answer with evidence IDs in brackets."
    )
    return generator.complete(
        prompt,
        system_prompt="Answer only from the supplied evidence. State uncertainty when necessary.",
        temperature=0.0,
        max_tokens=800,
    ).strip()
