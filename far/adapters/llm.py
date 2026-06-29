"""LLM protocol and VeraRAG client adapter."""

from __future__ import annotations

from typing import Any

from ..protocols import TextGenerator

__all__ = ["TextGenerator", "VeraLLMAdapter"]


class VeraLLMAdapter:
    """Wrap VeraRAG's six-provider client behind FAR's small stable interface."""

    SUPPORTED_PROVIDERS = (
        "openai",
        "anthropic",
        "ollama",
        "dashscope",
        "zhipuai",
        "deepseek",
    )

    def __init__(self, client: Any | None = None, **client_options: Any) -> None:
        if client is None:
            provider = str(client_options.get("provider", "ollama")).strip().lower()
            if provider not in self.SUPPORTED_PROVIDERS:
                supported = ", ".join(self.SUPPORTED_PROVIDERS)
                raise ValueError(
                    f"unsupported VeraRAG LLM provider {provider!r}; choose {supported}"
                )
            client_options["provider"] = provider
            try:
                from src.utils.llm_client import LLMClient
            except ImportError as exc:
                raise RuntimeError(
                    "VeraRAG is not importable. Install it with "
                    "`python -m pip install -e /path/to/VeraRAG`."
                ) from exc
            client = LLMClient(**client_options)
        self.client = client

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        return str(
            self.client.generate(
                prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )
