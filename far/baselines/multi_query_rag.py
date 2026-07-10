"""Untyped multi-query RAG baseline."""

from __future__ import annotations

import re

from far.adapters.retrieval import Retriever
from far.protocols import TextGenerator

from .common import BaselinePrediction, generate_answer, retrieve_unique


class MultiQueryRAG:
    name = "multi_query_rag"

    def __init__(
        self, retriever: Retriever, generator: TextGenerator | None = None, top_k: int = 5
    ):
        self.retriever = retriever
        self.generator = generator
        self.top_k = top_k

    @staticmethod
    def queries(question: str, initial_answer: str) -> list[str]:
        compact = re.sub(r"[?？。！!]", " ", question)
        terms = " ".join(dict.fromkeys(compact.split()))
        return list(
            dict.fromkeys(
                [
                    question,
                    terms,
                    f"{question} evidence sources",
                    f"{initial_answer} verification",
                ]
            )
        )

    def run(self, sample_id: str, question: str, initial_answer: str) -> BaselinePrediction:
        queries = self.queries(question, initial_answer)
        evidence = retrieve_unique(self.retriever, queries, top_k=self.top_k)
        answer = generate_answer(
            self.generator,
            question,
            initial_answer,
            evidence,
            instruction="Synthesize an answer from the union of multi-query retrieval results.",
        )
        return BaselinePrediction(
            sample_id=sample_id,
            method=self.name,
            answer=answer,
            evidence_ids=tuple(item.evidence_id for item in evidence),
            trace=({"stage": "multi_query_retrieve", "queries": queries},),
        )
