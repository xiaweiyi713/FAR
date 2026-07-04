"""Create a machine-readable FAR project-status snapshot.

This is a lightweight audit, not a replacement for the final release gate.  It
separates local implementation/diagnostic evidence from strict external
submission evidence so the project can keep moving without blurring those
claims.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from bench.build.common import sha256_file, write_json
from bench.build.validate_bench import validate as validate_benchmark
from experiments.diagnostic_release import verify_solo_release
from experiments.evaluate_fever_binary import verify_evaluation as verify_fever_binary
from experiments.jury_paper_readiness import audit as audit_jury_paper_readiness
from experiments.solo_paper_readiness import audit as audit_solo_paper_readiness
from experiments.submission_readiness import audit as audit_submission_readiness

SNAPSHOT_SCHEMA_VERSION = "far-project-status-snapshot-v3"
SNAPSHOT_AUDIT_SCHEMA_VERSION = "far-project-status-snapshot-audit-v1"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _priority_table(root: Path, path: Path) -> dict[str, Any]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    dispositions = sorted({row.get("disposition", "") for row in rows})
    scores = [int(row["priority_score"]) for row in rows]
    ranks = [int(row["rank"]) for row in rows]
    valid = (
        len(rows) == 122
        and dispositions == ["machine_disputed"]
        and ranks == list(range(1, len(rows) + 1))
        and scores == sorted(scores, reverse=True)
        and "revised_answer" not in path.read_text(encoding="utf-8")
    )
    return {
        "valid": valid,
        "path": path.relative_to(root).as_posix(),
        "rows": len(rows),
        "dispositions": dispositions,
        "sha256": sha256_file(path),
        "publication_gold": False,
        "can_satisfy_human_annotation_gate": False,
    }


def _reader_reports(root: Path) -> dict[str, Any]:
    report = root / "reports/single_author_diagnostic_report.md"
    priority = root / "reports/solo_human_review_priority.csv"
    readme = root / "reports/README.md"
    solo_paper_json = root / "reports/solo_paper_readiness.json"
    solo_paper_markdown = root / "reports/solo_paper_readiness.md"
    required = [report, priority, readme, solo_paper_json, solo_paper_markdown]
    missing = [path.relative_to(root).as_posix() for path in required if not path.is_file()]
    return {
        "valid": not missing,
        "missing": missing,
        "files": {
            path.relative_to(root).as_posix(): sha256_file(path)
            for path in required
            if path.is_file()
        },
    }


def build_status_snapshot(root: Path) -> dict[str, Any]:
    benchmark = validate_benchmark(root / "bench")
    solo_release = verify_solo_release(root / "diagnostics/solo_v1")
    fever_binary = verify_fever_binary(
        root / "bench/external/fever_pair_candidates_v1",
        root / "diagnostics/fever_binary_v1",
    )
    priority = _priority_table(root, root / "reports/solo_human_review_priority.csv")
    reports = _reader_reports(root)
    solo_paper = audit_solo_paper_readiness(root)
    jury_paper = audit_jury_paper_readiness(
        root / "bench/external/ramdocs_v1",
        root / "diagnostics/ramdocs_v1/dev",
        root / "diagnostics/jury_v1/consensus/jury_consensus_report.json",
        root / "bench/labels_jury_v1/manifest.json",
        root / "diagnostics/jury_v1/model_matrix.json",
        root / "diagnostics/jury_v1/falsirag_test/one_shot_seal.json",
        root / "diagnostics/jury_v1/falsirag_test/matrix_family_manifest.json",
        root / "diagnostics/ramdocs_v1/test/one_shot_seal.json",
        root / "diagnostics/ramdocs_v1/test/suite_manifest.json",
        root / "paper/main.tex",
    )
    submission = audit_submission_readiness(root, _json(root / "submission/evidence.template.json"))
    strict_external_blockers = sorted(
        set(submission["blockers"])
        - {
            "candidate_benchmark",
            "release_archive",
        }
    )
    single_author_complete = all(
        [
            bool(benchmark.get("valid")),
            bool(solo_release.get("valid")),
            bool(fever_binary.get("valid")),
            bool(priority["valid"]),
            bool(reports["valid"]),
        ]
    )
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "project_profile": "far_proposal_completion_status",
        "single_author_machine_audited_diagnostic": {
            "complete": single_author_complete,
            "allowed_claim": "public single-author machine-audited diagnostic",
            "forbidden_claims": [
                "human gold",
                "human inter-annotator agreement",
                "externally held blind-test result",
                "strict AAAI submission readiness",
            ],
        },
        "single_author_machine_audited_paper": {
            "ready": bool(solo_paper["ready"]),
            "allowed_claim": solo_paper["allowed_claim"],
            "strict_aaai_submission_ready": False,
            "required_limitations": solo_paper["required_limitations"],
        },
        "cross_family_jury_external_validation_paper": {
            "ready": bool(jury_paper["ready"]),
            "human_gate_replaced_for_this_profile": True,
            "strict_independent_human_profile_ready": False,
            "blockers": jury_paper["errors"],
        },
        "strict_aaai_submission": {
            "ready": bool(submission["ready"]),
            "blockers": submission["blockers"],
            "external_blockers": strict_external_blockers,
            "template_evidence_used_for_status_only": True,
        },
        "evidence": {
            "benchmark": {
                "valid": bool(benchmark.get("valid")),
                "candidate_ready": bool(benchmark.get("candidate_ready")),
                "samples": benchmark.get("counts", {}).get("samples"),
                "documents": benchmark.get("counts", {}).get("documents"),
                "counter_evidence_recall": benchmark.get("counter_evidence_retrieval", {}).get(
                    "recall"
                ),
                "publication_ready": False,
                "fingerprints": benchmark.get("fingerprints", {}),
            },
            "solo_release": solo_release,
            "fever_binary": fever_binary,
            "review_priority": priority,
            "reader_reports": reports,
            "solo_paper_readiness": solo_paper,
            "jury_paper_readiness": jury_paper,
        },
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    diagnostic = snapshot["single_author_machine_audited_diagnostic"]
    paper_profile = snapshot["single_author_machine_audited_paper"]
    jury_profile = snapshot["cross_family_jury_external_validation_paper"]
    strict = snapshot["strict_aaai_submission"]
    evidence = snapshot["evidence"]
    diagnostic_status = str(diagnostic["complete"]).lower()
    paper_profile_status = str(paper_profile["ready"]).lower()
    paper_profile_meaning = "Narrow typed-control mechanism claim with mandatory negative ablations"
    strict_status = str(strict["ready"]).lower()
    jury_profile_status = str(jury_profile["ready"]).lower()
    jury_profile_meaning = (
        "Preregistered external upstream-label validation plus cross-family LLM jury"
    )
    strict_meaning = (
        "Requires real external evidence and cannot be satisfied by templates or machine labels"
    )
    benchmark = evidence["benchmark"]
    solo = evidence["solo_release"]
    fever = evidence["fever_binary"]
    priority = evidence["review_priority"]
    reports = evidence["reader_reports"]
    benchmark_status = (
        f"valid=`{str(benchmark['valid']).lower()}`, "
        f"samples={benchmark['samples']}, "
        f"counter-evidence recall={benchmark['counter_evidence_recall']}"
    )
    solo_status = (
        f"valid=`{str(solo['valid']).lower()}`, files={solo['files']}, methods={solo['methods']}"
    )
    fever_status = f"valid=`{str(fever['valid']).lower()}`, publication_ready_main_result=`false`"
    priority_status = (
        f"valid=`{str(priority['valid']).lower()}`, "
        f"rows={priority['rows']}, "
        f"dispositions={', '.join(priority['dispositions'])}"
    )
    reports_status = f"valid=`{str(reports['valid']).lower()}`"
    blockers = "\n".join(f"- `{blocker}`" for blocker in strict["blockers"])
    external_blockers = "\n".join(f"- `{blocker}`" for blocker in strict["external_blockers"])
    return f"""# FAR Project Status Snapshot

This snapshot is generated from tracked repository evidence. It is a status
ledger for the project proposal, not a submission waiver.

## Summary

| Track | Status | Meaning |
|---|---|---|
| Single-author machine-audited diagnostic | `{diagnostic_status}` | {diagnostic["allowed_claim"]} |
| Single-author machine-audited paper | `{paper_profile_status}` | {paper_profile_meaning} |
| Cross-family jury + external validation paper | `{jury_profile_status}` | {jury_profile_meaning} |
| Strict AAAI submission | `{strict_status}` | {strict_meaning} |

## Current evidence

| Evidence item | Status |
|---|---|
| Candidate benchmark | {benchmark_status} |
| Solo diagnostic release | {solo_status} |
| FEVER binary transfer diagnostic | {fever_status} |
| Review-priority table | {priority_status} |
| Reader-facing reports | {reports_status} |

## Strict submission blockers

These blockers come from `submission/evidence.template.json` and are expected
until real external evidence is supplied:

{blockers or "- none"}

External-role blockers:

{external_blockers or "- none"}

## Claim boundary

The completed local track may be described as a public single-author,
machine-audited diagnostic; it must not be described as human gold. The 2+4
track replaces the unavailable human gate only for its explicitly named profile;
it remains LLM jury + author adjudication, not human IAA or externally held
blind-test evidence.
"""


def verify_status_snapshot(
    root: Path,
    json_path: Path,
    markdown_path: Path,
) -> dict[str, Any]:
    """Rebuild and compare both tracked status representations without writing."""
    expected = build_status_snapshot(root)
    errors: list[str] = []

    try:
        tracked_json = _json(json_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"JSON snapshot unreadable: {exc}")
    else:
        if tracked_json != expected:
            errors.append("JSON snapshot is stale; regenerate it with falsirag-project-status")

    expected_markdown = render_markdown(expected)
    try:
        tracked_markdown = markdown_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"Markdown snapshot unreadable: {exc}")
    else:
        if tracked_markdown != expected_markdown:
            errors.append("Markdown snapshot is stale; regenerate it with falsirag-project-status")

    return {
        "schema_version": SNAPSHOT_AUDIT_SCHEMA_VERSION,
        "valid": not errors,
        "diagnostic_complete": bool(
            expected["single_author_machine_audited_diagnostic"]["complete"]
        ),
        "checked": {
            "json": _display_path(root, json_path),
            "markdown": _display_path(root, markdown_path),
        },
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="compare tracked JSON and Markdown snapshots with current evidence without writing",
    )
    args = parser.parse_args()

    root = args.project_root.resolve()
    if args.verify:
        json_path = (args.json_output or root / "reports/project_status_snapshot.json").resolve()
        markdown_path = (
            args.markdown_output or root / "reports/project_status_snapshot.md"
        ).resolve()
        audit = verify_status_snapshot(root, json_path, markdown_path)
        print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
        if not audit["valid"] or not audit["diagnostic_complete"]:
            raise SystemExit(1)
        return

    snapshot = build_status_snapshot(root)
    if args.json_output:
        write_json(args.json_output, snapshot)
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_markdown(snapshot), encoding="utf-8")
    print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
    if not snapshot["single_author_machine_audited_diagnostic"]["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
