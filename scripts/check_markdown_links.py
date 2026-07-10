"""Fail when a tracked Markdown file references a missing local path."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SCHEMES = {"http", "https", "mailto", "data"}
FROZEN_PATH_REDIRECTS = {
    (
        "docs/PLAN_LONGTERM_OPTIMIZATION.md",
        "../experiments/configs",
    ): "far/experiments/configs",
}


def _target(raw: str) -> str | None:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        value = value[1 : value.index(">")]
    elif " " in value:
        value = value.split(" ", 1)[0]
    value = unquote(value)
    parsed = urlsplit(value)
    if parsed.scheme.lower() in SCHEMES or not parsed.path:
        return None
    if any(token in parsed.path for token in ("*", "${", "<name>", "<family>")):
        return None
    return parsed.path


def find_broken_links(paths: list[Path], *, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for markdown in paths:
        text = markdown.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in LINK.finditer(line):
                target = _target(match.group(1))
                if target is None:
                    continue
                candidate = (
                    root / target.lstrip("/")
                    if target.startswith("/")
                    else markdown.parent / target
                ).resolve()
                source = markdown.resolve().relative_to(root.resolve()).as_posix()
                redirect = FROZEN_PATH_REDIRECTS.get((source, target))
                if not candidate.exists() and redirect is not None:
                    candidate = (root / redirect).resolve()
                if not candidate.exists():
                    errors.append(f"{markdown.relative_to(root)}:{line_number}: missing {target}")
    return errors


def tracked_markdown() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in completed.stdout.splitlines() if line]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    errors = find_broken_links(tracked_markdown())
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print(f"validated local links in {len(tracked_markdown())} tracked Markdown files")


if __name__ == "__main__":
    main()
