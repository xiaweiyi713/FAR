"""Shared, dependency-light FAR data models."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvidenceDocument:
    """One retrievable evidence unit with provenance and an immutable identity."""

    evidence_id: str
    text: str
    title: str = ""
    source: str = "unknown"
    date: str | None = None
    url: str | None = None
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id must not be empty")
        if not self.text.strip():
            raise ValueError("evidence text must not be empty")
        if self.score < 0.0 or not math.isfinite(self.score):
            raise ValueError("evidence score must be finite and non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "text": self.text,
            "title": self.title,
            "source": self.source,
            "date": self.date,
            "url": self.url,
            "score": self.score,
            "metadata": dict(self.metadata),
        }
