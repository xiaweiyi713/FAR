"""Audit repository-maintenance invariants for the long-term FAR roadmap.

This audit is intentionally engineering-only: it checks tracked-file size,
diagnostics growth, and ignored-output directory hygiene.  It does not read
benchmark test inputs, score predictions, call models, or change any research
claim.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bench.build.common import sha256_file, write_json

SCHEMA_VERSION = "far-repository-maintenance-audit-v1"
DEFAULT_DIAGNOSTICS_THRESHOLD_MIB = 200.0
DEFAULT_SINGLE_FILE_THRESHOLD_MIB = 50.0


@dataclass(frozen=True)
class TrackedFile:
    path: str
    bytes: int


def _run_git(root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _tracked_files(root: Path) -> list[TrackedFile]:
    raw = _run_git(root, ["ls-files", "-z"])
    files: list[TrackedFile] = []
    for item in raw.split("\0"):
        if not item:
            continue
        path = root / item
        if path.is_file():
            files.append(TrackedFile(item, path.stat().st_size))
    return files


def _bytes_to_mib(value: int) -> float:
    return round(value / (1024 * 1024), 3)


def _gitignore_has(root: Path, pattern: str) -> bool:
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return False
    return pattern in {
        line.strip()
        for line in gitignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def _path_is_ignored(root: Path, path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=root,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.returncode == 0


def audit(
    root: Path,
    *,
    diagnostics_threshold_mib: float = DEFAULT_DIAGNOSTICS_THRESHOLD_MIB,
    single_file_threshold_mib: float = DEFAULT_SINGLE_FILE_THRESHOLD_MIB,
) -> dict[str, Any]:
    root = root.resolve()
    tracked = _tracked_files(root)
    total_bytes = sum(item.bytes for item in tracked)
    diagnostics = [item for item in tracked if item.path.startswith("diagnostics/")]
    diagnostics_bytes = sum(item.bytes for item in diagnostics)
    largest = max(tracked, key=lambda item: item.bytes) if tracked else TrackedFile("", 0)
    output_tracked = sorted(
        item.path for item in tracked if item.path == "output" or item.path.startswith("output/")
    )
    outputs_tracked = sorted(item.path for item in tracked if item.path.startswith("outputs/"))
    outputs_has_only_gitkeep = outputs_tracked == ["outputs/.gitkeep"]
    output_disabled = _gitignore_has(root, "/output/")
    outputs_ignored = (
        _gitignore_has(root, "outputs/*")
        and _gitignore_has(root, "!outputs/.gitkeep")
        and _path_is_ignored(root, "outputs/transient-check.tmp")
    )
    diagnostics_under_threshold = _bytes_to_mib(diagnostics_bytes) <= diagnostics_threshold_mib
    largest_under_threshold = _bytes_to_mib(largest.bytes) <= single_file_threshold_mib
    valid = all(
        [
            diagnostics_under_threshold,
            largest_under_threshold,
            output_disabled,
            not output_tracked,
            outputs_ignored,
            outputs_has_only_gitkeep,
        ]
    )
    errors: list[str] = []
    if not diagnostics_under_threshold:
        errors.append("diagnostics tracked size exceeds migration threshold")
    if not largest_under_threshold:
        errors.append("largest tracked file exceeds single-file threshold")
    if not output_disabled:
        errors.append("legacy output/ directory is not disabled in .gitignore")
    if output_tracked:
        errors.append("legacy output/ files are still tracked")
    if not outputs_ignored:
        errors.append("outputs/ transient files are not ignored")
    if not outputs_has_only_gitkeep:
        errors.append("outputs/ should track only outputs/.gitkeep")
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": valid,
        "errors": errors,
        "claim_scope": "engineering hygiene only; does not alter F1-F10 or experimental gates",
        "thresholds": {
            "diagnostics_mib": diagnostics_threshold_mib,
            "single_file_mib": single_file_threshold_mib,
        },
        "tracked_files": {
            "count": len(tracked),
            "bytes": total_bytes,
            "mib": _bytes_to_mib(total_bytes),
        },
        "diagnostics": {
            "tracked_files": len(diagnostics),
            "bytes": diagnostics_bytes,
            "mib": _bytes_to_mib(diagnostics_bytes),
            "under_threshold": diagnostics_under_threshold,
        },
        "largest_tracked_file": {
            "path": largest.path,
            "bytes": largest.bytes,
            "mib": _bytes_to_mib(largest.bytes),
            "under_threshold": largest_under_threshold,
            "sha256": sha256_file(root / largest.path) if largest.path else None,
        },
        "ignored_outputs": {
            "legacy_output_disabled": output_disabled,
            "legacy_output_tracked_files": output_tracked,
            "outputs_transients_ignored": outputs_ignored,
            "outputs_tracked_files": outputs_tracked,
            "outputs_tracks_only_gitkeep": outputs_has_only_gitkeep,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    diagnostics = report["diagnostics"]
    tracked = report["tracked_files"]
    largest = report["largest_tracked_file"]
    ignored = report["ignored_outputs"]
    errors = report["errors"]
    error_block = "\n".join(f"- `{error}`" for error in errors) if errors else "- 无"
    outputs_files = ", ".join(f"`{item}`" for item in ignored["outputs_tracked_files"]) or "无"
    diagnostics_under_threshold = str(diagnostics["under_threshold"]).lower()
    largest_under_threshold = str(largest["under_threshold"]).lower()
    output_disabled = str(ignored["legacy_output_disabled"]).lower()
    outputs_ignored = str(ignored["outputs_transients_ignored"]).lower()
    return f"""# FAR 仓库维护基线 (可重算)

- 审计 schema: `{report["schema_version"]}`; valid=`{str(report["valid"]).lower()}`.
- `diagnostics/` 跟踪体积: 约 {diagnostics["mib"]} MiB
  (阈值 {report["thresholds"]["diagnostics_mib"]} MiB;
  under_threshold=`{diagnostics_under_threshold}`).
- 全仓跟踪文件: {tracked["count"]} 个, 约 {tracked["mib"]} MiB.
- 最大跟踪文件: `{largest["path"]}`, 约 {largest["mib"]} MiB
  (阈值 {report["thresholds"]["single_file_mib"]} MiB;
  under_threshold=`{largest_under_threshold}`).
- `output/` 停用: `{output_disabled}`;
  `output/` 跟踪文件数: {len(ignored["legacy_output_tracked_files"])}.
- `outputs/` 临时文件忽略: `{outputs_ignored}`;
  `outputs/` 当前跟踪文件: {outputs_files}.

## 错误

{error_block}

此报告只记录 WS6 工程状态, 不改变 F1-F10、实验判定、标签级别、Phase B 状态或 held-out/test 状态。
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--check", action="store_true", help="exit nonzero if audit is invalid")
    args = parser.parse_args()
    report = audit(args.root)
    if args.json_output:
        write_json(args.json_output, report)
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.check and not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
