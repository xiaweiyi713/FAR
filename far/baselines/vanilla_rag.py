"""Single-query RAG baseline."""

from __future__ import annotations

from far.adapters.retrieval import Retriever
from far.protocols import TextGenerator

from .common import BaselinePrediction, generate_answer, retrieve_unique


class VanillaRAG:
    name = "vanilla_rag"

    def __init__(
        self, retriever: Retriever, generator: TextGenerator | None = None, top_k: int = 5
    ):
        self.retriever = retriever
        self.generator = generator
        self.top_k = top_k

    def run(self, sample_id: str, question: str, initial_answer: str) -> BaselinePrediction:
        evidence = retrieve_unique(self.retriever, [question], top_k=self.top_k)
        answer = generate_answer(
            self.generator,
            question,
            initial_answer,
            evidence,
            instruction="Synthesize the most directly supported answer.",
        )
        return BaselinePrediction(
            sample_id=sample_id,
            method=self.name,
            answer=answer,
            evidence_ids=tuple(item.evidence_id for item in evidence),
            trace=({"stage": "retrieve", "queries": [question]},),
        )
