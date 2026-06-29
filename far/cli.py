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
