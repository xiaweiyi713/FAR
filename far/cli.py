"""Console entry point shims that are safe beside VeraRAG's top-level packages.

FAR intentionally reuses VeraRAG as an editable local dependency during
development. Both projects expose research helper packages with generic names
such as ``experiments``. Console scripts are executed from the virtual
environment, so import order can otherwise resolve those generic modules from
VeraRAG instead of this repository. These small shims put FAR's repository root
at the front of ``sys.path`` before importing the actual command modules.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _prefer_far_repo() -> None:
    root = Path(__file__).resolve().parents[1]
    root_text = str(root)
    if sys.path[:1] != [root_text]:
        sys.path = [path for path in sys.path if path != root_text]
        sys.path.insert(0, root_text)


def run_far_main() -> None:
    _prefer_far_repo()
    from experiments.run_far import main

    main()


def run_baselines_main() -> None:
    _prefer_far_repo()
    from experiments.run_baselines import main

    main()


def run_eval_main() -> None:
    _prefer_far_repo()
    from eval.run_eval import main

    main()


def validate_bench_main() -> None:
    _prefer_far_repo()
    from bench.build.validate_bench import main

    main()


def annotate_packet_main() -> None:
    _prefer_far_repo()
    from bench.build.annotate_packet import main

    main()


def auto_annotate_main() -> None:
    _prefer_far_repo()
    from bench.build.auto_annotate import main

    main()


def weak_label_main() -> None:
    _prefer_far_repo()
    from bench.build.weak_label import main

    main()


def machine_label_audit_main() -> None:
    _prefer_far_repo()
    from bench.build.machine_label_audit import main

    main()


def machine_consensus_main() -> None:
    _prefer_far_repo()
    from bench.build.machine_consensus import main

    main()


def run_suite_main() -> None:
    _prefer_far_repo()
    from experiments.run_suite import main

    main()


def build_artifacts_main() -> None:
    _prefer_far_repo()
    from experiments.build_artifacts import main

    main()


def build_blind_bundle_main() -> None:
    _prefer_far_repo()
    from bench.build.build_blind_bundle import main

    main()


def generate_sbom_main() -> None:
    _prefer_far_repo()
    from experiments.generate_sbom import main

    main()


def generate_release_checksums_main() -> None:
    _prefer_far_repo()
    from experiments.generate_release_checksums import main

    main()


def scan_secrets_main() -> None:
    _prefer_far_repo()
    from experiments.scan_secrets import main

    main()


def submission_readiness_main() -> None:
    _prefer_far_repo()
    from experiments.submission_readiness import main

    main()


def solo_readiness_main() -> None:
    _prefer_far_repo()
    from experiments.solo_readiness import main

    main()


def solo_release_main() -> None:
    _prefer_far_repo()
    from experiments.diagnostic_release import main

    main()


def evaluate_fever_binary_main() -> None:
    _prefer_far_repo()
    from experiments.evaluate_fever_binary import main

    main()


def score_blind_return_main() -> None:
    _prefer_far_repo()
    from experiments.score_blind_return import main

    main()


def review_priority_main() -> None:
    _prefer_far_repo()
    from experiments.review_priority import main

    main()


def project_status_main() -> None:
    _prefer_far_repo()
    from experiments.project_status import main

    main()


def solo_paper_readiness_main() -> None:
    _prefer_far_repo()
    from experiments.solo_paper_readiness import main

    main()


def build_ramdocs_main() -> None:
    _prefer_far_repo()
    from bench.build.ramdocs import main

    main()


def evaluate_ramdocs_main() -> None:
    _prefer_far_repo()
    from eval.ramdocs import main

    main()


def run_ramdocs_main() -> None:
    _prefer_far_repo()
    from experiments.run_ramdocs import main

    main()


def jury_annotate_main() -> None:
    _prefer_far_repo()
    from bench.build.jury_annotate import main

    main()


def jury_consensus_main() -> None:
    _prefer_far_repo()
    from bench.build.jury_consensus import main

    main()


def jury_adjudication_main() -> None:
    _prefer_far_repo()
    from bench.build.jury_adjudication import main

    main()


def ramdocs_suite_main() -> None:
    _prefer_far_repo()
    from experiments.ramdocs_suite import main

    main()


def model_matrix_main() -> None:
    _prefer_far_repo()
    from experiments.model_matrix import main

    main()


def jury_rescore_main() -> None:
    _prefer_far_repo()
    from experiments.jury_rescore import main

    main()


def one_shot_main() -> None:
    _prefer_far_repo()
    from experiments.one_shot import main

    main()


def jury_paper_readiness_main() -> None:
    _prefer_far_repo()
    from experiments.jury_paper_readiness import main

    main()


def evidence_2plus4_main() -> None:
    _prefer_far_repo()
    from experiments.evidence_2plus4 import main

    main()


def jury_sensitivity_main() -> None:
    _prefer_far_repo()
    from experiments.jury_sensitivity import main

    main()
