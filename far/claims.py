"""Step 1: decompose an answer into a validated claim dependency graph."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from .protocols import TextGenerator


class ClaimType(str, Enum):
    FACTUAL = "factual"
    NUMERICAL = "numerical"
    TEMPORAL = "temporal"
    CAUSAL = "causal"
    COMPARATIVE = "comparative"
    DEFINITIONAL = "definitional"
    INFERENTIAL = "inferential"


@dataclass(frozen=True)
class ClaimNode:
    """An atomic, verifiable answer claim and its graph dependencies."""

    claim_id: str
    text: str
    claim_type: ClaimType
    depends_on: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    numbers: tuple[str, ...] = ()
    time_expressions: tuple[str, ...] = ()
    verifiable: bool = True
    confidence: float = 1.0
    source_reliability: str = "unknown"

    def __post_init__(self) -> None:
        if not self.claim_id.strip() or not self.text.strip():
            raise ValueError("claim_id and text must not be empty")
        if self.claim_id in self.depends_on:
            raise ValueError(f"claim {self.claim_id} cannot depend on itself")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("claim confidence must be in [0, 1]")
        if self.source_reliability not in {"unknown", "low", "standard", "high"}:
            raise ValueError("unsupported claim source reliability")

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim": self.text,
            "claim_type": self.claim_type.value,
            "depends_on": list(self.depends_on),
            "entities": list(self.entities),
            "numbers": list(self.numbers),
            "time_expressions": list(self.time_expressions),
            "verifiable": self.verifiable,
            "confidence": self.confidence,
            "source_reliability": self.source_reliability,
        }


@dataclass(frozen=True)
class ClaimGraph:
    """A directed acyclic graph whose edges point from claims to prerequisites."""

    claims: tuple[ClaimNode, ...]
    _by_id: dict[str, ClaimNode] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        by_id = {claim.claim_id: claim for claim in self.claims}
        if len(by_id) != len(self.claims):
            raise ValueError("claim IDs must be unique")
        for claim in self.claims:
            missing = set(claim.depends_on) - set(by_id)
            if missing:
                raise ValueError(f"claim {claim.claim_id} has missing dependencies: {missing}")
        object.__setattr__(self, "_by_id", by_id)
        self.topological_order()

    def get(self, claim_id: str) -> ClaimNode:
        return self._by_id[claim_id]

    def topological_order(self) -> tuple[ClaimNode, ...]:
        state: dict[str, int] = {}
        ordered: list[ClaimNode] = []

        def visit(claim_id: str) -> None:
            marker = state.get(claim_id, 0)
            if marker == 1:
                raise ValueError("claim dependency graph contains a cycle")
            if marker == 2:
                return
            state[claim_id] = 1
            claim = self._by_id[claim_id]
            for dependency in claim.depends_on:
                visit(dependency)
            state[claim_id] = 2
            ordered.append(claim)

        for claim in self.claims:
            visit(claim.claim_id)
        return tuple(ordered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": [claim.to_dict() for claim in self.claims],
            "edges": [
                {"source": dependency, "target": claim.claim_id}
                for claim in self.claims
                for dependency in claim.depends_on
            ],
        }


class ClaimDecomposer(Protocol):
    def decompose(self, answer: str) -> ClaimGraph: ...


class RuleBasedClaimDecomposer:
    """Conservative offline decomposition; an LLM implementation can replace it."""

    _SENTENCE = re.compile(
        r"(?<=[。！？!?;；])\s*|(?<!\d)\.(?!\d)\s*|"
        r"(?:，|,)\s*(?=但|不过|然而|but\b|however\b)|[\n]+",
        re.I,
    )
    _NUMBER = re.compile(
        r"(?<![A-Za-z0-9_.,])[+-]?\d+(?:[.,]\d+)*(?:%|％|万|亿|million|billion)?",
        re.I,
    )
    _TIME = re.compile(
        r"(?:19|20)\d{2}(?:[-年/]\d{1,2})?(?:[-月/]\d{1,2})?日?|"
        r"\b(?:Q[1-4]|spring|summer|autumn|fall|winter)\s+(?:19|20)\d{2}\b",
        re.I,
    )
    _CAUSAL = re.compile(
        r"导致|引起|造成|源于|因为|因此|因而|caus(?:e|es|ed|ing)|results? in|because of|due to",
        re.I,
    )
    _DEFINITION = re.compile(r"是指|定义为|指的是|means|is defined as|refers to", re.I)
    _COMPARATIVE = re.compile(
        r"高于|低于|多于|少于|增加|下降|better|worse|higher|lower|more than|less than", re.I
    )
    _INFERENCE_PREFIX = re.compile(r"^(?:因此|所以|由此|这表明|therefore|thus|hence)\b", re.I)
    _ENTITY = re.compile(r"[A-Z][A-Za-z0-9]*(?:[ -][A-Z][A-Za-z0-9]*)*|[\u4e00-\u9fff]{2,12}")
    _LOW_RELIABILITY_PREFIX = re.compile(
        r"^An unverified secondary summary reports:\s*",
        re.I,
    )

    def decompose(self, answer: str) -> ClaimGraph:
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("answer must be a non-empty string")
        source_reliability = "unknown"
        if self._LOW_RELIABILITY_PREFIX.match(answer.strip()):
            source_reliability = "low"
            answer = self._LOW_RELIABILITY_PREFIX.sub("", answer.strip(), count=1)
        segments = [self._clean(part) for part in self._SENTENCE.split(answer)]
        segments = [segment for segment in segments if segment]
        claims: list[ClaimNode] = []
        for index, text in enumerate(segments, start=1):
            claim_type = self._infer_type(text)
            depends_on: tuple[str, ...] = ()
            if claims and (
                claim_type is ClaimType.INFERENTIAL or self._INFERENCE_PREFIX.search(text)
            ):
                depends_on = (claims[-1].claim_id,)
            claims.append(
                ClaimNode(
                    claim_id=f"C{index}",
                    text=text,
                    claim_type=claim_type,
                    depends_on=depends_on,
                    entities=tuple(dict.fromkeys(self._ENTITY.findall(text))),
                    numbers=tuple(self._NUMBER.findall(text)),
                    time_expressions=tuple(self._TIME.findall(text)),
                    verifiable=not self._looks_subjective(text),
                    source_reliability=source_reliability,
                )
            )
        return ClaimGraph(tuple(claims))

    @staticmethod
    def _clean(text: str) -> str:
        return text.strip().strip("。！？!?;； ")

    def _infer_type(self, text: str) -> ClaimType:
        if self._CAUSAL.search(text):
            return ClaimType.CAUSAL
        if self._DEFINITION.search(text):
            return ClaimType.DEFINITIONAL
        time_matches = tuple(self._TIME.finditer(text))
        number_matches = tuple(self._NUMBER.finditer(text))
        has_non_temporal_number = any(
            not any(
                time_match.start() <= number_match.start()
                and number_match.end() <= time_match.end()
                for time_match in time_matches
            )
            for number_match in number_matches
        )
        if has_non_temporal_number:
            return ClaimType.NUMERICAL
        if time_matches:
            return ClaimType.TEMPORAL
        if number_matches:
            return ClaimType.NUMERICAL
        if self._COMPARATIVE.search(text):
            return ClaimType.COMPARATIVE
        if self._INFERENCE_PREFIX.search(text):
            return ClaimType.INFERENTIAL
        return ClaimType.FACTUAL

    @staticmethod
    def _looks_subjective(text: str) -> bool:
        lowered = text.lower()
        return any(
            marker in lowered
            for marker in (
                "我认为",
                "我觉得",
                "in my opinion",
                "这个说法不准确",
                "这个说法不正确",
                "这一说法不准确",
                "这一说法不正确",
                "this claim is inaccurate",
                "this statement is inaccurate",
            )
        )


class LLMClaimDecomposer:
    """Validated LLM decomposition with a deterministic conservative fallback."""

    def __init__(self, generator: TextGenerator, fallback: ClaimDecomposer | None = None) -> None:
        self.generator = generator
        self.fallback = fallback or RuleBasedClaimDecomposer()

    def decompose(self, answer: str) -> ClaimGraph:
        prompt = (
            "Decompose the answer into minimal verifiable claims and dependency edges. "
            "Preserve every entity, number, time expression, negation, and scope; add no facts. "
            'Return JSON only as {"claims":[{"claim_id":"C1","claim":"...",'
            '"type":"factual|numerical|temporal|causal|comparative|definitional|inferential",'
            '"depends_on":[],"source_reliability":"unknown|low|standard|high"}]}.\n'
            "When the answer is attributed to an unverified secondary summary, mark every "
            "derived claim as low reliability. Answer: "
            f"{answer}"
        )
        try:
            response = self.generator.complete(
                prompt,
                system_prompt=(
                    "You are a conservative claim decomposition parser. Output JSON only."
                ),
                temperature=0.0,
                max_tokens=1200,
            )
            payload = self._parse_json(response)
            claims = tuple(self._claim(row) for row in payload["claims"])
            graph = ClaimGraph(claims)
            if not self._source_coverage(answer, graph):
                raise ValueError("LLM decomposition does not preserve source content")
            return graph
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return self.fallback.decompose(answer)

    @staticmethod
    def _parse_json(response: str) -> dict[str, Any]:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
        value = json.loads(cleaned)
        if not isinstance(value, dict) or not isinstance(value.get("claims"), list):
            raise ValueError("claim decomposition must be a JSON object with a claims list")
        return value

    def _claim(self, row: Any) -> ClaimNode:
        if not isinstance(row, dict):
            raise ValueError("claim rows must be objects")
        text = str(row["claim"])
        # The LLM is responsible for atomic boundaries and dependencies, but
        # downstream typed retrieval/conflict logic must never depend on it
        # remembering to emit fields that are not part of the JSON contract.
        # Reparse every accepted claim deterministically and aggregate all
        # fragments defensively in case a provider returns a multi-sentence
        # claim despite the atomicity instruction.
        parsed = RuleBasedClaimDecomposer().decompose(text)
        return ClaimNode(
            claim_id=str(row["claim_id"]),
            text=text,
            claim_type=ClaimType(str(row["type"])),
            depends_on=tuple(str(item) for item in row.get("depends_on", [])),
            entities=tuple(
                dict.fromkeys(entity for claim in parsed.claims for entity in claim.entities)
            ),
            numbers=tuple(
                dict.fromkeys(number for claim in parsed.claims for number in claim.numbers)
            ),
            time_expressions=tuple(
                dict.fromkeys(
                    expression
                    for claim in parsed.claims
                    for expression in claim.time_expressions
                )
            ),
            verifiable=all(claim.verifiable for claim in parsed.claims),
            source_reliability=str(row.get("source_reliability", "unknown")),
        )

    @staticmethod
    def _source_coverage(answer: str, graph: ClaimGraph) -> bool:
        answer = RuleBasedClaimDecomposer._LOW_RELIABILITY_PREFIX.sub("", answer.strip(), count=1)
        source_tokens = set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", answer.lower()))
        claim_tokens = set(
            re.findall(
                r"[A-Za-z0-9]+|[\u4e00-\u9fff]",
                " ".join(claim.text for claim in graph.claims).lower(),
            )
        )
        # Claim decomposition may split and reorder text, but it may neither
        # omit source vocabulary nor introduce vocabulary that was not present
        # in the answer. A weaker recall-only threshold allowed the decomposer
        # to smuggle alternatives into a claim while still covering most of the
        # source, changing the proposition before falsification even started.
        compact_source = re.sub(r"[\W_]+", "", answer.lower())
        compact_claims = [
            re.sub(r"[\W_]+", "", claim.text.lower()) for claim in graph.claims
        ]
        claims_are_source_spans = all(
            bool(compact_claim) and compact_claim in compact_source
            for compact_claim in compact_claims
        )
        return bool(source_tokens) and claim_tokens == source_tokens and claims_are_source_spans
