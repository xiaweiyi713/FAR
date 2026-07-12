from __future__ import annotations

import os
import subprocess

from far.paths import repository_root

ROOT = repository_root()
SCRIPTS = (
    "preflight_windows_p6_prelabels.sh",
    "prepare_windows_p6_prelabels.sh",
    "start_windows_p6_prelabels.sh",
    "check_windows_p6_prelabels.sh",
    "stop_windows_p6_prelabels.sh",
    "fetch_windows_p6_prelabels.sh",
)


def test_p6_remote_scripts_are_executable_and_parse_as_bash() -> None:
    paths = [ROOT / "scripts" / name for name in SCRIPTS]

    assert all(path.is_file() and os.access(path, os.X_OK) for path in paths)
    subprocess.run(["bash", "-n", *map(str, paths)], check=True, cwd=ROOT)


def test_p6_remote_mutations_are_default_deny_before_ssh() -> None:
    cases = (
        ("prepare_windows_p6_prelabels.sh", "FAR_P6_PREP_ALLOWED"),
        ("start_windows_p6_prelabels.sh", "FAR_P6_PRELABEL_ALLOWED"),
        ("fetch_windows_p6_prelabels.sh", "FAR_P6_FETCH_ALLOWED"),
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


def test_p6_systemd_units_bind_remote_packet_and_prelabel_runner() -> None:
    runner = (ROOT / "scripts/systemd/far-p6-prelabels.service").read_text(encoding="utf-8")
    ollama = (ROOT / "scripts/systemd/far-ollama-p6.service").read_text(encoding="utf-8")

    assert "WorkingDirectory=/mnt/d/FAR-workspace/FAR-longterm" in runner
    assert "python -m far.experiments.type_mappability prelabel" in runner
    assert "--packet-dir /mnt/d/FAR-outputs/type_mappability_v1" in runner
    assert "Wants=far-ollama-p6.service" in runner
    assert "Restart=no" in runner
    assert "WorkingDirectory=/mnt/d/FAR-workspace/FAR-longterm" in ollama
    assert "source scripts/windows_gpu_env.sh; exec ollama serve" in ollama
    starter = (ROOT / "scripts/start_windows_p6_prelabels.sh").read_text(encoding="utf-8")
    assert "stable >= 3" in starter
    assert "did not become stable within 180 seconds" in starter
