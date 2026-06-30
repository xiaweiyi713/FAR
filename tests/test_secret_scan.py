from __future__ import annotations

from pathlib import Path

from experiments.scan_secrets import scan_paths


def _fake_key() -> str:
    return "sk-" + ("r" * 32)


def test_secret_scan_detects_and_redacts_api_key(tmp_path: Path) -> None:
    token = _fake_key()
    (tmp_path / "leak.py").write_text(f'DEEPSEEK_API_KEY = "{token}"\n', encoding="utf-8")

    findings = scan_paths([tmp_path])

    assert {item.rule for item in findings} == {
        "generic_secret_assignment",
        "openai_or_deepseek_style_key",
    }
    assert all(token not in item.redacted for item in findings)


def test_secret_scan_allows_documented_placeholders(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "\n".join(
            [
                'DEEPSEEK_API_KEY="<paste key here>"',
                'OPENAI_API_KEY="sk-xxx"',
                'api_key = "${DEEPSEEK_API_KEY}"',
                'api_key = "your-api-key"',
            ]
        ),
        encoding="utf-8",
    )

    assert scan_paths([tmp_path]) == []


def test_repository_has_no_high_confidence_secret() -> None:
    assert scan_paths([Path(__file__).parents[1]]) == []
