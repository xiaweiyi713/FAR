from __future__ import annotations

from types import SimpleNamespace

import pytest

from far.adapters import InMemoryRetriever, NLIOnlyConflictDetector
from far.claims import ClaimGraph, ClaimNode, ClaimType
from far.evidence_types import EvidenceType, TypedConflict
from far.experiments.ablations import (
    ABLATION_NAMES,
    AggressiveGenericRevisionEngine,
    FlatClaimDecomposer,
    LLMAggressiveGenericRevisionEngine,
    build_ablation,
)
from far.experiments.run_suite import DEFAULT_ABLATIONS
from far.models import EvidenceDocument
from far.revision import RevisionAction


class _DependentDecomposer:
    def decompose(self, answer: str) -> ClaimGraph:
        del answer
        return ClaimGraph(
            (
                ClaimNode("C1", "The premise holds.", ClaimType.FACTUAL),
                ClaimNode(
                    "C2",
                    "Therefore the conclusion holds.",
                    ClaimType.INFERENTIAL,
                    depends_on=("C1",),
                ),
            )
        )


class _FakeNLIModel:
    def __init__(self, scores: object) -> None:
        self.scores = scores
        self.pairs: list[tuple[str, str]] = []
        self.model = SimpleNamespace(
            config=SimpleNamespace(id2label={0: "contradiction", 1: "entailment", 2: "neutral"})
        )

    def predict(
        self,
        pairs: list[tuple[str, str]],
        *,
        show_progress_bar: bool,
    ) -> object:
        assert show_progress_bar is False
        self.pairs = pairs
        return self.scores


class _RevisionGenerator:
    def __init__(self) -> None:
        self.prompt = ""

    def complete(self, prompt: str, **kwargs: object) -> str:
        del kwargs
        self.prompt = prompt
        return "Revenue was 18 million."


def _nli_config() -> dict[str, object]:
    return {
        "conflict_graph": {
            "enable_nli": True,
            "require_nli": True,
            "nli_threshold": 0.7,
            "nli_model": "example/pinned-nli",
            "nli_revision": "a" * 40,
        }
    }


def test_aggressive_generic_revision_is_type_blind_but_not_always_conservative() -> None:
    claim = ClaimNode("C1", "Revenue was 20 million.", ClaimType.NUMERICAL)
    evidence = (EvidenceDocument("E1", "Revenue was 18 million."),)
    strong = TypedConflict(
        claim_id="C1",
        evidence_id="E1",
        conflict_type=EvidenceType.NUMERICAL,
        confidence=0.9,
        rationale="Values differ.",
        strength="strong",
        suggested_revision="Revenue was 18 million.",
    )

    trace = AggressiveGenericRevisionEngine().revise(claim, (strong,), evidence)

    assert trace.action is RevisionAction.RETRACT
    assert trace.after.startswith("The available counter-evidence refutes this claim:")
    assert trace.after != strong.suggested_revision
    assert trace.conflict_types == ()
    assert trace.evidence_ids == ("E1",)

    weak = TypedConflict(
        claim_id="C1",
        evidence_id="E1",
        conflict_type=EvidenceType.CAUSAL,
        confidence=0.72,
        rationale="Causality is unsupported.",
        strength="weak",
    )
    weak_trace = AggressiveGenericRevisionEngine().revise(claim, (weak,), evidence)
    assert weak_trace.action is RevisionAction.QUALIFY_UNCERTAINTY
    assert weak_trace.conflict_types == ()


def test_aggressive_generic_revision_uses_same_generator_without_type_labels() -> None:
    generator = _RevisionGenerator()
    pipeline = build_ablation(
        "minus_typed_revision_aggressive",
        InMemoryRetriever([]),
        text_generator=generator,
    )
    assert isinstance(pipeline.revision_engine, LLMAggressiveGenericRevisionEngine)
    trace = pipeline.revision_engine.revise(
        ClaimNode("C1", "Revenue was 20 million.", ClaimType.NUMERICAL),
        (
            TypedConflict(
                claim_id="C1",
                evidence_id="E1",
                conflict_type=EvidenceType.NUMERICAL,
                confidence=0.9,
                rationale="Values differ.",
                strength="strong",
            ),
        ),
        (EvidenceDocument("E1", "Revenue was 18 million."),),
    )
    assert trace.after == "Revenue was 18 million."
    assert trace.conflict_types == ()
    assert "numerical" not in generator.prompt
    assert "No conflict-type label is available" in generator.prompt


def test_flat_claim_decomposer_only_removes_dependency_edges() -> None:
    original = _DependentDecomposer().decompose("ignored")
    flattened = FlatClaimDecomposer(_DependentDecomposer()).decompose("ignored")

    assert [claim.text for claim in flattened.claims] == [claim.text for claim in original.claims]
    assert [claim.claim_type for claim in flattened.claims] == [
        claim.claim_type for claim in original.claims
    ]
    assert all(claim.depends_on == () for claim in flattened.claims)
    assert flattened.to_dict()["edges"] == []

    pipeline = build_ablation("flat_claims", InMemoryRetriever([]))
    assert isinstance(pipeline.decomposer, FlatClaimDecomposer)


def test_nli_only_detector_uses_only_cross_encoder_contradiction_scores() -> None:
    model = _FakeNLIModel([[5.0, 0.0, 0.0], [0.0, 5.0, 0.0]])
    detector = NLIOnlyConflictDetector(_nli_config(), model=model)
    claim = ClaimNode("C1", "Revenue was 20 million.", ClaimType.NUMERICAL)
    evidence = (
        EvidenceDocument("E1", "The audited revenue was 18 million."),
        EvidenceDocument("E2", "Revenue was 20 million."),
    )

    conflicts = detector.detect_many(claim, evidence)

    assert model.pairs == [
        ("The audited revenue was 18 million.", claim.text),
        ("Revenue was 20 million.", claim.text),
    ]
    assert len(conflicts) == 1
    assert conflicts[0].evidence_id == "E1"
    assert conflicts[0].conflict_type is EvidenceType.COUNTER_EVIDENCE
    assert conflicts[0].metadata == {
        "detector": "nli_only_cross_encoder",
        "model": "example/pinned-nli",
        "model_revision": "a" * 40,
        "threshold": 0.7,
        "input_order": "evidence_premise_claim_hypothesis",
        "contradiction_label_index": 0,
    }


def test_nli_only_ablation_fails_closed_for_wrong_detector_or_output_shape() -> None:
    with pytest.raises(ValueError, match="explicit NLIOnlyConflictDetector"):
        build_ablation("minus_typed_detection_nli", InMemoryRetriever([]))

    detector = NLIOnlyConflictDetector(_nli_config(), model=_FakeNLIModel([[1.0, 2.0]]))
    pipeline = build_ablation(
        "minus_typed_detection_nli",
        InMemoryRetriever([]),
        conflict_detector=detector,
    )
    assert pipeline.conflict_detector is detector
    with pytest.raises(RuntimeError, match="exactly three logits"):
        detector.detect(
            ClaimNode("C1", "A claim.", ClaimType.FACTUAL),
            EvidenceDocument("E1", "Evidence."),
        )

    unlabeled = _FakeNLIModel([[1.0, 0.0, 0.0]])
    unlabeled.model.config.id2label = {0: "LABEL_0", 1: "LABEL_1", 2: "LABEL_2"}
    with pytest.raises(RuntimeError, match="does not expose semantic"):
        NLIOnlyConflictDetector(_nli_config(), model=unlabeled)

    nonfinite = NLIOnlyConflictDetector(
        _nli_config(), model=_FakeNLIModel([[float("nan"), 0.0, 0.0]])
    )
    with pytest.raises(RuntimeError, match="non-finite logits"):
        nonfinite.detect(
            ClaimNode("C1", "A claim.", ClaimType.FACTUAL),
            EvidenceDocument("E1", "Evidence."),
        )


def test_nli_only_detector_requires_explicit_enable_and_require() -> None:
    model = _FakeNLIModel([[1.0, 0.0, 0.0]])
    with pytest.raises(ValueError, match="enable_nli=true"):
        NLIOnlyConflictDetector({"conflict_graph": {}}, model=model)
    with pytest.raises(ValueError, match="require_nli=true"):
        NLIOnlyConflictDetector(
            {"conflict_graph": {"enable_nli": True}},
            model=model,
        )


def test_enhancement_ablations_are_explicit_and_not_added_to_default_suite() -> None:
    enhancements = {
        "minus_typed_revision_aggressive",
        "minus_typed_detection_nli",
        "flat_claims",
    }
    assert enhancements <= set(ABLATION_NAMES)
    assert enhancements.isdisjoint(DEFAULT_ABLATIONS)
