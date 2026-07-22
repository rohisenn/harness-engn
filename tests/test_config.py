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


def test_config_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("HARNESS_COLOR", raising=False)
    config = load_config()
    assert config.color is True

    monkeypatch.setenv("NO_COLOR", "1")
    config = load_config()
    assert config.color is False

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("HARNESS_COLOR", "false")
    config = load_config()
    assert config.color is False


def test_config_git_integration(monkeypatch):
    monkeypatch.delenv("HARNESS_GIT_INTEGRATION", raising=False)
    monkeypatch.delenv("HARNESS_GIT_BRANCH_PREFIX", raising=False)
    
    config = load_config()
    assert config.git_integration is False
    assert config.git_branch_prefix == "harness/"

    monkeypatch.setenv("HARNESS_GIT_INTEGRATION", "true")
    monkeypatch.setenv("HARNESS_GIT_BRANCH_PREFIX", "test-prefix/")
    config = load_config()
    assert config.git_integration is True
    assert config.git_branch_prefix == "test-prefix/"

    # Test overrides
    config = load_config(git_integration_override=False, git_branch_prefix_override="override/")
    assert config.git_integration is False
    assert config.git_branch_prefix == "override/"


