"""Compatibility boundary between FAR and VeraRAG internals."""

from .conflict import HeuristicConflictDetector, VeraConflictDetector
from .llm import VeraLLMAdapter
from .retrieval import InMemoryRetriever, VeraRetrieverAdapter

__all__ = [
    "HeuristicConflictDetector",
    "InMemoryRetriever",
    "VeraConflictDetector",
    "VeraLLMAdapter",
    "VeraRetrieverAdapter",
]
