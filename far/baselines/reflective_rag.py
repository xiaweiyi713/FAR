"""Iterative reflective retrieval baseline without typed conflict control."""

from __future__ import annotations

from far.adapters.retrieval import Retriever
from far.protocols import TextGenerator

from .common import BaselinePrediction, generate_answer, retrieve_unique


class ReflectiveRAG:
    name = "reflective_rag"

    def __init__(
        self, retriever: Retriever, generator: TextGenerator | None = None, top_k: int = 5
    ):
        self.retriever = retriever
        self.generator = generator
        self.top_k = top_k

    def _reflection_query(self, question: str, initial_answer: str) -> str:
        if self.generator is None:
            return f"{initial_answer} possible error contrary evidence limitation"
        return self.generator.complete(
            (
                f"Question: {question}\nDraft: {initial_answer}\n"
                "Write one short retrieval query for information the draft may have missed."
            ),
            system_prompt="Return only a retrieval query; do not answer the question.",
            temperature=0.0,
            max_tokens=100,
        ).strip()

    def run(self, sample_id: str, question: str, initial_answer: str) -> BaselinePrediction:
        reflection_query = self._reflection_query(question, initial_answer)
        queries = [question, reflection_query]
        evidence = retrieve_unique(self.retriever, queries, top_k=self.top_k)
        answer = generate_answer(
            self.generator,
            question,
            initial_answer,
            evidence,
            instruction="Reflect on the draft once, then correct unsupported statements.",
        )
        return BaselinePrediction(
            sample_id=sample_id,
            method=self.name,
            answer=answer,
            evidence_ids=tuple(item.evidence_id for item in evidence),
            trace=(
                {"stage": "initial_retrieve", "query": question},
                {"stage": "reflection_retrieve", "query": reflection_query},
            ),
        )
