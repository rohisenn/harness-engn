import os

import pytest

from agent.config import load_config


def test_default_provider_is_gemini(monkeypatch):
    monkeypatch.delenv("HARNESS_PROVIDER", raising=False)
    config = load_config()
    assert config.provider == "gemini"


def test_provider_override():
    config = load_config(provider_override="gemini")
    assert config.provider == "gemini"
    assert config.active_model == config.gemini_model

    config = load_config(provider_override="groq")
    assert config.provider == "groq"
    assert config.active_model == config.groq_model

    config = load_config(provider_override="grok")
    assert config.provider == "grok"
    assert config.active_model == config.groq_model


def test_invalid_provider_raises():
    with pytest.raises(ValueError):
        load_config(provider_override="not-a-real-provider")


def test_model_override_only_applies_to_selected_provider():
    config = load_config(provider_override="gemini", model_override="custom-gemini-model")
    assert config.gemini_model == "custom-gemini-model"
    assert config.active_model == "custom-gemini-model"
