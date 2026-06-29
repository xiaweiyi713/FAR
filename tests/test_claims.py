from __future__ import annotations

import pytest

from far.claims import ClaimGraph, ClaimNode, ClaimType, RuleBasedClaimDecomposer


def test_decomposer_infers_types_and_dependency() -> None:
    graph = RuleBasedClaimDecomposer().decompose(
        "The trial enrolled 120 patients. Therefore, the treatment causes recovery."
    )
    assert [claim.claim_type for claim in graph.claims] == [
        ClaimType.NUMERICAL,
        ClaimType.CAUSAL,
    ]
    assert graph.claims[1].depends_on == ("C1",)
    assert [claim.claim_id for claim in graph.topological_order()] == ["C1", "C2"]


def test_claim_graph_rejects_cycles() -> None:
    with pytest.raises(ValueError, match="cycle"):
        ClaimGraph(
            (
                ClaimNode("C1", "one", ClaimType.FACTUAL, depends_on=("C2",)),
                ClaimNode("C2", "two", ClaimType.FACTUAL, depends_on=("C1",)),
            )
        )


def test_chinese_sentences_and_attached_numbers_are_decomposed() -> None:
    graph = RuleBasedClaimDecomposer().decompose("公司营收612亿元。员工总数41000人。")
    assert len(graph.claims) == 2
    assert graph.claims[0].numbers == ("612亿",)
    assert graph.claims[1].numbers == ("41000",)
