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


def test_decimal_points_do_not_split_claims() -> None:
    graph = RuleBasedClaimDecomposer().decompose("市场规模下降8.2%。这一变化并不证明因果关系。")
    assert [claim.text for claim in graph.claims] == [
        "市场规模下降8.2%",
        "这一变化并不证明因果关系",
    ]
    assert graph.claims[0].numbers == ("8.2%",)


def test_dated_measurement_is_numerical_not_merely_temporal() -> None:
    claim = (
        RuleBasedClaimDecomposer()
        .decompose("2023年市场规模为5270亿美元，较2022年下降8.2%。")
        .claims[0]
    )
    assert claim.claim_type is ClaimType.NUMERICAL
    assert claim.time_expressions == ("2023", "2022")
    assert "5270亿" in claim.numbers


def test_contrastive_conjunction_splits_independent_claims() -> None:
    graph = RuleBasedClaimDecomposer().decompose(
        "Willow拥有105个量子比特，但实用系统需要约100万个物理量子比特。"
    )
    assert [claim.text for claim in graph.claims] == [
        "Willow拥有105个量子比特",
        "但实用系统需要约100万个物理量子比特",
    ]


def test_low_reliability_attribution_propagates_to_every_atomic_claim() -> None:
    graph = RuleBasedClaimDecomposer().decompose(
        "An unverified secondary summary reports: Revenue was 20 million. Profit was 5 million."
    )
    assert [claim.text for claim in graph.claims] == [
        "Revenue was 20 million",
        "Profit was 5 million",
    ]
    assert {claim.source_reliability for claim in graph.claims} == {"low"}
