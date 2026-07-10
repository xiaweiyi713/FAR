"""Compatibility boundary between FAR and VeraRAG internals."""

from .conflict import HeuristicConflictDetector, VeraConflictDetector
from .llm import VeraLLMAdapter
from .retrieval import BM25Retriever, InMemoryRetriever, VeraRetrieverAdapter

__all__ = [
    "BM25Retriever",
    "HeuristicConflictDetector",
    "InMemoryRetriever",
    "VeraConflictDetector",
    "VeraLLMAdapter",
    "VeraRetrieverAdapter",
]
