"""Retrieval protocol, offline implementation, and VeraRAG compatibility adapter."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import replace
from typing import Any, Protocol

from ..models import EvidenceDocument


class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int = 5) -> list[EvidenceDocument]: ...


class InMemoryRetriever:
    """Deterministic lexical retriever for tests, demos, and dependency-free smoke runs."""

    _ENGLISH = re.compile(r"[A-Za-z0-9]+(?:[._%-][A-Za-z0-9]+)*")
    _CJK = re.compile(r"[\u4e00-\u9fff]+")

    def __init__(self, documents: Iterable[EvidenceDocument]) -> None:
        self.documents = tuple(documents)
        self._tokens = {
            doc.evidence_id: self._tokenize(f"{doc.title} {doc.text}") for doc in self.documents
        }

    def retrieve(self, query: str, top_k: int = 5) -> list[EvidenceDocument]:
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 0:
            raise ValueError("top_k must be a non-negative integer")
        if not query.strip() or top_k == 0:
            return []
        query_tokens = self._tokenize(query)
        scored: list[tuple[float, EvidenceDocument]] = []
        for document in self.documents:
            doc_tokens = self._tokens[document.evidence_id]
            overlap = query_tokens & doc_tokens
            if not overlap:
                continue
            precision = len(overlap) / max(1, len(query_tokens))
            recall = len(overlap) / max(1, len(doc_tokens))
            score = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
            score *= 1.0 + math.log1p(len(overlap))
            scored.append((score, replace(document, score=score)))
        scored.sort(key=lambda pair: (-pair[0], pair[1].evidence_id))
        return [document for _, document in scored[:top_k]]

    @classmethod
    def _tokenize(cls, text: str) -> set[str]:
        lowered = text.lower()
        tokens = {item.lower() for item in cls._ENGLISH.findall(lowered)}
        for block in cls._CJK.findall(lowered):
            tokens.add(block)
            tokens.update(block[index : index + 2] for index in range(max(0, len(block) - 1)))
        return {token for token in tokens if token}


class VeraRetrieverAdapter:
    """Convert VeraRAG RetrievalResult objects into FAR evidence records."""

    def __init__(self, retriever: Any) -> None:
        if not hasattr(retriever, "retrieve"):
            raise TypeError("retriever must expose retrieve(query, top_k)")
        self.retriever = retriever

    @classmethod
    def bm25(
        cls, documents: Iterable[EvidenceDocument], config: dict[str, Any] | None = None
    ) -> VeraRetrieverAdapter:
        try:
            from src.retriever import BM25Retriever
        except ImportError as exc:
            raise RuntimeError("VeraRAG is required for the Vera BM25 adapter") from exc
        retriever = BM25Retriever(config or {})
        retriever.index_documents(
            [
                {
                    "id": doc.evidence_id,
                    "text": doc.text,
                    "title": doc.title,
                    "source": doc.source,
                    "date": doc.date,
                    "url": doc.url,
                    **doc.metadata,
                }
                for doc in documents
            ]
        )
        return cls(retriever)

    def retrieve(self, query: str, top_k: int = 5) -> list[EvidenceDocument]:
        results = self.retriever.retrieve(query, top_k=top_k)
        converted: list[EvidenceDocument] = []
        for result in results:
            metadata = dict(getattr(result, "metadata", {}) or {})
            converted.append(
                EvidenceDocument(
                    evidence_id=str(result.doc_id),
                    text=str(result.content),
                    title=str(getattr(result, "title", "")),
                    source=str(metadata.pop("source", "unknown")),
                    date=metadata.pop("date", None),
                    url=metadata.pop("url", None),
                    score=max(0.0, float(getattr(result, "score", 0.0))),
                    metadata=metadata,
                )
            )
        return converted
