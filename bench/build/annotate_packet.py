"""Build or compile blind FalsiRAG double-annotation packets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bench.annotations import build_annotation_packet, compile_annotations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--data-dir", type=Path, required=True)
    build_parser.add_argument("--output-dir", type=Path, required=True)
    build_parser.add_argument("--annotator", action="append", required=True)
    build_parser.add_argument("--overwrite", action="store_true")
    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--data-dir", type=Path, required=True)
    compile_parser.add_argument("--packet-dir", type=Path, required=True)
    compile_parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        result = build_annotation_packet(
            args.data_dir,
            args.output_dir,
            args.annotator,
            overwrite=args.overwrite,
        )
    else:
        result = compile_annotations(args.data_dir, args.packet_dir, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
