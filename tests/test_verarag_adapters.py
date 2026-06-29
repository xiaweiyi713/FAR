from __future__ import annotations

import importlib.util

import pytest

from far.adapters import VeraLLMAdapter, VeraRetrieverAdapter
from far.models import EvidenceDocument


class _FakeLLMClient:
    def generate(self, prompt: str, **kwargs: object) -> str:
        return f"generated:{prompt}:{kwargs['temperature']}"


def test_llm_adapter_maps_the_stable_far_interface() -> None:
    adapter = VeraLLMAdapter(client=_FakeLLMClient())
    assert adapter.complete("claim", temperature=0.0) == "generated:claim:0.0"


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
