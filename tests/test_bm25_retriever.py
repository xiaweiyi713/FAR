from __future__ import annotations

import pytest

from experiments.runner import build_retriever
from far.adapters import BM25Retriever, InMemoryRetriever
from far.models import EvidenceDocument


def _documents() -> list[EvidenceDocument]:
    return [
        EvidenceDocument(
            evidence_id="E1",
            title="Audited annual report",
            text="The audited revenue was 18 million.",
            source="official",
            date="2025-01-01",
            metadata={"language": "en"},
        ),
        EvidenceDocument(
            evidence_id="E2",
            title="Revenue forecast",
            text="The unaudited revenue forecast was 20 million.",
        ),
        EvidenceDocument(
            evidence_id="E3",
            title="Weather",
            text="Rain is expected tomorrow.",
        ),
    ]


def test_bm25_ranks_relevant_documents_and_preserves_provenance() -> None:
    documents = _documents()
    results = BM25Retriever(documents).retrieve("audited annual revenue 18", top_k=2)

    assert [item.evidence_id for item in results] == ["E1", "E2"]
    assert results[0].source == "official"
    assert results[0].date == "2025-01-01"
    assert results[0].metadata == {"language": "en"}
    assert results[0].score >= results[1].score >= 0.0
    assert all(document.score == 0.0 for document in documents)


def test_bm25_supports_cjk_bigrams_and_filters_no_overlap() -> None:
    retriever = BM25Retriever(
        [
            EvidenceDocument("CN1", "审计报告显示公司收入为一千八百万元。"),
            EvidenceDocument("CN2", "明天可能出现降雨。"),
        ]
    )

    assert retriever.retrieve("公司收入", top_k=1)[0].evidence_id == "CN1"
    assert retriever.retrieve("火星地质", top_k=5) == []
    assert retriever.retrieve("", top_k=5) == []
    assert retriever.retrieve("收入", top_k=0) == []


@pytest.mark.parametrize("top_k", [-1, 1.5, True])
def test_bm25_rejects_invalid_top_k(top_k: object) -> None:
    with pytest.raises(ValueError, match="top_k"):
        BM25Retriever(_documents()).retrieve("revenue", top_k=top_k)  # type: ignore[arg-type]


def test_bm25_validates_corpus_identity_and_parameters() -> None:
    duplicate = [EvidenceDocument("E1", "Alpha"), EvidenceDocument("E1", "Beta")]
    with pytest.raises(ValueError, match="unique"):
        BM25Retriever(duplicate)
    with pytest.raises(ValueError, match="k1"):
        BM25Retriever([], k1=0)
    with pytest.raises(ValueError, match="b"):
        BM25Retriever([], b=1.1)
    with pytest.raises(ValueError, match="epsilon"):
        BM25Retriever([], epsilon=-0.1)


def test_experiment_factory_defaults_to_bm25_and_keeps_lexical_compatibility() -> None:
    documents = _documents()

    assert isinstance(build_retriever({}, documents), BM25Retriever)
    assert isinstance(
        build_retriever({"retrieval": {"backend": "bm25", "k1": 1.2}}, documents),
        BM25Retriever,
    )
    assert isinstance(
        build_retriever({"retrieval": {"backend": "lexical"}}, documents),
        InMemoryRetriever,
    )
