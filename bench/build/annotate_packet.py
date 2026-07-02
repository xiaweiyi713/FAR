"""Build or compile blind FalsiRAG double-annotation packets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bench.annotations import (
    annotation_packet_status,
    build_annotation_packet,
    build_reviewer_handoff,
    compile_annotations,
    install_adjudication_file,
    install_review_file,
    validate_annotation_evidence,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--data-dir", type=Path, required=True)
    build_parser.add_argument("--output-dir", type=Path, required=True)
    build_parser.add_argument("--annotator", action="append", required=True)
    build_parser.add_argument("--overwrite", action="store_true")
    reviewer_handoff_parser = subparsers.add_parser("reviewer-handoff")
    reviewer_handoff_parser.add_argument("--packet-dir", type=Path, required=True)
    reviewer_handoff_parser.add_argument("--output-dir", type=Path, required=True)
    reviewer_handoff_parser.add_argument("--reviewer-id", required=True)
    reviewer_handoff_parser.add_argument("--overwrite", action="store_true")
    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--data-dir", type=Path, required=True)
    compile_parser.add_argument("--packet-dir", type=Path, required=True)
    compile_parser.add_argument("--output-dir", type=Path, required=True)
    install_parser = subparsers.add_parser("install-review")
    install_parser.add_argument("--packet-dir", type=Path, required=True)
    install_parser.add_argument("--review-file", type=Path, required=True)
    install_parser.add_argument("--reviewer-id", required=True)
    install_adjudication_parser = subparsers.add_parser("install-adjudication")
    install_adjudication_parser.add_argument("--packet-dir", type=Path, required=True)
    install_adjudication_parser.add_argument("--adjudication-file", type=Path, required=True)
    install_adjudication_parser.add_argument("--adjudicator-id")
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--packet-dir", type=Path, required=True)
    status_parser.add_argument("--data-dir", type=Path)
    validate_parser = subparsers.add_parser("validate-evidence")
    validate_parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        result = build_annotation_packet(
            args.data_dir,
            args.output_dir,
            args.annotator,
            overwrite=args.overwrite,
        )
    elif args.command == "reviewer-handoff":
        result = build_reviewer_handoff(
            args.packet_dir,
            args.output_dir,
            reviewer_id=args.reviewer_id,
            overwrite=args.overwrite,
        )
    elif args.command == "compile":
        result = compile_annotations(args.data_dir, args.packet_dir, args.output_dir)
    elif args.command == "install-review":
        result = install_review_file(
            args.packet_dir,
            args.review_file,
            reviewer_id=args.reviewer_id,
        )
    elif args.command == "install-adjudication":
        result = install_adjudication_file(
            args.packet_dir,
            args.adjudication_file,
            adjudicator_id=args.adjudicator_id,
        )
    elif args.command == "status":
        result = annotation_packet_status(args.packet_dir, data_dir=args.data_dir)
    else:
        result = validate_annotation_evidence(args.data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
