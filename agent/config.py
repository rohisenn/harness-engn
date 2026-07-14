"""
Centralized configuration for harness.

All environment variables are read here, once, so the rest of the
codebase never touches os.environ directly. This makes it trivial to
add new providers or settings later without hunting through the code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env from the current working directory (or any parent) the moment
# this module is imported. Safe to call even if no .env file exists.
load_dotenv()


@dataclass(frozen=True)
class Config:
    provider: str
    anthropic_api_key: str | None
    anthropic_model: str
    openai_api_key: str | None
    openai_model: str
    max_tokens: int

    @property
    def active_model(self) -> str:
        return self.anthropic_model if self.provider == "anthropic" else self.openai_model

    @property
    def active_api_key(self) -> str | None:
        return self.anthropic_api_key if self.provider == "anthropic" else self.openai_api_key


def load_config(provider_override: str | None = None, model_override: str | None = None) -> Config:
    provider = (provider_override or os.getenv("HARNESS_PROVIDER", "anthropic")).lower()

    if provider not in ("anthropic", "openai"):
        raise ValueError(
            f"Unknown provider '{provider}'. Expected 'anthropic' or 'openai'."
        )

    anthropic_model = model_override if (model_override and provider == "anthropic") else os.getenv(
        "HARNESS_ANTHROPIC_MODEL", "claude-sonnet-4-6"
    )
    openai_model = model_override if (model_override and provider == "openai") else os.getenv(
        "HARNESS_OPENAI_MODEL", "gpt-4o"
    )

    return Config(
        provider=provider,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        anthropic_model=anthropic_model,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=openai_model,
        max_tokens=int(os.getenv("HARNESS_MAX_TOKENS", "4096")),
    )
