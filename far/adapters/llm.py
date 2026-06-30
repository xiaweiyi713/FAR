"""LLM protocol and VeraRAG client adapter."""

from __future__ import annotations

from typing import Any

from ..protocols import TextGenerator

__all__ = ["TextGenerator", "VeraLLMAdapter"]


class _OllamaGenerateClient:
    """Small Ollama client shim for thinking models that leave ``response`` empty."""

    def __init__(self, **client_options: Any) -> None:
        try:
            import ollama
        except ImportError as exc:
            raise RuntimeError(
                "The ollama Python package is required for the local Ollama provider."
            ) from exc
        self.model = str(client_options.get("model", "qwen3.5:9b"))
        self.client = ollama.Client(host=client_options.get("base_url") or "http://localhost:11434")

    @staticmethod
    def _response_field(response: Any, field: str) -> Any:
        if hasattr(response, "get"):
            return response.get(field)
        return getattr(response, field, None)

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        response_format: str | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if response_format == "json":
            kwargs["format"] = "json"
        response = self.client.generate(**kwargs)
        text = self._response_field(response, "response")
        if isinstance(text, str) and text.strip():
            return text
        thinking = self._response_field(response, "thinking")
        if isinstance(thinking, str):
            return thinking
        return "" if text is None else str(text)


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
            if provider == "ollama":
                client = _OllamaGenerateClient(**client_options)
                self.client = client
                return
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
        response_format: str | None = None,
    ) -> str:
        return str(
            self.client.generate(
                prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
        )
