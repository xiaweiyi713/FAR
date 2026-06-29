"""Retrieval protocol, offline implementation, and VeraRAG compatibility adapter."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import replace
from typing import Any, Protocol

from ..models import EvidenceDocument
from .model_assets import resolve_huggingface_snapshot


def _load_vera_retrieval_classes() -> tuple[Any, Any, Any, Any, Any, Any]:
    """Import VeraRAG lazily so FAR's dependency-free path stays usable."""

    from src.retriever import (
        BM25Retriever,
        DenseRetriever,
        HybridRetriever,
        Reranker,
        RerankingRetriever,
    )
    from src.retriever.dense import FAISSRetriever

    return (
        BM25Retriever,
        DenseRetriever,
        FAISSRetriever,
        HybridRetriever,
        Reranker,
        RerankingRetriever,
    )


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
    """Build VeraRAG retrieval stacks and convert their results into FAR records."""

    SUPPORTED_BACKENDS = (
        "vera_bm25",
        "vera_dense",
        "vera_faiss",
        "vera_hybrid",
    )

    def __init__(self, retriever: Any) -> None:
        if not hasattr(retriever, "retrieve"):
            raise TypeError("retriever must expose retrieve(query, top_k)")
        self.retriever = retriever

    @staticmethod
    def _documents(documents: Iterable[EvidenceDocument]) -> list[dict[str, Any]]:
        return [
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

    @staticmethod
    def _mapping(value: Any, *, field: str) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError(f"retrieval.{field} must be a mapping")
        return dict(value)

    @classmethod
    def from_config(
        cls,
        documents: Iterable[EvidenceDocument],
        config: dict[str, Any],
    ) -> VeraRetrieverAdapter:
        """Instantiate BM25, dense, FAISS, hybrid/RRF, and optional reranking.

        VeraRAG's hybrid retriever deliberately supports a BM25 fallback. FAR
        rejects that fallback by default because a silently degraded run would
        make the paper configuration disagree with the executed method.
        """

        if not isinstance(config, dict):
            raise TypeError("retrieval configuration must be a mapping")
        backend = str(config.get("backend", "vera_bm25"))
        if backend not in cls.SUPPORTED_BACKENDS:
            supported = ", ".join(cls.SUPPORTED_BACKENDS)
            raise ValueError(
                f"unsupported VeraRAG retrieval backend {backend!r}; choose {supported}"
            )

        try:
            (
                BM25Retriever,
                DenseRetriever,
                FAISSRetriever,
                HybridRetriever,
                Reranker,
                RerankingRetriever,
            ) = _load_vera_retrieval_classes()
        except ImportError as exc:
            raise RuntimeError(
                "VeraRAG is required for vera_* retrieval backends; install it with "
                "`uv sync --extra experiment` followed by "
                "`uv pip install --no-deps -e /path/to/VeraRAG`."
            ) from exc

        sparse = cls._mapping(config.get("sparse"), field="sparse")
        dense = cls._mapping(config.get("dense"), field="dense")
        if dense.get("model_name"):
            dense["model_name"] = resolve_huggingface_snapshot(
                str(dense["model_name"]),
                str(dense["revision"]) if dense.get("revision") else None,
                local_files_only=bool(dense.get("local_files_only", False)),
            )
        if backend == "vera_bm25":
            retriever: Any = BM25Retriever(
                config=sparse,
                **{key: sparse[key] for key in ("k1", "b", "epsilon") if key in sparse},
            )
            hybrid_retriever = None
        elif backend == "vera_dense":
            retriever = DenseRetriever(config=dense)
            hybrid_retriever = None
        elif backend == "vera_faiss":
            retriever = FAISSRetriever(config=dense)
            hybrid_retriever = None
        else:
            sparse_weight = float(config.get("sparse_weight", 0.3))
            dense_weight = float(config.get("dense_weight", 0.7))
            if (
                not math.isfinite(sparse_weight)
                or not math.isfinite(dense_weight)
                or sparse_weight < 0
                or dense_weight < 0
                or sparse_weight + dense_weight == 0
            ):
                raise ValueError(
                    "hybrid sparse_weight and dense_weight must be non-negative and nonzero"
                )
            hybrid_retriever = HybridRetriever(
                config={"sparse": sparse, "dense": dense},
                sparse_weight=sparse_weight,
                dense_weight=dense_weight,
                **{key: sparse[key] for key in ("k1", "b", "epsilon") if key in sparse},
            )
            retriever = hybrid_retriever

        rerank_value = config.get("rerank")
        if isinstance(rerank_value, bool):
            rerank = {"enabled": rerank_value}
        else:
            rerank = cls._mapping(rerank_value, field="rerank")
        if rerank.get("enabled", False):
            candidate_k = int(rerank.get("candidate_k", 20))
            preserve_base_top_k = int(rerank.get("preserve_base_top_k", 0))
            if candidate_k < 1:
                raise ValueError("retrieval.rerank.candidate_k must be positive")
            batch_size = int(rerank.get("batch_size", 16))
            if batch_size < 1:
                raise ValueError("retrieval.rerank.batch_size must be positive")
            reranker_model = resolve_huggingface_snapshot(
                str(rerank.get("model_name", "BAAI/bge-reranker-base")),
                str(rerank["revision"]) if rerank.get("revision") else None,
                local_files_only=bool(rerank.get("local_files_only", False)),
            )
            reranker = Reranker(
                model_name=reranker_model,
                device=str(rerank.get("device", "cpu")),
                batch_size=batch_size,
                top_k=candidate_k,
                local_files_only=bool(rerank.get("local_files_only", False)),
            )
            retriever = RerankingRetriever(
                retriever,
                reranker,
                candidate_k=candidate_k,
                preserve_base_top_k=preserve_base_top_k,
            )

        try:
            retriever.index_documents(cls._documents(documents))
        except ImportError as exc:
            raise RuntimeError(
                "The configured VeraRAG retrieval stack needs optional dense dependencies; "
                "install FAR's `experiment` extra and the local VeraRAG package."
            ) from exc

        if (
            hybrid_retriever is not None
            and not bool(getattr(hybrid_retriever, "_dense_available", False))
            and not bool(config.get("allow_dense_fallback", False))
        ):
            raise RuntimeError(
                "VeraRAG hybrid retrieval degraded to BM25 because dense retrieval was "
                "unavailable. "
                "Install/cache the configured embedding model, or explicitly set "
                "retrieval.allow_dense_fallback=true for a diagnostic-only run."
            )
        return cls(retriever)

    @classmethod
    def bm25(
        cls, documents: Iterable[EvidenceDocument], config: dict[str, Any] | None = None
    ) -> VeraRetrieverAdapter:
        options = dict(config or {})
        options["backend"] = "vera_bm25"
        return cls.from_config(documents, options)

    def retrieve(self, query: str, top_k: int = 5) -> list[EvidenceDocument]:
        try:
            results = self.retriever.retrieve(query, top_k=top_k)
        except ImportError as exc:
            raise RuntimeError(
                "The configured VeraRAG retrieval stack needs optional dense dependencies; "
                "install FAR's `experiment` extra and the local VeraRAG package."
            ) from exc
        converted: list[EvidenceDocument] = []
        for result in results:
            metadata = dict(getattr(result, "metadata", {}) or {})
            metadata.pop("title", None)
            score = float(getattr(result, "score", 0.0))
            if not math.isfinite(score):
                raise ValueError(f"VeraRAG returned a non-finite retrieval score: {score}")
            converted.append(
                EvidenceDocument(
                    evidence_id=str(result.doc_id),
                    text=str(result.content),
                    title=str(getattr(result, "title", "")),
                    source=str(metadata.pop("source", "unknown")),
                    date=metadata.pop("date", None),
                    url=metadata.pop("url", None),
                    score=max(0.0, score),
                    metadata=metadata,
                )
            )
        return converted
