from __future__ import annotations

import shutil
from pathlib import Path

from far.experiments.diagnostic_release import verify_solo_release

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "diagnostics/solo_v1"


def test_tracked_solo_diagnostic_release_verifies() -> None:
    audit = verify_solo_release(RELEASE)
    assert audit["valid"] is True
    assert audit["errors"] == []
    assert audit["files"] == 69
    assert audit["methods"] == 11
    assert audit["publication_ready"] is False


def test_solo_diagnostic_release_rejects_tampering(tmp_path: Path) -> None:
    copied = tmp_path / "solo_v1"
    shutil.copytree(RELEASE, copied)
    target = copied / "experiments/artifacts/main_results.csv"
    target.write_text(target.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    audit = verify_solo_release(copied)
    assert audit["valid"] is False
    assert any("fingerprint mismatch" in error for error in audit["errors"])
