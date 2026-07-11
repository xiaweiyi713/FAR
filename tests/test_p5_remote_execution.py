from __future__ import annotations

import os
import subprocess

from far.paths import repository_root

ROOT = repository_root()
SCRIPTS = (
    "preflight_windows_p5_ablations.sh",
    "prepare_windows_p5_ablations.sh",
    "start_windows_p5_ablations.sh",
    "check_windows_p5_ablations.sh",
    "stop_windows_p5_ablations.sh",
    "fetch_windows_p5_ablations.sh",
)


def test_p5_remote_scripts_are_executable_and_parse_as_bash() -> None:
    paths = [ROOT / "scripts" / name for name in SCRIPTS]

    assert all(path.is_file() and os.access(path, os.X_OK) for path in paths)
    subprocess.run(["bash", "-n", *map(str, paths)], check=True, cwd=ROOT)


def test_p5_remote_mutations_are_default_deny_before_ssh() -> None:
    cases = (
        ("prepare_windows_p5_ablations.sh", "FAR_P5_PREP_ALLOWED"),
        ("start_windows_p5_ablations.sh", "FAR_P5_TRAINING_ALLOWED"),
        ("fetch_windows_p5_ablations.sh", "FAR_P5_FETCH_ALLOWED"),
    )
    for script, authorization in cases:
        environment = dict(os.environ)
        environment.pop(authorization, None)
        completed = subprocess.run(
            [str(ROOT / "scripts" / script), "--execute", "unreachable.invalid"],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert completed.returncode == 3


def test_p5_systemd_units_bind_remote_paths_and_registered_runner() -> None:
    runner = (ROOT / "scripts/systemd/far-p5-ablations.service").read_text(encoding="utf-8")
    ollama = (ROOT / "scripts/systemd/far-ollama-p5.service").read_text(encoding="utf-8")

    assert "WorkingDirectory=/mnt/d/FAR-workspace/FAR-longterm" in runner
    assert "python -m far.experiments.p5_ablations run-all" in runner
    assert "--output-dir /mnt/d/FAR-outputs/p5_ramdocs_v1" in runner
    assert "Wants=far-ollama-p5.service" in runner
    assert "WorkingDirectory=/mnt/d/FAR-workspace/FAR-longterm" in ollama
    assert "source scripts/windows_gpu_env.sh; exec ollama serve" in ollama
