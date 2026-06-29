"""Transparent CRAG-style reproduction, not the official CRAG implementation."""

from __future__ import annotations

from far.adapters.retrieval import Retriever
from far.protocols import TextGenerator

from .common import BaselinePrediction, generate_answer, retrieve_unique


class CRAGStyleBaseline:
    """Retrieve, grade relevance, and run a corrective corpus query when needed."""

    name = "crag_style_reproduction"

    def __init__(
        self, retriever: Retriever, generator: TextGenerator | None = None, top_k: int = 5
    ):
        self.retriever = retriever
        self.generator = generator
        self.top_k = top_k

    def run(self, sample_id: str, question: str, initial_answer: str) -> BaselinePrediction:
        first = retrieve_unique(self.retriever, [question], top_k=self.top_k)
        relevance = max((item.score for item in first), default=0.0)
        corrective_query = f"{question} authoritative correction fact check"
        queries = [question] if relevance >= 0.1 else [question, corrective_query]
        evidence = retrieve_unique(self.retriever, queries, top_k=self.top_k)
        answer = generate_answer(
            self.generator,
            question,
            initial_answer,
            evidence,
            instruction=(
                "Use the relevance-graded evidence and correct the draft when authoritative "
                "evidence disagrees."
            ),
        )
        return BaselinePrediction(
            sample_id=sample_id,
            method=self.name,
            answer=answer,
            evidence_ids=tuple(item.evidence_id for item in evidence),
            trace=(
                {"stage": "relevance_grade", "max_lexical_score": relevance},
                {"stage": "corrective_retrieve", "applied": len(queries) > 1},
            ),
            metadata={
                "official_implementation": False,
                "scope": "closed-corpus CRAG-style reproduction; no web search",
            },
        )
