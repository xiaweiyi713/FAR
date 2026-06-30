from __future__ import annotations

import importlib.util
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

from far.adapters import VeraConflictDetector, VeraLLMAdapter, VeraRetrieverAdapter
from far.claims import ClaimNode, ClaimType
from far.models import EvidenceDocument


class _FakeLLMClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate(self, prompt: str, **kwargs: object) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        return f"generated:{prompt}:{kwargs['temperature']}"


def test_llm_adapter_maps_the_stable_far_interface() -> None:
    adapter = VeraLLMAdapter(client=_FakeLLMClient())
    assert adapter.complete("claim", temperature=0.0) == "generated:claim:0.0"


def test_llm_adapter_forwards_json_response_format() -> None:
    client = _FakeLLMClient()
    adapter = VeraLLMAdapter(client=client)

    assert (
        adapter.complete("claim", temperature=0.0, response_format="json") == "generated:claim:0.0"
    )
    assert client.calls == [
        {
            "prompt": "claim",
            "system_prompt": None,
            "temperature": 0.0,
            "max_tokens": 1000,
            "response_format": "json",
        }
    ]


def test_ollama_adapter_disables_thinking_for_publication_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = ModuleType("ollama")
    calls: list[dict[str, object]] = []

    class FakeOllamaClient:
        def __init__(self, host: str) -> None:
            calls.append({"host": host})

        def generate(self, **kwargs: object) -> dict[str, object]:
            calls.append(kwargs)
            return {"response": '{"ok": true}', "thinking": ""}

    fake_module.Client = FakeOllamaClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ollama", fake_module)

    adapter = VeraLLMAdapter(
        provider="ollama",
        model="qwen3.5:9b",
        base_url="http://ollama.local:11434",
        think=False,
        unload_after_sample=True,
    )

    assert adapter.complete("json please", response_format="json") == '{"ok": true}'
    assert calls == [
        {"host": "http://ollama.local:11434"},
        {
            "model": "qwen3.5:9b",
            "prompt": "json please",
            "options": {"num_predict": 1000, "temperature": 0.0},
            "think": False,
            "format": "json",
        },
    ]
    adapter.release()
    assert calls[-1] == {"model": "qwen3.5:9b", "prompt": "", "keep_alive": 0}


def test_ollama_adapter_rejects_thinking_without_final_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = ModuleType("ollama")

    class FakeOllamaClient:
        def __init__(self, host: str) -> None:
            del host

        def generate(self, **kwargs: object) -> dict[str, object]:
            del kwargs
            return {"response": "", "thinking": "unfinished reasoning"}

    fake_module.Client = FakeOllamaClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ollama", fake_module)
    adapter = VeraLLMAdapter(provider="ollama", model="qwen3.5:9b")

    with pytest.raises(RuntimeError, match="thinking text without a final response"):
        adapter.complete("answer")


def test_llm_adapter_rejects_invalid_release_configuration() -> None:
    with pytest.raises(TypeError, match="unload_after_sample"):
        VeraLLMAdapter(client=_FakeLLMClient(), unload_after_sample="yes")


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
    with (
        patch(
            "far.adapters.retrieval._load_vera_retrieval_classes",
            return_value=_fake_vera_classes(),
        ),
        patch(
            "far.adapters.retrieval.resolve_huggingface_snapshot",
            side_effect=lambda name, revision, **_: (
                f"/snapshots/{revision}/{name.rsplit('/', 1)[-1]}"
            ),
        ) as resolve_model,
    ):
        adapter = VeraRetrieverAdapter.from_config(
            [document],
            {
                "backend": "vera_hybrid",
                "sparse_weight": 0.4,
                "dense_weight": 0.6,
                "dense": {
                    "model_name": "example/embed",
                    "revision": "embed-revision",
                    "local_files_only": True,
                },
                "rerank": {
                    "enabled": True,
                    "model_name": "example/reranker",
                    "revision": "reranker-revision",
                    "candidate_k": 11,
                    "preserve_base_top_k": 1,
                },
            },
        )
    assert isinstance(adapter.retriever, _FakeRerankingRetriever)
    base = adapter.retriever.base_retriever
    assert base.kwargs == {"sparse_weight": 0.4, "dense_weight": 0.6}
    dense_config = base.config["dense"]
    assert isinstance(dense_config, dict)
    assert dense_config["model_name"] == "/snapshots/embed-revision/embed"
    assert resolve_model.call_count == 2
    assert adapter.retriever.reranker.kwargs["model_name"] == (
        "/snapshots/reranker-revision/reranker"
    )
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


@pytest.mark.skipif(importlib.util.find_spec("src") is None, reason="VeraRAG is not installed")
def test_vera_conflict_adapter_emits_graph_and_fallback_signals() -> None:
    detector = VeraConflictDetector({"conflict_graph": {"enable_nli": False}})
    numeric = detector.detect(
        ClaimNode(
            "C1",
            "Revenue was 20 million.",
            ClaimType.NUMERICAL,
            numbers=("20 million",),
        ),
        EvidenceDocument(
            "E1",
            "Revenue was 18 million in the audited report.",
            source="official",
        ),
    )
    assert numeric[0].conflict_type.value == "numerical"
    assert numeric[0].metadata["detector"] == "verarag_conflict_graph"
    assert numeric[0].metadata["resolver_strategy"] == "flag_for_verification"

    causal = detector.detect(
        ClaimNode(
            "C2",
            "The intervention caused the improvement.",
            ClaimType.CAUSAL,
        ),
        EvidenceDocument(
            "E2",
            "The intervention correlated with the improvement, but does not establish causality.",
            source="paper",
        ),
    )
    assert causal[0].conflict_type.value == "causal"
    assert causal[0].metadata["detector"] == "far_heuristic_fallback"

    batched = detector.detect_many(
        ClaimNode(
            "C3",
            "Revenue was 20 million.",
            ClaimType.NUMERICAL,
            numbers=("20 million",),
        ),
        (
            EvidenceDocument("E3", "Revenue was 18 million.", source="official"),
            EvidenceDocument("E4", "Revenue was 15 million.", source="report"),
        ),
    )
    assert {item.evidence_id for item in batched} == {"E3", "E4"}
    assert detector.builder.last_build_stats["claims"] == 3


@pytest.mark.skipif(importlib.util.find_spec("src") is None, reason="VeraRAG is not installed")
def test_vera_conflict_adapter_aligns_the_edge_claim_not_the_whole_document() -> None:
    detector = VeraConflictDetector({"conflict_graph": {"enable_nli": False}})
    conflicts = detector.detect(
        ClaimNode(
            "C1",
            "Willow has 105 qubits.",
            ClaimType.NUMERICAL,
            entities=("Willow",),
            numbers=("105",),
        ),
        EvidenceDocument(
            "E1",
            "Willow has 105 qubits. A separate benchmark uses 5 trials.",
            source="paper",
        ),
    )
    assert not conflicts


@pytest.mark.skipif(importlib.util.find_spec("src") is None, reason="VeraRAG is not installed")
def test_vera_conflict_adapter_fails_closed_when_required_nli_is_unavailable() -> None:
    class _UnavailableNLIBuilder:
        _nli_tried = True
        _nli_available = False

        def build_graph(self, evidence: object, use_llm: bool) -> SimpleNamespace:
            del evidence, use_llm
            return SimpleNamespace(get_conflicts=lambda: [])

    detector = VeraConflictDetector(
        {"conflict_graph": {"enable_nli": True, "require_nli": True}},
        builder=_UnavailableNLIBuilder(),
    )
    with pytest.raises(RuntimeError, match="NLI was required"):
        detector.detect(
            ClaimNode("C1", "A claim.", ClaimType.FACTUAL),
            EvidenceDocument("E1", "Contrary evidence."),
        )


@pytest.mark.skipif(importlib.util.find_spec("src") is None, reason="VeraRAG is not installed")
def test_vera_conflict_adapter_detects_high_precision_corpus_entity_substitution() -> None:
    class _EmptyGraphBuilder:
        _nli_tried = False
        _nli_available = True

        def build_graph(self, evidence: object, use_llm: bool) -> SimpleNamespace:
            del evidence, use_llm
            return SimpleNamespace(get_conflicts=lambda: [])

    detector = VeraConflictDetector(
        {
            "conflict_graph": {
                "enable_nli": False,
                "enable_entity_lexicon_conflict": True,
                "entity_lexicon_similarity": 0.55,
            }
        },
        builder=_EmptyGraphBuilder(),
        entity_lexicon=("Rapidus", "chiplet", "2nm"),
    )
    conflicts = detector.detect(
        ClaimNode(
            "C1",
            "Rapidus的目标是量产chiplet先进制程芯片，计划2027年开始量产",
            ClaimType.FACTUAL,
        ),
        EvidenceDocument(
            "E1",
            "Rapidus计划2027年开始量产2nm芯片。",
            source="official",
            metadata={"entities": ["Rapidus", "2nm"]},
        ),
    )
    assert conflicts[0].conflict_type.value == "entity"
    assert conflicts[0].metadata["detector"] == "corpus_entity_lexicon"
    assert conflicts[0].metadata["unsupported_entities"] == ["chiplet"]

    unrelated = detector.detect(
        ClaimNode("C2", "Rapidus获得政府资金支持", ClaimType.FACTUAL),
        EvidenceDocument(
            "E2",
            "Rapidus计划2027年开始量产2nm芯片。",
            source="official",
            metadata={"entities": ["Rapidus", "2nm"]},
        ),
    )
    assert unrelated == ()
