from __future__ import annotations

from pathlib import Path

from scripts.check_markdown_links import find_broken_links


def test_markdown_link_checker_accepts_existing_and_external_targets(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("ok\n", encoding="utf-8")
    source = tmp_path / "source.md"
    source.write_text(
        "[local](target.md#section) [web](https://example.com/x)\n",
        encoding="utf-8",
    )
    assert find_broken_links([source], root=tmp_path) == []


def test_markdown_link_checker_reports_missing_target(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("[missing](nope.md)\n", encoding="utf-8")
    assert find_broken_links([source], root=tmp_path) == ["source.md:1: missing nope.md"]


def test_markdown_link_checker_redirects_one_frozen_pre_p10_path(tmp_path: Path) -> None:
    source = tmp_path / "docs/PLAN_LONGTERM_OPTIMIZATION.md"
    source.parent.mkdir()
    source.write_text("[configs](../experiments/configs)\n", encoding="utf-8")
    (tmp_path / "far/experiments/configs").mkdir(parents=True)

    assert find_broken_links([source], root=tmp_path) == []
