"""Transparent closed-corpus CounterRefine-style reproduction."""

from __future__ import annotations

import json
import re
from typing import Any

from far.adapters.retrieval import Retriever
from far.models import EvidenceDocument
from far.protocols import TextGenerator

from .common import BaselinePrediction, generate_answer, retrieve_unique

_MONTHS = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "was",
    "were",
    "with",
}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text.lower())
        if token not in _STOPWORDS
    }


def _normalized(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text.lower()))


class CounterRefineStyleBaseline:
    """Draft, answer-conditioned retrieve, then guarded KEEP/REVISE.

    This is a closed-corpus adaptation of the published control flow, not the
    authors' web-retrieval implementation. It intentionally has no FAR typed
    conflict ontology, typed query tactics, or typed revision policy.
    """

    name = "counterrefine_style_reproduction"

    def __init__(
        self, retriever: Retriever, generator: TextGenerator | None = None, top_k: int = 5
    ):
        self.retriever = retriever
        self.generator = generator
        self.top_k = top_k

    @staticmethod
    def _question_type(question: str) -> str:
        lowered = question.lower().strip()
        if re.match(r"^(is|are|was|were|do|does|did|has|have|had|can|could|will|would)\b", lowered):
            return "yes_no"
        if re.search(r"\b(what year|which year|in what year)\b", lowered):
            return "year"
        if re.match(r"^when\b", lowered) or re.search(
            r"\b(month|date|timeframe|what day|which day)\b", lowered
        ):
            return "temporal"
        if re.search(r"\b(how many|how much|population|number|percentage|percent)\b", lowered):
            return "numeric"
        if re.match(r"^where\b", lowered) or re.search(
            r"\b(city|county|town|village|municipality|neighborhood|country)\b", lowered
        ):
            return "location"
        if re.match(r"^(who|whom|whose)\b", lowered):
            return "person"
        return "other"

    @classmethod
    def queries(cls, question: str, draft: str) -> list[str]:
        queries = [question, f'{question} "{draft}"']
        if cls._question_type(question) != "other":
            queries.append(draft)
        return list(dict.fromkeys(query for query in queries if query.strip()))

    @staticmethod
    def _parse_payload(response: str) -> dict[str, Any] | None:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(cleaned[start : end + 1])
        except (json.JSONDecodeError, TypeError):
            return None
        return payload if isinstance(payload, dict) else None

    @classmethod
    def _validate_revision(
        cls,
        question: str,
        draft: str,
        answer: str,
        evidence_id: str,
        evidence_by_id: dict[str, EvidenceDocument],
    ) -> tuple[bool, str]:
        if not answer.strip() or _normalized(answer) == _normalized(draft):
            return False, "empty_or_unchanged"
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            return False, "missing_evidence_id"
        question_type = cls._question_type(question)
        lowered_answer = answer.lower()
        if question_type == "yes_no" and _normalized(answer) not in {"yes", "no"}:
            return False, "ill_typed_yes_no"
        if question_type in {"year", "temporal", "numeric"} and not (
            re.search(r"\d", answer) or any(month in lowered_answer for month in _MONTHS)
        ):
            return False, "missing_numeric_or_temporal_marker"
        if question_type in {"person", "location"} and len(answer.split()) > 20:
            return False, "overlong_entity_answer"
        answer_tokens = _tokens(answer)
        evidence_tokens = _tokens(f"{evidence.title} {evidence.text}")
        if question_type in {"year", "temporal", "numeric"}:
            answer_markers = {
                token for token in answer_tokens if any(char.isdigit() for char in token)
            }
            answer_markers.update(month for month in _MONTHS if month in lowered_answer)
            if not (answer_markers & evidence_tokens):
                return False, "unanchored_numeric_or_temporal_marker"
        if not answer_tokens or not (answer_tokens & evidence_tokens):
            return False, "weak_lexical_grounding"
        return True, "accepted"

    def _refine(
        self,
        question: str,
        draft: str,
        evidence: tuple[EvidenceDocument, ...],
    ) -> tuple[str, str, str | None]:
        if self.generator is None:
            return draft, "KEEP", "no_generator"
        context = "\n".join(f"[{item.evidence_id}] {item.title}: {item.text}" for item in evidence)
        response = self.generator.complete(
            (
                f"Question: {question}\nDraft answer: {draft}\nEvidence:\n{context}\n\n"
                "Decide conservatively whether the draft should be kept or revised. "
                "Revise only when one supplied passage strongly supports a different answer. "
                "Return JSON only with exactly these fields: "
                '{"decision":"KEEP or REVISE","answer":"final answer",'
                '"evidence_id":"one supplied evidence ID or NONE"}.'
            ),
            system_prompt=(
                "You are a conservative answer-repair gate. Use only supplied evidence and do "
                "not expose chain-of-thought."
            ),
            temperature=0.0,
            max_tokens=400,
        )
        payload = self._parse_payload(response)
        if payload is None:
            return draft, "KEEP", "malformed_refinement"
        decision = str(payload.get("decision", "")).strip().upper()
        if decision == "KEEP":
            return draft, "KEEP", "model_keep"
        if decision != "REVISE":
            return draft, "KEEP", "invalid_decision"
        answer = str(payload.get("answer", "")).strip()
        evidence_id = str(payload.get("evidence_id", "")).strip()
        valid, reason = self._validate_revision(
            question,
            draft,
            answer,
            evidence_id,
            {item.evidence_id: item for item in evidence},
        )
        return (answer, "REVISE", reason) if valid else (draft, "KEEP", reason)

    def run(self, sample_id: str, question: str, initial_answer: str) -> BaselinePrediction:
        initial_evidence = retrieve_unique(self.retriever, [question], top_k=self.top_k)
        draft = generate_answer(
            self.generator,
            question,
            initial_answer,
            initial_evidence,
            instruction="Produce a concise retrieval-grounded draft answer.",
        )
        queries = self.queries(question, draft)
        evidence = retrieve_unique(self.retriever, queries, top_k=self.top_k)
        answer, decision, validation = self._refine(question, draft, evidence)
        return BaselinePrediction(
            sample_id=sample_id,
            method=self.name,
            answer=answer,
            evidence_ids=tuple(item.evidence_id for item in evidence),
            trace=(
                {"stage": "retrieval_grounded_draft", "query": question},
                {"stage": "answer_conditioned_retrieve", "queries": queries},
                {
                    "stage": "guarded_refinement",
                    "decision": decision,
                    "validation": validation,
                },
            ),
            metadata={
                "official_implementation": False,
                "scope": (
                    "closed-corpus CounterRefine-style reproduction; supplied initial answer; "
                    "no web search"
                ),
                "model_calls": 0 if self.generator is None else 2,
                "retrieval_queries": 1 + len(queries),
            },
        )
