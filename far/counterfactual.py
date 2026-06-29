"""Step 3: typed support, refutation, and boundary query generation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

from .claims import ClaimNode
from .evidence_types import EvidenceRequirement, EvidenceType
from .protocols import TextGenerator


class QueryKind(str, Enum):
    SUPPORT = "support"
    REFUTATION = "refutation"
    BOUNDARY = "boundary"


@dataclass(frozen=True)
class CounterfactualQuery:
    query_id: str
    claim_id: str
    kind: QueryKind
    evidence_type: EvidenceType
    text: str
    tactic: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "claim_id": self.claim_id,
            "kind": self.kind.value,
            "evidence_type": self.evidence_type.value,
            "text": self.text,
            "tactic": self.tactic,
        }


class TypedQueryGenerator:
    """Generate an explicit three-way falsification protocol for every claim."""

    _TACTICS: ClassVar[dict[EvidenceType, dict[QueryKind, tuple[str, str]]]] = {
        EvidenceType.TEMPORAL: {
            QueryKind.SUPPORT: ("dated corroboration", "official date timeline confirms"),
            QueryKind.REFUTATION: (
                "alternative date/version",
                "different date earlier later updated version",
            ),
            QueryKind.BOUNDARY: (
                "effective-time boundary",
                "as of effective from superseded timeline boundary",
            ),
        },
        EvidenceType.ENTITY: {
            QueryKind.SUPPORT: ("entity identity", "official identity same entity confirms"),
            QueryKind.REFUTATION: (
                "entity disambiguation",
                "different entity subsidiary parent namesake incorrect",
            ),
            QueryKind.BOUNDARY: (
                "entity scope",
                "entity scope subsidiary parent jurisdiction alias",
            ),
        },
        EvidenceType.NUMERICAL: {
            QueryKind.SUPPORT: (
                "measurement corroboration",
                "official statistic exact value confirms",
            ),
            QueryKind.REFUTATION: (
                "alternative measurement",
                "different value revised estimate correction",
            ),
            QueryKind.BOUNDARY: (
                "measurement comparability",
                "unit denominator period methodology not comparable",
            ),
        },
        EvidenceType.CAUSAL: {
            QueryKind.SUPPORT: (
                "causal identification",
                "causal mechanism experiment controls evidence",
            ),
            QueryKind.REFUTATION: (
                "causal alternative",
                "correlation only no causal evidence confounder third factor",
            ),
            QueryKind.BOUNDARY: (
                "causal scope",
                "conditions limitations heterogeneous effect setting",
            ),
        },
        EvidenceType.SOURCE_RELIABILITY: {
            QueryKind.SUPPORT: ("authoritative provenance", "primary official source confirms"),
            QueryKind.REFUTATION: (
                "source challenge",
                "retraction correction unreliable source disputed",
            ),
            QueryKind.BOUNDARY: (
                "source hierarchy",
                "primary secondary source methodology limitations",
            ),
        },
        EvidenceType.DEFINITION: {
            QueryKind.SUPPORT: ("definition agreement", "standard definition consensus means"),
            QueryKind.REFUTATION: (
                "definition disagreement",
                "alternative definition does not mean disputed terminology",
            ),
            QueryKind.BOUNDARY: (
                "definition boundary",
                "scope inclusion exclusion operational definition",
            ),
        },
        EvidenceType.COUNTER_EVIDENCE: {
            QueryKind.SUPPORT: ("direct corroboration", "evidence confirms true"),
            QueryKind.REFUTATION: (
                "direct falsification",
                "false incorrect contrary counterexample refutes",
            ),
            QueryKind.BOUNDARY: ("claim boundary", "exception limitation only under conditions"),
        },
    }
    _GENERIC: ClassVar[dict[QueryKind, tuple[str, str]]] = {
        QueryKind.SUPPORT: ("generic support", "evidence supporting confirms"),
        QueryKind.REFUTATION: ("generic contradiction", "evidence contradicts false incorrect"),
        QueryKind.BOUNDARY: ("generic limitation", "limitations exceptions conditions"),
    }

    def __init__(
        self,
        *,
        typed: bool = True,
        include_refutation: bool = True,
        include_boundary: bool = True,
    ) -> None:
        self.typed = typed
        self.include_refutation = include_refutation
        self.include_boundary = include_boundary

    def generate(
        self,
        claim: ClaimNode,
        requirements: tuple[EvidenceRequirement, ...],
    ) -> tuple[CounterfactualQuery, ...]:
        primary = self._primary_requirement(requirements)
        kinds = [QueryKind.SUPPORT]
        if self.include_refutation:
            kinds.append(QueryKind.REFUTATION)
        if self.include_boundary:
            kinds.append(QueryKind.BOUNDARY)
        queries = [self._build(claim, primary, kind) for kind in kinds]
        return tuple(queries)

    def _build(
        self,
        claim: ClaimNode,
        requirement: EvidenceRequirement,
        kind: QueryKind,
    ) -> CounterfactualQuery:
        tactics = self._TACTICS[requirement.evidence_type] if self.typed else self._GENERIC
        tactic, expansion = tactics[kind]
        anchors = self._anchors(claim, requirement.evidence_type)
        query_text = " ".join(part for part in (claim.text, anchors, expansion) if part).strip()
        digest = hashlib.sha1(query_text.encode("utf-8")).hexdigest()[:10]
        return CounterfactualQuery(
            query_id=f"{claim.claim_id}-{kind.value}-{digest}",
            claim_id=claim.claim_id,
            kind=kind,
            evidence_type=requirement.evidence_type,
            text=query_text,
            tactic=tactic,
        )

    @staticmethod
    def _primary_requirement(
        requirements: tuple[EvidenceRequirement, ...],
    ) -> EvidenceRequirement:
        if not requirements:
            raise ValueError("at least one evidence requirement is required")
        non_generic = [
            item
            for item in requirements
            if item.evidence_type
            not in {EvidenceType.SOURCE_RELIABILITY, EvidenceType.COUNTER_EVIDENCE}
        ]
        candidates = non_generic or list(requirements)
        return max(candidates, key=lambda item: item.priority)

    @staticmethod
    def _anchors(claim: ClaimNode, evidence_type: EvidenceType) -> str:
        values: tuple[str, ...] = ()
        if evidence_type is EvidenceType.TEMPORAL:
            values = claim.time_expressions
        elif evidence_type is EvidenceType.NUMERICAL:
            values = claim.numbers
        elif evidence_type is EvidenceType.ENTITY:
            values = claim.entities
        cleaned = [re.sub(r"\s+", " ", value).strip() for value in values if value.strip()]
        return " ".join(dict.fromkeys(cleaned))


class LLMTypedQueryGenerator(TypedQueryGenerator):
    """Model-generated typed queries with strict three-family validation and fallback."""

    def __init__(
        self,
        generator: TextGenerator,
        *,
        typed: bool = True,
        include_refutation: bool = True,
        include_boundary: bool = True,
    ) -> None:
        super().__init__(
            typed=typed,
            include_refutation=include_refutation,
            include_boundary=include_boundary,
        )
        self.generator = generator

    def generate(
        self,
        claim: ClaimNode,
        requirements: tuple[EvidenceRequirement, ...],
    ) -> tuple[CounterfactualQuery, ...]:
        fallback = super().generate(claim, requirements)
        primary = self._primary_requirement(requirements)
        required_kinds = [item.kind for item in fallback]
        prompt = (
            f"Claim: {claim.text}\nEvidence type: {primary.evidence_type.value}\n"
            "Generate distinct retrieval queries that test this claim. The support query seeks "
            "corroboration; the refutation query seeks evidence that could make it false; the "
            "boundary query seeks scope, definition, time, unit, or comparability limits. "
            "Return JSON only with keys support, refutation, boundary and short query strings."
        )
        try:
            response = self.generator.complete(
                prompt,
                system_prompt=(
                    "Generate falsification-oriented retrieval queries. Output JSON only."
                ),
                temperature=0.0,
                max_tokens=500,
            )
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
            payload = json.loads(cleaned)
            if not isinstance(payload, dict):
                raise ValueError("query output must be an object")
            queries = []
            for fallback_query in fallback:
                value = payload.get(fallback_query.kind.value)
                if not isinstance(value, str) or len(value.strip()) < 4:
                    raise ValueError(f"missing {fallback_query.kind.value} query")
                text = value.strip()
                digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
                queries.append(
                    CounterfactualQuery(
                        query_id=f"{claim.claim_id}-{fallback_query.kind.value}-{digest}",
                        claim_id=claim.claim_id,
                        kind=fallback_query.kind,
                        evidence_type=primary.evidence_type,
                        text=text,
                        tactic=f"llm:{fallback_query.tactic}",
                    )
                )
            if [item.kind for item in queries] != required_kinds:
                raise ValueError("LLM query families do not match the requested ablation")
            return tuple(queries)
        except (json.JSONDecodeError, TypeError, ValueError):
            return fallback
