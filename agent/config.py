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
    gemini_api_key: str | None
    gemini_model: str
    groq_api_key: str | None
    groq_model: str
    max_tokens: int

    @property
    def active_model(self) -> str:
        if self.provider == "gemini":
            return self.gemini_model
        elif self.provider in ("groq", "grok"):
            return self.groq_model
        return ""

    @property
    def active_api_key(self) -> str | None:
        if self.provider == "gemini":
            return self.gemini_api_key
        elif self.provider in ("groq", "grok"):
            return self.groq_api_key
        return None


def load_config(provider_override: str | None = None, model_override: str | None = None) -> Config:
    provider = (provider_override or os.getenv("HARNESS_PROVIDER", "gemini")).lower()

    if provider not in ("gemini", "groq", "grok"):
        raise ValueError(
            f"Unknown provider '{provider}'. Expected 'gemini', 'groq', or 'grok'."
        )

    gemini_model = model_override if (model_override and provider == "gemini") else os.getenv(
        "HARNESS_GEMINI_MODEL", "gemini-3.5-flash"
    )
    groq_model = model_override if (model_override and provider in ("groq", "grok")) else os.getenv(
        "HARNESS_GROQ_MODEL", os.getenv("HARNESS_GROK_MODEL", "llama-3.3-70b-versatile")
    )

    return Config(
        provider=provider,
        gemini_api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"),
        gemini_model=gemini_model,
        groq_api_key=os.getenv("GROK_API_KEY") or os.getenv("GROQ_API_KEY"),
        groq_model=groq_model,
        max_tokens=int(os.getenv("HARNESS_MAX_TOKENS", "4096")),
    )
