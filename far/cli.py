"""Unified FAR command tree and deprecated console-script aliases."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from contextvars import ContextVar
from importlib.metadata import PackageNotFoundError, version
from typing import Any

_MAIN_CLI_DISPATCH: ContextVar[bool] = ContextVar("far_main_cli_dispatch", default=False)

_LEGACY_MIGRATIONS = {
    "falsirag-run": "falsirag run",
    "far-run": "falsirag run",
    "falsirag-baselines": "falsirag baselines",
    "falsirag-eval": "falsirag eval",
    "far-eval": "falsirag eval",
    "falsirag-suite": "falsirag suite",
    "falsirag-validate-bench": "falsirag bench validate",
    "far-validate-bench": "falsirag bench validate",
    "falsirag-annotate-packet": "falsirag bench annotate-packet",
    "falsirag-auto-annotate": "falsirag bench auto-annotate",
    "falsirag-weak-label": "falsirag bench weak-label",
    "falsirag-machine-label-audit": "falsirag bench machine-label-audit",
    "falsirag-machine-consensus": "falsirag bench machine-consensus",
    "falsirag-build-blind-bundle": "falsirag bench build-blind-bundle",
    "falsirag-build-ramdocs": "falsirag bench build-ramdocs",
    "falsirag-eval-ramdocs": "falsirag bench eval-ramdocs",
    "falsirag-ramdocs": "falsirag bench run-ramdocs",
    "falsirag-ramdocs-suite": "falsirag bench ramdocs-suite",
    "falsirag-build-boundary": "falsirag bench build-boundary",
    "falsirag-attribution": "falsirag diag attribution",
    "falsirag-attribution-evidence": "falsirag diag attribution-evidence",
    "falsirag-power": "falsirag diag power",
    "falsirag-family-dev": "falsirag diag family-dev",
    "falsirag-family-dev-evidence": "falsirag diag family-dev-evidence",
    "falsirag-boundary": "falsirag diag boundary",
    "falsirag-boundary-evidence": "falsirag diag boundary-evidence",
    "falsirag-eval-fever-binary": "falsirag diag fever-binary",
    "falsirag-type-mappability": "falsirag diag type-mappability",
    "falsirag-type-mappability-machine": "falsirag diag type-mappability-machine",
    "falsirag-jury-annotate": "falsirag jury annotate",
    "falsirag-jury-consensus": "falsirag jury consensus",
    "falsirag-jury-adjudication": "falsirag jury adjudication",
    "falsirag-jury-rescore": "falsirag jury rescore",
    "falsirag-jury-sensitivity": "falsirag jury sensitivity",
    "falsirag-jury-paper-readiness": "falsirag jury readiness",
    "falsirag-project-status": "falsirag ops project-status",
    "falsirag-repository-maintenance": "falsirag ops repository-maintenance",
    "falsirag-longterm-status": "falsirag ops longterm-status",
    "falsirag-review-priority": "falsirag ops review-priority",
    "falsirag-build-artifacts": "falsirag release artifacts",
    "falsirag-generate-sbom": "falsirag release sbom",
    "falsirag-release-checksums": "falsirag release checksums",
    "falsirag-scan-secrets": "falsirag release scan-secrets",
    "falsirag-submission-readiness": "falsirag release submission-readiness",
    "falsirag-solo-readiness": "falsirag release solo-readiness",
    "falsirag-solo-release": "falsirag release solo",
    "falsirag-solo-paper-readiness": "falsirag release solo-paper-readiness",
    "falsirag-score-blind-return": "falsirag release score-blind-return",
    "falsirag-model-matrix": "falsirag release model-matrix",
    "falsirag-verify-2plus4-smoke": "falsirag release verify-2plus4-smoke",
    "falsirag-round2-failure-readiness": "falsirag release round2-failure-readiness",
    "falsirag-one-shot": "falsirag release one-shot",
    "falsirag-2plus4-release": "falsirag release 2plus4",
}


def _warn_legacy_alias() -> None:
    invoked = sys.argv[0].rsplit("/", maxsplit=1)[-1]
    replacement = _LEGACY_MIGRATIONS.get(invoked)
    if replacement and not _MAIN_CLI_DISPATCH.get():
        print(
            f"warning: {invoked} is deprecated; use `{replacement}` instead",
            file=sys.stderr,
        )


def run_far_main() -> None:
    _warn_legacy_alias()
    from far.experiments.run_far import main

    main()


def run_baselines_main() -> None:
    _warn_legacy_alias()
    from far.experiments.run_baselines import main

    main()


def run_eval_main() -> None:
    _warn_legacy_alias()
    from far.eval.run_eval import main

    main()


def validate_bench_main() -> None:
    _warn_legacy_alias()
    from far.bench.build.validate_bench import main

    main()


def annotate_packet_main() -> None:
    _warn_legacy_alias()
    from far.bench.build.annotate_packet import main

    main()


def auto_annotate_main() -> None:
    _warn_legacy_alias()
    from far.bench.build.auto_annotate import main

    main()


def weak_label_main() -> None:
    _warn_legacy_alias()
    from far.bench.build.weak_label import main

    main()


def machine_label_audit_main() -> None:
    _warn_legacy_alias()
    from far.bench.build.machine_label_audit import main

    main()


def machine_consensus_main() -> None:
    _warn_legacy_alias()
    from far.bench.build.machine_consensus import main

    main()


def run_suite_main() -> None:
    _warn_legacy_alias()
    from far.experiments.run_suite import main

    main()


def build_artifacts_main() -> None:
    _warn_legacy_alias()
    from far.experiments.build_artifacts import main

    main()


def build_blind_bundle_main() -> None:
    _warn_legacy_alias()
    from far.bench.build.build_blind_bundle import main

    main()


def generate_sbom_main() -> None:
    _warn_legacy_alias()
    from far.experiments.generate_sbom import main

    main()


def generate_release_checksums_main() -> None:
    _warn_legacy_alias()
    from far.experiments.generate_release_checksums import main

    main()


def solo_paper_bundle_main() -> None:
    from far.experiments.solo_paper_bundle import main

    main()


def scan_secrets_main() -> None:
    _warn_legacy_alias()
    from far.experiments.scan_secrets import main

    main()


def submission_readiness_main() -> None:
    _warn_legacy_alias()
    from far.experiments.submission_readiness import main

    main()


def solo_readiness_main() -> None:
    _warn_legacy_alias()
    from far.experiments.solo_readiness import main

    main()


def solo_release_main() -> None:
    _warn_legacy_alias()
    from far.experiments.diagnostic_release import main

    main()


def evaluate_fever_binary_main() -> None:
    _warn_legacy_alias()
    from far.experiments.evaluate_fever_binary import main

    main()


def score_blind_return_main() -> None:
    _warn_legacy_alias()
    from far.experiments.score_blind_return import main

    main()


def review_priority_main() -> None:
    _warn_legacy_alias()
    from far.experiments.review_priority import main

    main()


def project_status_main() -> None:
    _warn_legacy_alias()
    from far.experiments.project_status import main

    main()


def repository_maintenance_main() -> None:
    _warn_legacy_alias()
    from far.experiments.repository_maintenance import main

    main()


def longterm_status_main() -> None:
    _warn_legacy_alias()
    from far.experiments.longterm_status import main

    main()


def solo_paper_readiness_main() -> None:
    _warn_legacy_alias()
    from far.experiments.solo_paper_readiness import main

    main()


def build_ramdocs_main() -> None:
    _warn_legacy_alias()
    from far.bench.build.ramdocs import main

    main()


def evaluate_ramdocs_main() -> None:
    _warn_legacy_alias()
    from far.eval.ramdocs import main

    main()


def run_ramdocs_main() -> None:
    _warn_legacy_alias()
    from far.experiments.run_ramdocs import main

    main()


def jury_annotate_main() -> None:
    _warn_legacy_alias()
    from far.bench.build.jury_annotate import main

    main()


def jury_consensus_main() -> None:
    _warn_legacy_alias()
    from far.bench.build.jury_consensus import main

    main()


def jury_adjudication_main() -> None:
    _warn_legacy_alias()
    from far.bench.build.jury_adjudication import main

    main()


def ramdocs_suite_main() -> None:
    _warn_legacy_alias()
    from far.experiments.ramdocs_suite import main

    main()


def model_matrix_main() -> None:
    _warn_legacy_alias()
    from far.experiments.model_matrix import main

    main()


def verify_2plus4_model_smoke_main() -> None:
    _warn_legacy_alias()
    from far.experiments.model_smoke_2plus4 import main

    main()


def ramdocs_round2_failure_readiness_main() -> None:
    _warn_legacy_alias()
    from far.experiments.ramdocs_round2_failure_readiness import main

    main()


def jury_rescore_main() -> None:
    _warn_legacy_alias()
    from far.experiments.jury_rescore import main

    main()


def one_shot_main() -> None:
    _warn_legacy_alias()
    from far.experiments.one_shot import main

    main()


def jury_paper_readiness_main() -> None:
    _warn_legacy_alias()
    from far.experiments.jury_paper_readiness import main

    main()


def evidence_2plus4_main() -> None:
    _warn_legacy_alias()
    from far.experiments.evidence_2plus4 import main

    main()


def jury_sensitivity_main() -> None:
    _warn_legacy_alias()
    from far.experiments.jury_sensitivity import main

    main()


def attribution_main() -> None:
    _warn_legacy_alias()
    from far.experiments.attribution import main

    main()


def evidence_attribution_main() -> None:
    _warn_legacy_alias()
    from far.experiments.evidence_attribution import main

    main()


def power_main() -> None:
    _warn_legacy_alias()
    from far.experiments.power import main

    main()


def family_dev_main() -> None:
    _warn_legacy_alias()
    from far.experiments.family_dev import main

    main()


def evidence_family_dev_main() -> None:
    _warn_legacy_alias()
    from far.experiments.evidence_family_dev import main

    main()


def build_boundary_main() -> None:
    _warn_legacy_alias()
    from far.bench.build.boundary import main

    main()


def boundary_main() -> None:
    _warn_legacy_alias()
    from far.experiments.boundary import main

    main()


def evidence_boundary_main() -> None:
    _warn_legacy_alias()
    from far.experiments.evidence_boundary import main

    main()


def stage_trace_map_main() -> None:
    _warn_legacy_alias()
    from far.experiments.stage_trace_map import main

    main()


def revision_trace_audit_main() -> None:
    from far.experiments.revision_trace_audit import main

    main()


def selective_revision_audit_main() -> None:
    from far.experiments.selective_revision_audit import main

    main()


def selective_acceptance_main() -> None:
    from far.experiments.selective_acceptance import main

    main()


def type_mappability_main() -> None:
    _warn_legacy_alias()
    from far.experiments.type_mappability import main

    main()


def type_mappability_machine_main() -> None:
    _warn_legacy_alias()
    from far.experiments.type_mappability_machine import main

    main()


def p5_ablations_main() -> None:
    _warn_legacy_alias()
    from far.experiments.p5_ablations import main

    main()


def diagnostic_artifacts_main() -> None:
    _warn_legacy_alias()
    from far.artifacts import main

    main()


def _distribution_version() -> str:
    try:
        return version("falsification-augmented-retrieval")
    except PackageNotFoundError:
        return "0.1.0+source"


def _add_leaf(
    subparsers: Any,
    name: str,
    handler: Callable[[], None],
    summary: str,
    command_path: str,
) -> None:
    leaf = subparsers.add_parser(
        name,
        help=summary,
        description=f"{summary} Arguments after this command are forwarded unchanged.",
        add_help=False,
    )
    leaf.set_defaults(_handler=handler, _command_path=command_path)


def _add_group(subparsers: Any, name: str, summary: str) -> Any:
    group = subparsers.add_parser(name, help=summary, description=summary)
    return group.add_subparsers(dest=f"{name}_command", required=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="falsirag",
        description=(
            "Run FAR experiments, diagnostics, benchmark tools, jury workflows, "
            "maintenance checks, and release gates from one command tree."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_distribution_version()}",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    _add_leaf(commands, "run", run_far_main, "Run FAR or one ablation.", "run")
    _add_leaf(commands, "suite", run_suite_main, "Run a matched experiment suite.", "suite")
    _add_leaf(
        commands,
        "baselines",
        run_baselines_main,
        "Run transparent baseline methods.",
        "baselines",
    )
    _add_leaf(commands, "eval", run_eval_main, "Evaluate FAR predictions.", "eval")

    bench = _add_group(commands, "bench", "Build, label, run, and validate benchmarks.")
    _add_leaf(bench, "validate", validate_bench_main, "Validate FalsiRAG-Bench.", "bench validate")
    _add_leaf(
        bench,
        "annotate-packet",
        annotate_packet_main,
        "Build an annotation packet.",
        "bench annotate-packet",
    )
    _add_leaf(
        bench,
        "auto-annotate",
        auto_annotate_main,
        "Generate or exchange machine preannotations.",
        "bench auto-annotate",
    )
    _add_leaf(bench, "weak-label", weak_label_main, "Generate weak labels.", "bench weak-label")
    _add_leaf(
        bench,
        "machine-label-audit",
        machine_label_audit_main,
        "Audit machine labels.",
        "bench machine-label-audit",
    )
    _add_leaf(
        bench,
        "machine-consensus",
        machine_consensus_main,
        "Build machine-consensus evidence.",
        "bench machine-consensus",
    )
    _add_leaf(
        bench,
        "build-blind-bundle",
        build_blind_bundle_main,
        "Build a gold-free blind bundle.",
        "bench build-blind-bundle",
    )
    _add_leaf(
        bench,
        "build-ramdocs",
        build_ramdocs_main,
        "Build or verify the RAMDocs import.",
        "bench build-ramdocs",
    )
    _add_leaf(
        bench,
        "eval-ramdocs",
        evaluate_ramdocs_main,
        "Evaluate RAMDocs predictions.",
        "bench eval-ramdocs",
    )
    _add_leaf(
        bench,
        "run-ramdocs",
        run_ramdocs_main,
        "Run one RAMDocs method.",
        "bench run-ramdocs",
    )
    _add_leaf(
        bench,
        "ramdocs-suite",
        ramdocs_suite_main,
        "Run or finalize a RAMDocs suite.",
        "bench ramdocs-suite",
    )
    _add_leaf(
        bench,
        "build-boundary",
        build_boundary_main,
        "Build external boundary datasets.",
        "bench build-boundary",
    )

    diag = _add_group(commands, "diag", "Run model-free and model-backed diagnostics.")
    _add_leaf(
        diag,
        "attribution",
        attribution_main,
        "Run frozen mechanism attribution.",
        "diag attribution",
    )
    _add_leaf(
        diag,
        "attribution-evidence",
        evidence_attribution_main,
        "Build or verify attribution evidence.",
        "diag attribution-evidence",
    )
    _add_leaf(diag, "power", power_main, "Run the preregistered power gate.", "diag power")
    _add_leaf(
        diag,
        "family-dev",
        family_dev_main,
        "Run cross-family development diagnostics.",
        "diag family-dev",
    )
    _add_leaf(
        diag,
        "family-dev-evidence",
        evidence_family_dev_main,
        "Build or verify cross-family evidence.",
        "diag family-dev-evidence",
    )
    _add_leaf(
        diag,
        "boundary",
        boundary_main,
        "Run external boundary diagnostics.",
        "diag boundary",
    )
    _add_leaf(
        diag,
        "boundary-evidence",
        evidence_boundary_main,
        "Build or verify boundary evidence.",
        "diag boundary-evidence",
    )
    _add_leaf(
        diag,
        "fever-binary",
        evaluate_fever_binary_main,
        "Evaluate or verify the FEVER binary diagnostic.",
        "diag fever-binary",
    )
    _add_leaf(
        diag,
        "trace-map",
        stage_trace_map_main,
        "Build or verify the capability-aware stage trace map.",
        "diag trace-map",
    )
    _add_leaf(
        diag,
        "revision-trace-audit",
        revision_trace_audit_main,
        "Build or verify frozen revision-trace fidelity.",
        "diag revision-trace-audit",
    )
    _add_leaf(
        diag,
        "selective-revision-audit",
        selective_revision_audit_main,
        "Build or verify frozen selective-revision feasibility.",
        "diag selective-revision-audit",
    )
    _add_leaf(
        diag,
        "selective-acceptance",
        selective_acceptance_main,
        "Prepare, run, or verify preregistered selective acceptance.",
        "diag selective-acceptance",
    )
    _add_leaf(
        diag,
        "type-mappability",
        type_mappability_main,
        "Prepare, hand off, or analyze the P6 type-mappability study.",
        "diag type-mappability",
    )
    _add_leaf(
        diag,
        "type-mappability-machine",
        type_mappability_machine_main,
        "Run or verify the machine-only P6-M ontology-stability audit.",
        "diag type-mappability-machine",
    )
    _add_leaf(
        diag,
        "p5-ablations",
        p5_ablations_main,
        "Run or verify the registered P5 RAMDocs ablations.",
        "diag p5-ablations",
    )

    jury = _add_group(commands, "jury", "Run the optional cross-family jury workflow.")
    _add_leaf(jury, "annotate", jury_annotate_main, "Run one juror.", "jury annotate")
    _add_leaf(jury, "consensus", jury_consensus_main, "Compute jury consensus.", "jury consensus")
    _add_leaf(
        jury,
        "adjudication",
        jury_adjudication_main,
        "Prepare or import blind adjudication.",
        "jury adjudication",
    )
    _add_leaf(jury, "rescore", jury_rescore_main, "Rescore with jury labels.", "jury rescore")
    _add_leaf(
        jury,
        "sensitivity",
        jury_sensitivity_main,
        "Run jury-label sensitivity analysis.",
        "jury sensitivity",
    )
    _add_leaf(
        jury,
        "readiness",
        jury_paper_readiness_main,
        "Check the 2+4 paper gate.",
        "jury readiness",
    )

    ops = _add_group(commands, "ops", "Inspect project status and maintenance invariants.")
    _add_leaf(
        ops,
        "project-status",
        project_status_main,
        "Generate or verify project status.",
        "ops project-status",
    )
    _add_leaf(
        ops,
        "repository-maintenance",
        repository_maintenance_main,
        "Audit repository hygiene.",
        "ops repository-maintenance",
    )
    _add_leaf(
        ops,
        "longterm-status",
        longterm_status_main,
        "Generate or check the long-term roadmap ledger.",
        "ops longterm-status",
    )
    _add_leaf(
        ops,
        "review-priority",
        review_priority_main,
        "Build human-review priorities.",
        "ops review-priority",
    )
    _add_leaf(
        ops,
        "diagnostic-data",
        diagnostic_artifacts_main,
        "Pack, verify, or install diagnostic data.",
        "ops diagnostic-data",
    )

    release = _add_group(commands, "release", "Build and verify public or submission artifacts.")
    _add_leaf(
        release,
        "artifacts",
        build_artifacts_main,
        "Build experiment artifacts.",
        "release artifacts",
    )
    _add_leaf(release, "sbom", generate_sbom_main, "Generate an SBOM.", "release sbom")
    _add_leaf(
        release,
        "checksums",
        generate_release_checksums_main,
        "Generate release checksums.",
        "release checksums",
    )
    _add_leaf(
        release,
        "solo-paper-bundle",
        solo_paper_bundle_main,
        "Pack or verify the portable no-human TMLR release.",
        "release solo-paper-bundle",
    )
    _add_leaf(
        release,
        "scan-secrets",
        scan_secrets_main,
        "Scan tracked content for secrets.",
        "release scan-secrets",
    )
    _add_leaf(
        release,
        "submission-readiness",
        submission_readiness_main,
        "Check strict submission readiness.",
        "release submission-readiness",
    )
    _add_leaf(
        release,
        "solo-readiness",
        solo_readiness_main,
        "Check the single-author diagnostic profile.",
        "release solo-readiness",
    )
    _add_leaf(
        release,
        "solo",
        solo_release_main,
        "Build or verify the public diagnostic bundle.",
        "release solo",
    )
    _add_leaf(
        release,
        "solo-paper-readiness",
        solo_paper_readiness_main,
        "Check narrowed paper claims.",
        "release solo-paper-readiness",
    )
    _add_leaf(
        release,
        "score-blind-return",
        score_blind_return_main,
        "Score a verified blind return.",
        "release score-blind-return",
    )
    _add_leaf(
        release,
        "model-matrix",
        model_matrix_main,
        "Run or inspect the formal model matrix.",
        "release model-matrix",
    )
    _add_leaf(
        release,
        "verify-2plus4-smoke",
        verify_2plus4_model_smoke_main,
        "Verify the 2+4 model smoke bundle.",
        "release verify-2plus4-smoke",
    )
    _add_leaf(
        release,
        "round2-failure-readiness",
        ramdocs_round2_failure_readiness_main,
        "Verify the Round 2 stopped branch.",
        "release round2-failure-readiness",
    )
    _add_leaf(
        release,
        "one-shot",
        one_shot_main,
        "Run the guarded one-shot workflow.",
        "release one-shot",
    )
    _add_leaf(
        release,
        "2plus4",
        evidence_2plus4_main,
        "Build or verify the 2+4 evidence release.",
        "release 2plus4",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Dispatch the consolidated ``falsirag`` command tree."""

    parser = _build_parser()
    namespace, forwarded = parser.parse_known_args(list(argv) if argv is not None else None)
    handler = namespace._handler
    command_path = str(namespace._command_path)
    previous_argv = sys.argv
    token = _MAIN_CLI_DISPATCH.set(True)
    sys.argv = [f"falsirag {command_path}", *forwarded]
    try:
        handler()
    finally:
        sys.argv = previous_argv
        _MAIN_CLI_DISPATCH.reset(token)
