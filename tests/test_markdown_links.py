from __future__ import annotations

from scripts.check_markdown_links import find_broken_links


def test_markdown_link_checker_accepts_existing_and_external_targets(tmp_path) -> None:
    target = tmp_path / "target.md"
    target.write_text("ok\n", encoding="utf-8")
    source = tmp_path / "source.md"
    source.write_text(
        "[local](target.md#section) [web](https://example.com/x)\n",
        encoding="utf-8",
    )
    assert find_broken_links([source], root=tmp_path) == []


def test_markdown_link_checker_reports_missing_target(tmp_path) -> None:
    source = tmp_path / "source.md"
    source.write_text("[missing](nope.md)\n", encoding="utf-8")
    assert find_broken_links([source], root=tmp_path) == [
        "source.md:1: missing nope.md"
    ]
