"""Falsification-Augmented Retrieval public API."""

from .claims import ClaimGraph, ClaimNode, ClaimType, LLMClaimDecomposer, RuleBasedClaimDecomposer
from .counterfactual import (
    CounterfactualQuery,
    LLMTypedQueryGenerator,
    QueryKind,
    TypedQueryGenerator,
)
from .evidence_types import EvidenceRequirement, EvidenceType, TypedConflict
from .models import EvidenceDocument
from .pipeline import FARPipeline, FARResult
from .revision import LLMTypedRevisionEngine, RevisionAction, RevisionTrace, TypedRevisionEngine

__all__ = [
    "ClaimGraph",
    "ClaimNode",
    "ClaimType",
    "CounterfactualQuery",
    "EvidenceDocument",
    "EvidenceRequirement",
    "EvidenceType",
    "FARPipeline",
    "FARResult",
    "LLMClaimDecomposer",
    "LLMTypedQueryGenerator",
    "LLMTypedRevisionEngine",
    "QueryKind",
    "RevisionAction",
    "RevisionTrace",
    "RuleBasedClaimDecomposer",
    "TypedConflict",
    "TypedQueryGenerator",
    "TypedRevisionEngine",
]

__version__ = "0.1.0"
