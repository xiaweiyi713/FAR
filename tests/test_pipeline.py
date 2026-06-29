from __future__ import annotations

from far.adapters import HeuristicConflictDetector, InMemoryRetriever
from far.claims import RuleBasedClaimDecomposer
from far.models import EvidenceDocument
from far.pipeline import FARPipeline
from far.revision import RevisionAction


class _AllRetriever:
    def __init__(self, documents: list[EvidenceDocument]) -> None:
        self.documents = documents

    def retrieve(self, query: str, top_k: int = 5) -> list[EvidenceDocument]:
        del query
        return self.documents[:top_k]


class _BatchOnlyDetector:
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def detect(self, claim: object, evidence: object) -> tuple[object, ...]:
        del claim, evidence
        raise AssertionError("pipeline should use detect_many when available")

    def detect_many(
        self, claim: object, evidence: tuple[EvidenceDocument, ...]
    ) -> tuple[object, ...]:
        del claim
        self.batch_sizes.append(len(evidence))
        return ()


def test_offline_pipeline_retrieves_counter_evidence_and_revises() -> None:
    documents = [
        EvidenceDocument(
            evidence_id="E1",
            title="Audited annual report",
            text="The audited report states revenue was 18 million, not the earlier estimate.",
            source="official",
            metadata={
                "conflict_type": "numerical",
                "refutes_claim": "C1",
                "suggested_revision": "Revenue was 18 million.",
            },
        )
    ]
    pipeline = FARPipeline(
        InMemoryRetriever(documents),
        conflict_detector=HeuristicConflictDetector(allow_oracle_metadata=True),
        top_k_per_query=1,
    )
    result = pipeline.run("What was revenue?", "Revenue was 20 million.")
    assert result.revised_answer == "Revenue was 18 million."
    assert result.revision_trace[0].action is RevisionAction.REPLACE_NUMERICAL
    assert {item.query.kind.value for item in result.retrieval_trace} == {
        "support",
        "refutation",
        "boundary",
    }
    assert result.conflicts["C1"][0].metadata == {"oracle_metadata": True}


def test_pipeline_causal_path_works_without_oracle_metadata() -> None:
    documents = [
        EvidenceDocument(
            evidence_id="E1",
            text=(
                "Exercise is associated with lower blood pressure, but the study does not "
                "establish causality because residual confounding remains."
            ),
        )
    ]
    result = FARPipeline(InMemoryRetriever(documents), top_k_per_query=1).run(
        "Does exercise cause lower blood pressure?",
        "Exercise causes lower blood pressure.",
    )
    assert result.revision_trace[0].action is RevisionAction.DOWNGRADE_CAUSAL


def test_heuristic_conflicts_require_topic_alignment() -> None:
    detector = HeuristicConflictDetector()
    claim = (
        RuleBasedClaimDecomposer()
        .decompose("Semiconductor revenue caused the market decline.")
        .claims[0]
    )
    unrelated = EvidenceDocument(
        "E1",
        "Exercise correlates with blood pressure but does not establish causality.",
    )
    assert detector.detect(claim, unrelated) == ()
    relevant = EvidenceDocument(
        "E2",
        "Semiconductor revenue declined, but the source does not establish "
        "the added causal relationship.",
    )
    conflicts = detector.detect(claim, relevant)
    assert conflicts[0].conflict_type.value == "causal"


def test_heuristic_topic_alignment_allows_entity_replacements() -> None:
    detector = HeuristicConflictDetector()
    claim = RuleBasedClaimDecomposer().decompose("信越化学和SpaceX占全球硅晶圆市场约60%").claims[0]
    evidence = EvidenceDocument(
        "E1",
        "主体不同: 信越化学和SUMCO占全球硅晶圆市场约60%，而SpaceX并非硅晶圆供应商。",
        source="report",
    )
    conflicts = detector.detect(claim, evidence)
    assert conflicts


def test_pipeline_batches_all_evidence_for_batch_capable_detector() -> None:
    detector = _BatchOnlyDetector()
    pipeline = FARPipeline(
        _AllRetriever(
            [
                EvidenceDocument("E1", "Revenue was 18 million."),
                EvidenceDocument("E2", "Revenue was 19 million."),
            ]
        ),
        conflict_detector=detector,  # type: ignore[arg-type]
        top_k_per_query=2,
    )
    pipeline.run("What was revenue?", "Revenue was 20 million.")
    assert detector.batch_sizes == [2]


def test_pipeline_skips_non_verifiable_discourse_claims() -> None:
    detector = _BatchOnlyDetector()
    result = FARPipeline(
        _AllRetriever([EvidenceDocument("E1", "Unrelated evidence is incorrect.")]),
        conflict_detector=detector,  # type: ignore[arg-type]
    ).run("Is the statement correct?", "这个说法不准确。")
    assert detector.batch_sizes == []
    assert result.revision_trace[0].action is RevisionAction.KEEP
    assert result.claim_graph.claims[0].verifiable is False
