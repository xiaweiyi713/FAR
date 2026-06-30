"""Scan FAR repository text files for high-confidence leaked secrets.

Adapted from VeraRAG's MIT-licensed scanner. Findings are always redacted.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "outputs",
}
TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".env",
    ".ini",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".sh",
    ".tex",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
MAX_FILE_BYTES = 5_000_000
ALLOWLIST_MARKERS = (
    "${",
    "<key>",
    "<paste key here>",
    "dummy",
    "example",
    "placeholder",
    "sk-test",
    "sk-xxx",
    "test-key",
    "your-api-key",
)


@dataclass(frozen=True)
class SecretFinding:
    path: str
    line_number: int
    rule: str
    redacted: str


SECRET_PATTERNS = (
    (
        "openai_or_deepseek_style_key",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9][A-Za-z0-9_-]{20,}\b"),
    ),
    ("anthropic_style_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
    ("github_fine_grained_token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "private_key_header",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ),
)
ASSIGNMENT_PATTERN = re.compile(
    r"""(?ix)
    \b[A-Za-z0-9_]*(?:api[_-]?key|secret|token|access[_-]?key)\b
    \s*[:=]\s*["']
    (?P<value>[A-Za-z0-9][A-Za-z0-9_./+=:-]{19,})
    ["']
    """
)
ENV_ASSIGNMENT_PATTERN = re.compile(
    r"""(?ix)
    ^\s*(?:export\s+)?
    [A-Za-z_][A-Za-z0-9_]*(?:api[_-]?key|secret|token|access[_-]?key)[A-Za-z0-9_]*
    \s*=\s*["']?
    (?P<value>[A-Za-z0-9][A-Za-z0-9_./+=:-]{19,})
    ["']?(?:\s*(?:\#.*)?)$
    """
)


def scan_paths(
    paths: Iterable[str | Path],
    *,
    include_ignored: bool = False,
) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for path in _candidate_files(paths, include_ignored=include_ignored):
        findings.extend(_scan_file(path))
    return findings


def _candidate_files(paths: Iterable[str | Path], *, include_ignored: bool) -> list[Path]:
    candidates: list[Path] = []
    for value in paths:
        path = Path(value)
        if path.is_file():
            candidates.append(path)
        elif path.is_dir():
            candidates.extend(_directory_files(path, include_ignored=include_ignored))
        else:
            raise FileNotFoundError(path)
    return sorted({path.resolve() for path in candidates})


def _directory_files(root: Path, *, include_ignored: bool) -> list[Path]:
    if not include_ignored and (git_files := _git_files(root)) is not None:
        return [root / path for path in git_files if _scannable(root / path)]
    return [path for path in root.rglob("*") if _scannable(path)]


def _git_files(root: Path) -> list[Path] | None:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return [Path(line) for line in result.stdout.splitlines() if line.strip()]


def _scannable(path: Path) -> bool:
    if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
        return False
    name = path.name.lower()
    if not (name == ".env" or name.startswith(".env.") or path.suffix.lower() in TEXT_SUFFIXES):
        return False
    try:
        return path.stat().st_size <= MAX_FILE_BYTES
    except OSError:
        return False


def _scan_file(path: Path) -> list[SecretFinding]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    findings = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        findings.extend(_scan_line(path, line_number, line))
    return findings


def _scan_line(path: Path, line_number: int, line: str) -> list[SecretFinding]:
    findings = []
    for rule, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(line):
            token = match.group(0)
            if not _allowlisted(token, line):
                findings.append(_finding(path, line_number, rule, token))
    assignment = ASSIGNMENT_PATTERN.search(line)
    if assignment and not _allowlisted(assignment.group("value"), line):
        findings.append(
            _finding(path, line_number, "generic_secret_assignment", assignment.group("value"))
        )
    env_assignment = None if assignment else ENV_ASSIGNMENT_PATTERN.search(line)
    if env_assignment and not _allowlisted(env_assignment.group("value"), line):
        findings.append(
            _finding(path, line_number, "env_secret_assignment", env_assignment.group("value"))
        )
    return findings


def _finding(path: Path, line_number: int, rule: str, token: str) -> SecretFinding:
    redacted = "***" if len(token) <= 10 else f"{token[:6]}...{token[-4:]}"
    return SecretFinding(str(path), line_number, rule, redacted)


def _allowlisted(token: str, line: str) -> bool:
    normalized_token = token.lower()
    normalized_line = line.lower()
    return any(
        marker in normalized_token or marker in normalized_line for marker in ALLOWLIST_MARKERS
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["."])
    parser.add_argument("--include-ignored", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    findings = scan_paths(args.paths, include_ignored=args.include_ignored)
    if args.json:
        print(json.dumps([asdict(item) for item in findings], indent=2))
    elif findings:
        for item in findings:
            print(f"{item.path}:{item.line_number}: {item.rule}: {item.redacted}")
    else:
        print("No high-confidence secrets detected.")
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
