"""Small stable protocols shared by FAR components and adapters."""

from __future__ import annotations

from typing import Protocol


class TextGenerator(Protocol):
    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        response_format: str | None = None,
    ) -> str: ...
