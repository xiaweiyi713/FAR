from __future__ import annotations

import shutil
from pathlib import Path

from far.experiments.evaluate_fever_binary import validate_source, verify_evaluation

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "bench/external/fever_pair_candidates_v1"
EVALUATION = ROOT / "diagnostics/fever_binary_v1"


def test_fever_binary_source_inherits_only_binary_reference() -> None:
    audit = validate_source(SOURCE)
    assert audit["valid"] is True
    assert audit["labels"] == {"REFUTES": 40, "SUPPORTS": 60}
    assert audit["typed_bucket_publication_gold"] is False


def test_tracked_fever_binary_evaluation_verifies() -> None:
    audit = verify_evaluation(SOURCE, EVALUATION)
    assert audit["valid"] is True
    assert audit["errors"] == []
    assert audit["publication_ready_main_result"] is False


def test_fever_binary_evaluation_rejects_tampering(tmp_path: Path) -> None:
    copied = tmp_path / "fever_binary_v1"
    shutil.copytree(EVALUATION, copied)
    predictions = copied / "predictions_vera_nli.jsonl"
    predictions.write_text(
        predictions.read_text(encoding="utf-8") + '{"sample_id":"tampered"}\n',
        encoding="utf-8",
    )
    audit = verify_evaluation(SOURCE, copied)
    assert audit["valid"] is False
    assert any("fingerprint mismatch" in error for error in audit["errors"])
