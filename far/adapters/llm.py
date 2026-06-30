"""LLM protocol and VeraRAG client adapter."""

from __future__ import annotations

from typing import Any

from ..protocols import TextGenerator

__all__ = ["TextGenerator", "VeraLLMAdapter"]


class _OllamaGenerateClient:
    """Small Ollama client shim with explicit thinking-mode control."""

    def __init__(self, **client_options: Any) -> None:
        try:
            import ollama
        except ImportError as exc:
            raise RuntimeError(
                "The ollama Python package is required for the local Ollama provider."
            ) from exc
        self.model = str(client_options.get("model", "qwen3.5:9b"))
        self.think = client_options.get("think")
        if self.think is not None and not isinstance(self.think, bool):
            raise TypeError("Ollama 'think' must be true, false, or omitted")
        self.keep_alive = client_options.get("keep_alive")
        if self.keep_alive is not None and not isinstance(self.keep_alive, int | float | str):
            raise TypeError("Ollama 'keep_alive' must be a number, string, or omitted")
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
        if self.think is not None:
            kwargs["think"] = self.think
        if self.keep_alive is not None:
            kwargs["keep_alive"] = self.keep_alive
        if response_format == "json":
            kwargs["format"] = "json"
        response = self.client.generate(**kwargs)
        text = self._response_field(response, "response")
        if isinstance(text, str) and text.strip():
            return text
        thinking = self._response_field(response, "thinking")
        if isinstance(thinking, str) and thinking.strip():
            raise RuntimeError(
                "Ollama returned thinking text without a final response; set llm.think=false "
                "for publication runs or increase the generation budget"
            )
        raise RuntimeError("Ollama returned an empty final response")

    def unload(self) -> None:
        """Unload the model and clear Ollama's cross-request prompt cache."""

        self.client.generate(model=self.model, prompt="", keep_alive=0)


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
        unload_after_sample = client_options.pop("unload_after_sample", False)
        if not isinstance(unload_after_sample, bool):
            raise TypeError("'unload_after_sample' must be true or false")
        self.unload_after_sample = unload_after_sample
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

    def release(self) -> None:
        """Release local model state at the configured sample boundary."""

        if not self.unload_after_sample:
            return
        unload = getattr(self.client, "unload", None)
        if callable(unload):
            unload()

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
