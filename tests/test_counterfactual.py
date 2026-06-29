from __future__ import annotations

from far.claims import ClaimNode, ClaimType
from far.counterfactual import QueryKind, TypedQueryGenerator
from far.evidence_types import EvidenceRequirementAssigner, EvidenceType


def test_typed_query_protocol_emits_all_three_query_kinds() -> None:
    claim = ClaimNode("C1", "The policy took effect in 2024", ClaimType.TEMPORAL)
    requirements = EvidenceRequirementAssigner().assign(claim)
    queries = TypedQueryGenerator().generate(claim, requirements)
    assert {query.kind for query in queries} == set(QueryKind)
    assert {query.evidence_type for query in queries} == {EvidenceType.TEMPORAL}
    assert "different date" in next(
        query.text for query in queries if query.kind is QueryKind.REFUTATION
    )


def test_untyped_ablation_removes_type_specific_tactic() -> None:
    claim = ClaimNode("C1", "Revenue was 20 million", ClaimType.NUMERICAL, numbers=("20 million",))
    requirements = EvidenceRequirementAssigner().assign(claim)
    typed = TypedQueryGenerator().generate(claim, requirements)
    untyped = TypedQueryGenerator(typed=False).generate(claim, requirements)
    assert typed[1].tactic == "alternative measurement"
    assert untyped[1].tactic == "generic contradiction"
