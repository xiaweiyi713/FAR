from __future__ import annotations

from far.claims import ClaimType, LLMClaimDecomposer
from far.counterfactual import LLMTypedQueryGenerator, QueryKind
from far.evidence_types import EvidenceRequirementAssigner
from far.revision import LLMTypedRevisionEngine, RevisionAction


class _QueueGenerator:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)

    def complete(self, prompt: str, **kwargs: object) -> str:
        del prompt, kwargs
        return self.responses.pop(0)


def test_llm_claim_decomposition_and_query_generation_are_validated() -> None:
    decomposer = LLMClaimDecomposer(
        _QueueGenerator(
            '{"claims":[{"claim_id":"C1","claim":"Revenue was 20 million",'
            '"type":"numerical","depends_on":[]}]}'
        )
    )
    graph = decomposer.decompose("Revenue was 20 million")
    assert graph.claims[0].claim_type is ClaimType.NUMERICAL
    assert graph.claims[0].entities == ("Revenue",)
    assert graph.claims[0].numbers == ("20",)
    query_generator = LLMTypedQueryGenerator(
        _QueueGenerator(
            '{"support":"official revenue 20 million",'
            '"refutation":"revised revenue different value",'
            '"boundary":"revenue period unit methodology"}'
        )
    )
    queries = query_generator.generate(
        graph.claims[0],
        EvidenceRequirementAssigner().assign(graph.claims[0]),
    )
    assert {item.kind for item in queries} == set(QueryKind)
    assert all(item.tactic.startswith("llm:") for item in queries)


def test_invalid_llm_structure_falls_back_without_losing_query_families() -> None:
    decomposer = LLMClaimDecomposer(_QueueGenerator("not json"))
    graph = decomposer.decompose("Revenue was 20 million")
    generator = LLMTypedQueryGenerator(_QueueGenerator('{"support":"only one"}'))
    queries = generator.generate(
        graph.claims[0],
        EvidenceRequirementAssigner().assign(graph.claims[0]),
    )
    assert {item.kind for item in queries} == set(QueryKind)
    assert not any(item.tactic.startswith("llm:") for item in queries)


def test_llm_claims_receive_deterministic_typed_attributes() -> None:
    decomposer = LLMClaimDecomposer(
        _QueueGenerator(
            '{"claims":[{"claim_id":"C1","claim":"Agent 于 2023 年离职",'
            '"type":"temporal","depends_on":[]}]}'
        )
    )
    claim = decomposer.decompose("Agent 于 2023 年离职").claims[0]
    assert "Agent" in claim.entities
    assert claim.time_expressions == ("2023",)


def test_llm_claim_decomposition_rejects_novel_vocabulary() -> None:
    answer = "碳中和有潜力。目前量子计算仍处于研究阶段。"
    decomposer = LLMClaimDecomposer(
        _QueueGenerator(
            '{"claims":[{"claim_id":"C1","claim":"碳中和(或量子计算)有潜力",'
            '"type":"factual","depends_on":[]},{"claim_id":"C2",'
            '"claim":"目前量子计算仍处于研究阶段","type":"factual",'
            '"depends_on":[]}]}'
        )
    )
    graph = decomposer.decompose(answer)
    assert [claim.text for claim in graph.claims] == [
        "碳中和有潜力",
        "目前量子计算仍处于研究阶段",
    ]


def test_llm_claim_decomposition_rejects_cross_clause_substitution() -> None:
    answer = "碳中和有潜力。目前量子计算仍处于研究阶段。"
    decomposer = LLMClaimDecomposer(
        _QueueGenerator(
            '{"claims":[{"claim_id":"C1","claim":"量子计算有潜力",'
            '"type":"factual","depends_on":[]},{"claim_id":"C2",'
            '"claim":"目前碳中和仍处于研究阶段","type":"factual",'
            '"depends_on":[]}]}'
        )
    )
    graph = decomposer.decompose(answer)
    assert [claim.text for claim in graph.claims] == [
        "碳中和有潜力",
        "目前量子计算仍处于研究阶段",
    ]


def test_llm_revision_realizes_deterministically_selected_action() -> None:
    from far.claims import ClaimNode
    from far.evidence_types import EvidenceType, TypedConflict

    claim = ClaimNode("C1", "Exercise causes recovery", ClaimType.CAUSAL)
    conflict = TypedConflict(
        "C1",
        "E1",
        EvidenceType.CAUSAL,
        0.9,
        "Observational evidence only.",
    )
    trace = LLMTypedRevisionEngine(
        _QueueGenerator("Exercise is associated with recovery; causality is not established.")
    ).revise(claim, (conflict,), ())
    assert trace.action is RevisionAction.DOWNGRADE_CAUSAL
    assert "associated" in trace.after
