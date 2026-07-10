"""Run FAR with the self-contained BM25 backend and no model or network calls."""

from far import EvidenceDocument, FARPipeline
from far.adapters import BM25Retriever

documents = [
    EvidenceDocument(
        "study",
        "Exercise is associated with lower blood pressure, but the observational "
        "study does not establish causality because residual confounding remains.",
    )
]
pipeline = FARPipeline(BM25Retriever(documents), top_k_per_query=1)
result = pipeline.run(
    "Does exercise cause lower blood pressure?",
    "Exercise causes lower blood pressure.",
)
print(result.revised_answer)
