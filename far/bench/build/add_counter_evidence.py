"""Audit or attach explicitly supplied counter-evidence to candidate samples."""

from __future__ import annotations

import argparse
from pathlib import Path

from far.bench.build.common import read_jsonl, write_jsonl


def attach(benchmark_path: Path, additions_path: Path, output_path: Path) -> None:
    samples = read_jsonl(benchmark_path)
    additions = {row["id"]: row["counter_evidence"] for row in read_jsonl(additions_path)}
    unknown = set(additions) - {row["id"] for row in samples}
    if unknown:
        raise ValueError(f"counter-evidence additions reference unknown samples: {sorted(unknown)}")
    for sample in samples:
        if sample["id"] in additions:
            sample["counter_evidence"] = additions[sample["id"]]
            sample["annotation_status"] = "machine_seeded"
    write_jsonl(output_path, samples)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--additions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    attach(args.benchmark, args.additions, args.output)


if __name__ == "__main__":
    main()
