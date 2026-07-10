from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from far import cli

ROOT = Path(__file__).resolve().parents[1]


def test_main_help_exposes_grouped_command_tree(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--help"])

    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    assert "{run,suite,baselines,eval,bench,diag,jury,ops,release}" in output
    assert "Run FAR or one ablation" in output
    assert "Run model-free and model-backed diagnostics" in output


def test_group_help_lists_leaf_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["diag", "--help"])

    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    assert "attribution" in output
    assert "boundary-evidence" in output
    assert "fever-binary" in output
    assert "trace-map" in output


def test_dispatch_forwards_arguments_and_restores_sys_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []
    original = sys.argv

    def fake_attribution() -> None:
        observed.extend(sys.argv)

    monkeypatch.setattr(cli, "attribution_main", fake_attribution)
    cli.main(
        [
            "diag",
            "attribution",
            "--analysis-freeze-commit",
            "abc1234",
            "--resamples",
            "20",
        ]
    )

    assert observed == [
        "falsirag diag attribution",
        "--analysis-freeze-commit",
        "abc1234",
        "--resamples",
        "20",
    ]
    assert sys.argv is original


def test_leaf_help_is_forwarded_to_existing_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []

    def fake_run() -> None:
        observed.extend(sys.argv)

    monkeypatch.setattr(cli, "run_far_main", fake_run)
    cli.main(["run", "--help"])

    assert observed == ["falsirag run", "--help"]


def test_legacy_alias_prints_migration_hint(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["falsirag-run"])
    cli._prefer_far_repo()

    error = capsys.readouterr().err
    assert "deprecated" in error
    assert "falsirag run" in error


def test_new_dispatch_suppresses_legacy_hint(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_run() -> None:
        cli._prefer_far_repo()

    monkeypatch.setattr(cli, "run_far_main", fake_run)
    cli.main(["run"])

    assert "deprecated" not in capsys.readouterr().err


def test_every_legacy_console_script_has_a_valid_migration_target() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    scripts = pyproject.split("[project.scripts]", maxsplit=1)[1].split(
        "[tool.setuptools]", maxsplit=1
    )[0]
    names = set(re.findall(r'^([A-Za-z0-9_-]+)\s*=\s*"far\.cli:', scripts, re.MULTILINE))
    legacy_names = names - {"falsirag"}

    assert legacy_names == set(cli._LEGACY_MIGRATIONS)
    parser = cli._build_parser()
    for replacement in sorted(set(cli._LEGACY_MIGRATIONS.values())):
        path = replacement.removeprefix("falsirag ").split()
        namespace, forwarded = parser.parse_known_args(path)
        assert callable(namespace._handler)
        assert forwarded == []
