"""Transparent Self-RAG-style reproduction, not the official trained model."""

from __future__ import annotations

from far.adapters.retrieval import Retriever
from far.protocols import TextGenerator

from .common import BaselinePrediction, generate_answer, retrieve_unique


class SelfRAGStyleBaseline:
    """Approximate retrieve/relevance/support reflection with explicit telemetry."""

    name = "self_rag_style_reproduction"

    def __init__(
        self, retriever: Retriever, generator: TextGenerator | None = None, top_k: int = 5
    ):
        self.retriever = retriever
        self.generator = generator
        self.top_k = top_k

    def run(self, sample_id: str, question: str, initial_answer: str) -> BaselinePrediction:
        evidence = retrieve_unique(
            self.retriever,
            [question, f"{initial_answer} supporting evidence"],
            top_k=self.top_k,
        )
        support_score = max((item.score for item in evidence), default=0.0)
        answer = generate_answer(
            self.generator,
            question,
            initial_answer,
            evidence,
            instruction=(
                "Perform one retrieve/relevance/support reflection and answer only when the "
                "retrieved passages support the result."
            ),
        )
        if self.generator is None and support_score == 0.0:
            answer = f"Insufficient retrieved support for the draft: {initial_answer}"
        return BaselinePrediction(
            sample_id=sample_id,
            method=self.name,
            answer=answer,
            evidence_ids=tuple(item.evidence_id for item in evidence),
            trace=({"stage": "support_reflection", "lexical_support_score": support_score},),
            metadata={
                "official_implementation": False,
                "scope": "inference-time approximation; no Self-RAG reflection-token training",
            },
        )
