import os

import pytest

from agent.config import load_config


def test_default_provider_is_anthropic(monkeypatch):
    monkeypatch.delenv("HARNESS_PROVIDER", raising=False)
    config = load_config()
    assert config.provider == "anthropic"


def test_provider_override():
    config = load_config(provider_override="openai")
    assert config.provider == "openai"
    assert config.active_model == config.openai_model


def test_invalid_provider_raises():
    with pytest.raises(ValueError):
        load_config(provider_override="not-a-real-provider")


def test_model_override_only_applies_to_selected_provider():
    config = load_config(provider_override="anthropic", model_override="custom-model")
    assert config.anthropic_model == "custom-model"
    assert config.active_model == "custom-model"
