"""
Thin, provider-agnostic wrapper around the Anthropic and OpenAI SDKs.

The rest of the agent talks to `LLMClient` and never has to know which
provider is behind it. This is the seam we'll use later to add model
switching, local models, etc. (Milestone: "Model switching").
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from agent.config import Config


class LLMError(RuntimeError):
    """Raised when a provider call fails in a way the caller should handle."""


class LLMClient:
    def __init__(self, config: Config):
        self.config = config
        self._client = self._build_client()

    def _build_client(self) -> Any:
        if self.config.provider == "anthropic":
            if not self.config.anthropic_api_key:
                raise LLMError(
                    "ANTHROPIC_API_KEY is not set. Add it to your .env file "
                    "(see .env.example)."
                )
            import anthropic

            return anthropic.Anthropic(api_key=self.config.anthropic_api_key)

        if not self.config.openai_api_key:
            raise LLMError(
                "OPENAI_API_KEY is not set. Add it to your .env file "
                "(see .env.example)."
            )
        import openai

        return openai.OpenAI(api_key=self.config.openai_api_key)

    def stream(self, system: str, messages: list[dict[str, str]]) -> Iterator[str]:
        """
        Yields response text incrementally as it streams in from the model.
        `messages` is a list of {"role": "user"|"assistant", "content": str}.
        """
        if self.config.provider == "anthropic":
            yield from self._stream_anthropic(system, messages)
        else:
            yield from self._stream_openai(system, messages)

    def _stream_anthropic(self, system: str, messages: list[dict[str, str]]) -> Iterator[str]:
        try:
            with self._client.messages.stream(
                model=self.config.anthropic_model,
                max_tokens=self.config.max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                yield from stream.text_stream
        except Exception as exc:  # noqa: BLE001 - surface a clean error to the CLI
            raise LLMError(f"Anthropic API call failed: {exc}") from exc

    def _stream_openai(self, system: str, messages: list[dict[str, str]]) -> Iterator[str]:
        try:
            full_messages = [{"role": "system", "content": system}, *messages]
            stream = self._client.chat.completions.create(
                model=self.config.openai_model,
                max_tokens=self.config.max_tokens,
                messages=full_messages,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"OpenAI API call failed: {exc}") from exc
