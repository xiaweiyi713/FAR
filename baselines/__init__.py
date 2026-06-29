"""Baseline systems used in FAR comparisons."""

from .common import BaselinePrediction
from .crag import CRAGStyleBaseline
from .multi_query_rag import MultiQueryRAG
from .reflective_rag import ReflectiveRAG
from .self_rag import SelfRAGStyleBaseline
from .vanilla_rag import VanillaRAG

__all__ = [
    "BaselinePrediction",
    "CRAGStyleBaseline",
    "MultiQueryRAG",
    "ReflectiveRAG",
    "SelfRAGStyleBaseline",
    "VanillaRAG",
]
