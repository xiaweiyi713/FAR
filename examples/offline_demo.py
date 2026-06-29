"""Run a deterministic FAR demo without an LLM or network access."""

from __future__ import annotations

import json

from far.adapters import HeuristicConflictDetector, InMemoryRetriever
from far.models import EvidenceDocument
from far.pipeline import FARPipeline


def main() -> None:
    documents = [
        EvidenceDocument(
            evidence_id="E-support",
            title="Observational study",
            text="The study observed that exercise and lower blood pressure are associated.",
            source="paper",
        ),
        EvidenceDocument(
            evidence_id="E-counter",
            title="Causal analysis",
            text=(
                "Exercise is associated with lower blood pressure, but the observational design "
                "does not establish causality and residual confounding remains."
            ),
            source="paper",
        ),
    ]
    pipeline = FARPipeline(
        InMemoryRetriever(documents),
        conflict_detector=HeuristicConflictDetector(),
    )
    result = pipeline.run(
        "Does exercise cause lower blood pressure?",
        "Exercise causes lower blood pressure.",
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
