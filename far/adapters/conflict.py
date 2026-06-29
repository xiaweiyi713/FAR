"""Conflict detection adapters: transparent offline rules and VeraRAG reuse."""

from __future__ import annotations

import re
from typing import Any, ClassVar, Protocol

from ..claims import ClaimNode, ClaimType, RuleBasedClaimDecomposer
from ..evidence_types import EvidenceType, TypedConflict
from ..models import EvidenceDocument
from .model_assets import resolve_huggingface_snapshot


class ConflictDetector(Protocol):
    def detect(
        self,
        claim: ClaimNode,
        evidence: EvidenceDocument,
    ) -> tuple[TypedConflict, ...]: ...


class HeuristicConflictDetector:
    """High-precision rules suitable for offline runs; no hidden model calls."""

    _NUMBER = re.compile(
        r"(?<![A-Za-z0-9_.,])[+-]?\d+(?:[.,]\d+)*(?:%|％|万|亿|million|billion)?",
        re.I,
    )
    _TIME = re.compile(r"(?:19|20)\d{2}(?:[-年/]\d{1,2})?(?:[-月/]\d{1,2})?日?", re.I)
    _CAUSAL_DENIAL = re.compile(
        r"仅.{0,5}相关|只是相关|不能.{0,8}(?:证明|确认).{0,8}因果|并非因果|第三.{0,3}因素|"
        r"correlation (?:only|not causation)|does not .{0,40}caus|confound(?:er|ing)",
        re.I,
    )
    _REFUTE = re.compile(
        r"\b(?:false|incorrect|wrong|refut(?:e|es|ed)|contrary|not true)\b|"
        r"错误|不正确|并非如此|事实并非|反例|予以否认",
        re.I,
    )
    _DEFINITION = re.compile(
        r"定义不同|口径不同|does not mean|alternative definition|operational definition", re.I
    )
    _ENTITY = re.compile(
        r"主体不同|并非同一|母公司|子公司|namesake|different entit|subsidiary|parent company", re.I
    )
    _TOPIC_TERM = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}|[\u4e00-\u9fff]{2,12}")
    _TOPIC_STOP: ClassVar[set[str]] = {
        "answer",
        "claim",
        "evidence",
        "factor",
        "result",
        "source",
        "study",
        "that",
        "the",
        "this",
        "完全",
        "关系",
        "因果",
        "因素",
        "导致",
        "所述",
        "结果",
        "证据",
        "不准确",
        "不正确",
        "这个",
        "这一",
        "说法",
    }

    def __init__(self, *, allow_oracle_metadata: bool = False) -> None:
        self.allow_oracle_metadata = allow_oracle_metadata

    def detect(
        self,
        claim: ClaimNode,
        evidence: EvidenceDocument,
    ) -> tuple[TypedConflict, ...]:
        if self.allow_oracle_metadata:
            seeded = self._from_metadata(claim, evidence)
            if seeded is not None:
                return (seeded,)

        text = evidence.text
        if not self._topically_aligned(claim, text):
            return ()
        conflict_type: EvidenceType | None = None
        rationale = ""
        confidence = 0.0

        if claim.claim_type is ClaimType.CAUSAL and self._CAUSAL_DENIAL.search(text):
            conflict_type = EvidenceType.CAUSAL
            rationale = (
                "Evidence explicitly limits the claim to association or identifies confounding."
            )
            confidence = 0.92
        elif claim.claim_type is ClaimType.TEMPORAL and self._temporal_conflict(claim, text):
            conflict_type = EvidenceType.TEMPORAL
            rationale = "Evidence reports a different date or temporal version."
            confidence = 0.82
        elif claim.claim_type in {
            ClaimType.NUMERICAL,
            ClaimType.COMPARATIVE,
        } and self._numeric_conflict(claim, text):
            conflict_type = EvidenceType.NUMERICAL
            rationale = "Evidence reports a different value for the claim's measurement."
            confidence = 0.82
        elif self._ENTITY.search(text):
            conflict_type = EvidenceType.ENTITY
            rationale = "Evidence distinguishes the named entity or organizational scope."
            confidence = 0.86
        elif self._DEFINITION.search(text):
            conflict_type = EvidenceType.DEFINITION
            rationale = "Evidence uses or identifies a materially different definition."
            confidence = 0.85
        elif claim.claim_type in {ClaimType.FACTUAL, ClaimType.INFERENTIAL} and self._REFUTE.search(
            text
        ):
            conflict_type = EvidenceType.COUNTER_EVIDENCE
            rationale = "Evidence explicitly rejects or supplies a counterexample to the claim."
            confidence = 0.88

        if conflict_type is None:
            return ()
        if claim.source_reliability == "low" and evidence.source in {
            "official",
            "paper",
            "report",
            "wiki",
        }:
            conflict_type = EvidenceType.SOURCE_RELIABILITY
            rationale = (
                "An explicitly low-reliability claim conflicts with attributable evidence: "
                f"{rationale}"
            )
            confidence = max(confidence, 0.9)
        return (
            TypedConflict(
                claim_id=claim.claim_id,
                evidence_id=evidence.evidence_id,
                conflict_type=conflict_type,
                confidence=confidence,
                rationale=rationale,
                strength="strong" if confidence >= 0.85 else "weak",
            ),
        )

    @classmethod
    def _topic_terms(cls, text: str) -> set[str]:
        terms: set[str] = set()
        for token in cls._TOPIC_TERM.findall(text):
            lowered = token.lower()
            if lowered not in cls._TOPIC_STOP:
                terms.add(lowered)
            if re.fullmatch(r"[\u4e00-\u9fff]+", token):
                terms.update(
                    token[index : index + size]
                    for size in (2, 3)
                    for index in range(max(0, len(token) - size + 1))
                    if token[index : index + size] not in cls._TOPIC_STOP
                )
        return terms

    @classmethod
    def _topically_aligned(cls, claim: ClaimNode, text: str) -> bool:
        lowered = text.lower()
        named_entities = [
            entity
            for entity in claim.entities
            if re.fullmatch(r"[A-Z][A-Za-z0-9_-]{2,}", entity)
            and entity.lower() not in cls._TOPIC_STOP
        ]
        if named_entities:
            return any(entity.lower() in lowered for entity in named_entities)
        claim_terms = cls._topic_terms(claim.text)
        shared = claim_terms & cls._topic_terms(text)
        required = 1 if len(claim_terms) <= 3 else max(2, round(len(claim_terms) * 0.35))
        return len(shared) >= required

    def _from_metadata(
        self,
        claim: ClaimNode,
        evidence: EvidenceDocument,
    ) -> TypedConflict | None:
        raw_type = evidence.metadata.get("conflict_type")
        refutes = evidence.metadata.get("refutes_claim")
        if raw_type is None and refutes not in {claim.claim_id, claim.text, True}:
            return None
        aliases = {
            "temporal_conflict": EvidenceType.TEMPORAL,
            "temporal": EvidenceType.TEMPORAL,
            "entity_mismatch": EvidenceType.ENTITY,
            "entity": EvidenceType.ENTITY,
            "numeric_conflict": EvidenceType.NUMERICAL,
            "numerical": EvidenceType.NUMERICAL,
            "causal_conflict": EvidenceType.CAUSAL,
            "causal": EvidenceType.CAUSAL,
            "source_disagreement": EvidenceType.SOURCE_RELIABILITY,
            "source_reliability": EvidenceType.SOURCE_RELIABILITY,
            "definitional_conflict": EvidenceType.DEFINITION,
            "definition": EvidenceType.DEFINITION,
            "refute": EvidenceType.COUNTER_EVIDENCE,
            "counter_evidence": EvidenceType.COUNTER_EVIDENCE,
        }
        conflict_type = aliases.get(str(raw_type), EvidenceType.COUNTER_EVIDENCE)
        return TypedConflict(
            claim_id=claim.claim_id,
            evidence_id=evidence.evidence_id,
            conflict_type=conflict_type,
            confidence=float(evidence.metadata.get("conflict_confidence", 1.0)),
            rationale=str(
                evidence.metadata.get("conflict_rationale", "Gold/demo conflict metadata.")
            ),
            strength=str(evidence.metadata.get("strength", "strong")),
            suggested_revision=(
                str(evidence.metadata["suggested_revision"])
                if evidence.metadata.get("suggested_revision")
                else None
            ),
            metadata={"oracle_metadata": True},
        )

    def _numeric_conflict(self, claim: ClaimNode, text: str) -> bool:
        if not claim.numbers:
            return False
        evidence_numbers = set(self._NUMBER.findall(text))
        claim_numbers = set(claim.numbers)
        return bool(evidence_numbers and claim_numbers.isdisjoint(evidence_numbers))

    def _temporal_conflict(self, claim: ClaimNode, text: str) -> bool:
        if not claim.time_expressions:
            return False
        evidence_times = set(self._TIME.findall(text))
        claim_times = set(claim.time_expressions)
        return bool(evidence_times and claim_times.isdisjoint(evidence_times))


class VeraConflictDetector:
    """Reuse VeraRAG's layered graph with a transparent high-precision fallback."""

    _TERM = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,12}")
    _STOP_TERMS: ClassVar[set[str]] = {
        "the",
        "and",
        "was",
        "were",
        "with",
        "from",
        "that",
        "this",
        "report",
        "study",
        "evidence",
        "answer",
        "claim",
        "factor",
        "result",
        "source",
        "数据",
        "报告",
        "研究",
        "显示",
        "认为",
        "完全",
        "关系",
        "因果",
        "因素",
        "导致",
        "所述",
        "结果",
        "证据",
    }

    _TYPE_MAP: ClassVar[dict[str, EvidenceType]] = {
        "refute": EvidenceType.COUNTER_EVIDENCE,
        "numeric_conflict": EvidenceType.NUMERICAL,
        "temporal_conflict": EvidenceType.TEMPORAL,
        "entity_mismatch": EvidenceType.ENTITY,
        "source_disagreement": EvidenceType.SOURCE_RELIABILITY,
        "definitional_conflict": EvidenceType.DEFINITION,
        "scope_conflict": EvidenceType.DEFINITION,
        "causal_conflict": EvidenceType.CAUSAL,
        "granularity_conflict": EvidenceType.DEFINITION,
    }

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        builder: Any | None = None,
        fallback: ConflictDetector | None = None,
    ) -> None:
        safe_config = dict(config or {})
        conflict_config = dict(safe_config.get("conflict_graph", {}))
        self.require_nli = bool(conflict_config.get("require_nli", False))
        if conflict_config.get("nli_model"):
            conflict_config["nli_model"] = resolve_huggingface_snapshot(
                str(conflict_config["nli_model"]),
                (
                    str(conflict_config["nli_revision"])
                    if conflict_config.get("nli_revision")
                    else None
                ),
                local_files_only=bool(conflict_config.get("nli_local_files_only", False)),
            )
        self.fallback = fallback or HeuristicConflictDetector()
        self.decomposer = RuleBasedClaimDecomposer()
        if builder is None:
            try:
                from src.evidence.conflict_graph import ConflictGraphBuilder
            except ImportError as exc:
                raise RuntimeError("VeraRAG is required for VeraConflictDetector") from exc
            conflict_config.setdefault("enable_nli", False)
            if self.require_nli and not conflict_config["enable_nli"]:
                raise ValueError("conflict_graph.require_nli requires enable_nli=true")
            safe_config["conflict_graph"] = conflict_config
            builder = ConflictGraphBuilder(safe_config)
        self.builder = builder

    @classmethod
    def _terms(cls, text: str) -> set[str]:
        terms: set[str] = set()
        for token in cls._TERM.findall(text):
            lowered = token.lower()
            if lowered not in cls._STOP_TERMS:
                terms.add(lowered)
            if re.fullmatch(r"[\u4e00-\u9fff]+", token):
                terms.update(
                    token[index : index + size]
                    for size in (2, 3)
                    for index in range(max(0, len(token) - size + 1))
                )
        return terms

    @classmethod
    def _shared_terms(cls, left: str, right: str) -> tuple[str, ...]:
        left_terms = cls._terms(left)
        shared = left_terms & cls._terms(right)
        required = 1 if len(left_terms) <= 3 else max(2, round(len(left_terms) * 0.2))
        if len(shared) < required:
            return ()
        return tuple(sorted(shared, key=lambda item: (-len(item), item))[:12])

    def _parsed_claim(self, text: str) -> ClaimNode:
        return self.decomposer.decompose(text).claims[0]

    @staticmethod
    def _merge(*groups: tuple[str, ...]) -> list[str]:
        return list(dict.fromkeys(item for group in groups for item in group))

    def detect(
        self,
        claim: ClaimNode,
        evidence: EvidenceDocument,
    ) -> tuple[TypedConflict, ...]:
        return self.detect_many(claim, (evidence,))

    def detect_many(
        self,
        claim: ClaimNode,
        evidence: tuple[EvidenceDocument, ...],
    ) -> tuple[TypedConflict, ...]:
        if not evidence:
            return ()
        try:
            from src.utils.data_structures import Claim, Evidence
            from src.utils.data_structures import ClaimType as VeraClaimType
        except ImportError as exc:
            raise RuntimeError("VeraRAG data structures are unavailable") from exc
        type_map = {
            ClaimType.FACTUAL: VeraClaimType.FACTUAL,
            ClaimType.NUMERICAL: VeraClaimType.NUMERICAL,
            ClaimType.TEMPORAL: VeraClaimType.TEMPORAL,
            ClaimType.CAUSAL: VeraClaimType.CAUSAL,
            ClaimType.COMPARATIVE: VeraClaimType.COMPARATIVE,
            ClaimType.DEFINITIONAL: VeraClaimType.DEFINITIONAL,
            ClaimType.INFERENTIAL: VeraClaimType.UNCERTAINTY,
        }
        source_claim_id = f"far:{claim.claim_id}"
        parsed_source = self._parsed_claim(claim.text)
        shared_by_evidence = {
            item.evidence_id: self._shared_terms(claim.text, item.text) for item in evidence
        }
        evidence_by_id = {item.evidence_id: item for item in evidence}
        fallback_by_evidence = {
            item.evidence_id: self.fallback.detect(claim, item) for item in evidence
        }
        all_shared_terms = tuple(
            dict.fromkeys(
                term for item in evidence for term in shared_by_evidence[item.evidence_id]
            )
        )
        claim_evidence = Evidence(
            evidence_id=f"claim:{claim.claim_id}",
            source="far_initial_answer",
            title="Initial answer claim",
            text_span=claim.text,
            claims=[
                Claim(
                    claim_id=source_claim_id,
                    claim=claim.text,
                    claim_type=type_map[claim.claim_type],
                    entities=self._merge(
                        claim.entities,
                        parsed_source.entities,
                        all_shared_terms,
                    ),
                    numbers=self._merge(claim.numbers, parsed_source.numbers),
                    time_expressions=self._merge(
                        claim.time_expressions,
                        parsed_source.time_expressions,
                    ),
                )
            ],
        )
        evidence_claim_to_document: dict[str, str] = {}
        vera_evidence = [claim_evidence]
        for item in evidence:
            parsed_evidence = self.decomposer.decompose(item.text).claims
            shared_terms = shared_by_evidence[item.evidence_id]
            vera_claims = []
            for index, evidence_claim in enumerate(parsed_evidence, start=1):
                evidence_claim_id = f"far-evidence:{item.evidence_id}:{index}"
                evidence_claim_to_document[evidence_claim_id] = item.evidence_id
                vera_claims.append(
                    Claim(
                        claim_id=evidence_claim_id,
                        claim=evidence_claim.text,
                        claim_type=type_map[evidence_claim.claim_type],
                        entities=self._merge(evidence_claim.entities, shared_terms),
                        numbers=list(evidence_claim.numbers),
                        time_expressions=list(evidence_claim.time_expressions),
                    )
                )
            vera_evidence.append(
                Evidence(
                    evidence_id=item.evidence_id,
                    source=item.source,
                    title=item.title,
                    text_span=item.text,
                    date=item.date,
                    url=item.url,
                    entities=list(shared_terms),
                    claims=vera_claims,
                )
            )
        graph = self.builder.build_graph(vera_evidence, use_llm=False)
        if (
            self.require_nli
            and bool(getattr(self.builder, "_nli_tried", False))
            and not bool(getattr(self.builder, "_nli_available", False))
        ):
            raise RuntimeError(
                "VeraRAG NLI was required but the configured model could not be loaded. "
                "Install the dense/model dependencies and cache the configured NLI model."
            )
        conflicts: list[TypedConflict] = []
        for edge in graph.get_conflicts():
            endpoints = {edge.source_id, edge.target_id}
            evidence_claim_ids = endpoints & set(evidence_claim_to_document)
            if source_claim_id not in endpoints or not evidence_claim_ids:
                continue
            raw_conflict_type = edge.conflict_type.value
            if raw_conflict_type == "source_disagreement":
                continue
            conflict_type = self._TYPE_MAP.get(raw_conflict_type)
            if conflict_type is None:
                continue
            evidence_claim_id = next(iter(evidence_claim_ids))
            evidence_id = evidence_claim_to_document[evidence_claim_id]
            if not HeuristicConflictDetector._topically_aligned(
                claim,
                evidence_by_id[evidence_id].text,
            ):
                continue
            fallback_conflicts = fallback_by_evidence[evidence_id]
            if conflict_type is EvidenceType.COUNTER_EVIDENCE:
                if fallback_conflicts:
                    conflict_type = fallback_conflicts[0].conflict_type
                else:
                    conflict_type = {
                        ClaimType.CAUSAL: EvidenceType.CAUSAL,
                        ClaimType.NUMERICAL: EvidenceType.NUMERICAL,
                        ClaimType.COMPARATIVE: EvidenceType.NUMERICAL,
                        ClaimType.TEMPORAL: EvidenceType.TEMPORAL,
                        ClaimType.DEFINITIONAL: EvidenceType.DEFINITION,
                    }.get(claim.claim_type, EvidenceType.COUNTER_EVIDENCE)
            if (
                raw_conflict_type == "granularity_conflict"
                and claim.claim_type in {ClaimType.FACTUAL, ClaimType.TEMPORAL}
                and any(
                    re.fullmatch(r"[A-Z][A-Za-z0-9_-]{2,}", entity)
                    and entity.lower() in evidence_by_id[evidence_id].text.lower()
                    for entity in claim.entities
                )
            ):
                conflict_type = EvidenceType.ENTITY
            if claim.source_reliability == "low" and evidence_by_id[evidence_id].source in {
                "official",
                "paper",
                "report",
                "wiki",
            }:
                conflict_type = EvidenceType.SOURCE_RELIABILITY
            conflicts.append(
                TypedConflict(
                    claim_id=claim.claim_id,
                    evidence_id=evidence_id,
                    conflict_type=conflict_type,
                    confidence=float(edge.confidence),
                    rationale=(
                        "An explicitly low-reliability claim conflicts with attributable evidence: "
                        f"{edge.rationale or edge.resolver_strategy or 'VeraRAG detector'}"
                        if conflict_type is EvidenceType.SOURCE_RELIABILITY
                        and claim.source_reliability == "low"
                        else edge.rationale or edge.resolver_strategy or "VeraRAG detector"
                    ),
                    strength="strong" if edge.confidence >= 0.75 else "weak",
                    metadata={
                        "detector": "verarag_conflict_graph",
                        "resolver_strategy": edge.resolver_strategy,
                    },
                )
            )
        graph_keys = {(item.evidence_id, item.conflict_type) for item in conflicts}
        for document_conflicts in fallback_by_evidence.values():
            for fallback_conflict in document_conflicts:
                if (
                    fallback_conflict.evidence_id,
                    fallback_conflict.conflict_type,
                ) in graph_keys:
                    continue
                conflicts.append(
                    TypedConflict(
                        claim_id=fallback_conflict.claim_id,
                        evidence_id=fallback_conflict.evidence_id,
                        conflict_type=fallback_conflict.conflict_type,
                        confidence=fallback_conflict.confidence,
                        rationale=fallback_conflict.rationale,
                        strength=fallback_conflict.strength,
                        suggested_revision=fallback_conflict.suggested_revision,
                        metadata={
                            **fallback_conflict.metadata,
                            "detector": "far_heuristic_fallback",
                        },
                    )
                )
        return tuple(conflicts)
