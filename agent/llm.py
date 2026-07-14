"""
Thin, provider-agnostic wrapper around the Google GenAI and Groq/Grok APIs.

The rest of the agent talks to `LLMClient` and never has to know which
provider is behind it.
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
        if self.config.provider == "gemini":
            if not self.config.gemini_api_key:
                raise LLMError(
                    "GOOGLE_API_KEY (or GEMINI_API_KEY) is not set. Add it to your .env file."
                )
            from google import genai

            return genai.Client(api_key=self.config.gemini_api_key)

        elif self.config.provider in ("groq", "grok"):
            if not self.config.groq_api_key:
                raise LLMError(
                    "GROK_API_KEY (or GROQ_API_KEY) is not set. Add it to your .env file."
                )
            import openai

            return openai.OpenAI(
                api_key=self.config.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
            )
        else:
            raise LLMError(f"Unsupported provider: {self.config.provider}")

    def stream(self, system: str, messages: list[dict[str, str]]) -> Iterator[str]:
        """
        Yields response text incrementally as it streams in from the model.
        `messages` is a list of {"role": "user"|"assistant", "content": str}.
        """
        if self.config.provider == "gemini":
            yield from self._stream_gemini(system, messages)
        else:
            yield from self._stream_groq(system, messages)

    def _stream_gemini(self, system: str, messages: list[dict[str, str]]) -> Iterator[str]:
        try:
            from google.genai import types

            contents = []
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg["content"])]
                    )
                )

            config = types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=self.config.max_tokens,
            )

            response = self._client.models.generate_content_stream(
                model=self.config.gemini_model,
                contents=contents,
                config=config,
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Gemini API call failed: {exc}") from exc

    def _stream_groq(self, system: str, messages: list[dict[str, str]]) -> Iterator[str]:
        try:
            full_messages = [{"role": "system", "content": system}, *messages]
            with self._client.chat.completions.create(
                model=self.config.groq_model,
                max_tokens=self.config.max_tokens,
                messages=full_messages,
                stream=True,
            ) as stream:
                for chunk in stream:
                    if chunk.choices:
                        delta = chunk.choices[0].delta.content
                        if delta:
                            yield delta
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"{self.config.provider.capitalize()} API call failed: {exc}") from exc
