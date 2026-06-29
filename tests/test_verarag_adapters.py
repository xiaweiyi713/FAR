from __future__ import annotations

import importlib.util
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from far.adapters import VeraLLMAdapter, VeraRetrieverAdapter
from far.models import EvidenceDocument


class _FakeLLMClient:
    def generate(self, prompt: str, **kwargs: object) -> str:
        return f"generated:{prompt}:{kwargs['temperature']}"


def test_llm_adapter_maps_the_stable_far_interface() -> None:
    adapter = VeraLLMAdapter(client=_FakeLLMClient())
    assert adapter.complete("claim", temperature=0.0) == "generated:claim:0.0"


def test_llm_adapter_rejects_unknown_provider_before_import() -> None:
    with pytest.raises(ValueError, match="unsupported VeraRAG LLM provider"):
        VeraLLMAdapter(provider="imaginary-provider")


class _FakeRetriever:
    def __init__(self, config: dict[str, object] | None = None, **kwargs: object) -> None:
        self.config = config or {}
        self.kwargs = kwargs
        self.documents: list[dict[str, object]] = []

    def index_documents(self, documents: list[dict[str, object]]) -> None:
        self.documents = documents

    def retrieve(self, query: str, top_k: int = 5) -> list[SimpleNamespace]:
        del query
        return [
            SimpleNamespace(
                doc_id=row["id"],
                content=row["text"],
                title=row["title"],
                score=0.5,
                metadata=row,
            )
            for row in self.documents[:top_k]
        ]


class _FakeHybridRetriever(_FakeRetriever):
    _dense_available = True


class _FakeReranker:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class _FakeRerankingRetriever(_FakeRetriever):
    def __init__(
        self,
        base_retriever: _FakeRetriever,
        reranker: _FakeReranker,
        **kwargs: object,
    ) -> None:
        super().__init__()
        self.base_retriever = base_retriever
        self.reranker = reranker
        self.kwargs = kwargs

    def index_documents(self, documents: list[dict[str, object]]) -> None:
        self.base_retriever.index_documents(documents)
        self.documents = documents


def _fake_vera_classes() -> tuple[type[object], ...]:
    return (
        _FakeRetriever,
        _FakeRetriever,
        _FakeRetriever,
        _FakeHybridRetriever,
        _FakeReranker,
        _FakeRerankingRetriever,
    )


def test_vera_hybrid_reranker_factory_preserves_configuration_and_provenance() -> None:
    document = EvidenceDocument(
        evidence_id="E1",
        title="Audited revenue",
        text="The audited revenue was 18 million.",
        source="official",
        date="2025-01-01",
        metadata={"language": "en"},
    )
    with patch(
        "far.adapters.retrieval._load_vera_retrieval_classes",
        return_value=_fake_vera_classes(),
    ):
        adapter = VeraRetrieverAdapter.from_config(
            [document],
            {
                "backend": "vera_hybrid",
                "sparse_weight": 0.4,
                "dense_weight": 0.6,
                "dense": {"model_name": "example/embed"},
                "rerank": {
                    "enabled": True,
                    "model_name": "example/reranker",
                    "candidate_k": 11,
                    "preserve_base_top_k": 1,
                },
            },
        )
    assert isinstance(adapter.retriever, _FakeRerankingRetriever)
    base = adapter.retriever.base_retriever
    assert base.kwargs == {"sparse_weight": 0.4, "dense_weight": 0.6}
    assert base.config["dense"] == {"model_name": "example/embed"}
    assert adapter.retriever.kwargs == {"candidate_k": 11, "preserve_base_top_k": 1}
    result = adapter.retrieve("revenue", top_k=1)[0]
    assert result.evidence_id == "E1"
    assert result.source == "official"
    assert result.date == "2025-01-01"
    assert result.metadata == {"id": "E1", "text": document.text, "language": "en"}


def test_vera_hybrid_rejects_silent_dense_fallback() -> None:
    class _UnavailableHybrid(_FakeHybridRetriever):
        _dense_available = False

    classes = list(_fake_vera_classes())
    classes[3] = _UnavailableHybrid
    with (
        patch(
            "far.adapters.retrieval._load_vera_retrieval_classes",
            return_value=tuple(classes),
        ),
        pytest.raises(RuntimeError, match="degraded to BM25"),
    ):
        VeraRetrieverAdapter.from_config(
            [EvidenceDocument(evidence_id="E1", text="evidence")],
            {"backend": "vera_hybrid"},
        )


@pytest.mark.skipif(importlib.util.find_spec("src") is None, reason="VeraRAG is not installed")
def test_vera_bm25_adapter_round_trip() -> None:
    adapter = VeraRetrieverAdapter.bm25(
        [
            EvidenceDocument(
                evidence_id="E1",
                title="Audited revenue",
                text="The audited revenue was 18 million.",
                source="official",
            ),
            EvidenceDocument(
                evidence_id="E2",
                title="Weather",
                text="Rain is expected tomorrow.",
            ),
            EvidenceDocument(
                evidence_id="E3",
                title="Sports",
                text="The team won its match.",
            ),
        ]
    )
    results = adapter.retrieve("audited revenue 18 million", top_k=1)
    assert results[0].evidence_id == "E1"
    assert results[0].source == "official"
