from __future__ import annotations

from far.adapters import HeuristicConflictDetector, InMemoryRetriever
from far.models import EvidenceDocument
from far.pipeline import FARPipeline
from far.revision import RevisionAction


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
