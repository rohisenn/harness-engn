import sys
from unittest.mock import MagicMock, patch

# Dynamically mock modules that might not be installed in the environment to avoid ModuleNotFoundError
mock_openai_module = MagicMock()
mock_genai_module = MagicMock()

sys.modules['openai'] = mock_openai_module

mock_google = MagicMock()
mock_google.genai = mock_genai_module
sys.modules['google'] = mock_google
sys.modules['google.genai'] = mock_genai_module

# Set up mock types that retain properties passed to constructor
class MockGenerateContentConfig:
    def __init__(self, system_instruction=None, max_output_tokens=None, **kwargs):
        self.system_instruction = system_instruction
        self.max_output_tokens = max_output_tokens

mock_genai_module.types.GenerateContentConfig = MockGenerateContentConfig
mock_genai_module.types.Content = MagicMock()
mock_genai_module.types.Part = MagicMock()


import pytest
from agent.config import Config
from agent.llm import LLMClient, LLMError


def test_build_client_gemini():
    config = Config(
        provider="gemini",
        gemini_api_key="fake-gemini-key",
        gemini_model="gemini-3.5-flash",
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
    )
    
    mock_genai_module.Client = MagicMock()
    
    client = LLMClient(config)
    mock_genai_module.Client.assert_called_once_with(api_key="fake-gemini-key")
    assert client.config == config


def test_build_client_groq():
    config = Config(
        provider="groq",
        gemini_api_key=None,
        gemini_model="gemini-3.5-flash",
        groq_api_key="fake-groq-key",
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
    )
    
    mock_openai_module.OpenAI = MagicMock()
    
    client = LLMClient(config)
    mock_openai_module.OpenAI.assert_called_once_with(
        api_key="fake-groq-key",
        base_url="https://api.groq.com/openai/v1"
    )
    assert client.config == config


def test_build_client_missing_keys():
    config_gemini = Config(
        provider="gemini",
        gemini_api_key=None,
        gemini_model="gemini-3.5-flash",
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
    )
    with pytest.raises(LLMError, match="GOOGLE_API_KEY.*is not set"):
        LLMClient(config_gemini)

    config_groq = Config(
        provider="groq",
        gemini_api_key=None,
        gemini_model="gemini-3.5-flash",
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
    )
    with pytest.raises(LLMError, match="GROK_API_KEY.*is not set"):
        LLMClient(config_groq)


def test_stream_gemini():
    config = Config(
        provider="gemini",
        gemini_api_key="fake-key",
        gemini_model="gemini-3.5-flash",
        groq_api_key=None,
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
    )
    
    mock_client = MagicMock()
    mock_genai_module.Client.return_value = mock_client
    
    client = LLMClient(config)
    
    # Mock models.generate_content_stream to return an iterator of chunks
    mock_chunk_1 = MagicMock()
    mock_chunk_1.text = "Hello"
    
    mock_chunk_2 = MagicMock()
    mock_chunk_2.text = " world"
    
    mock_chunk_3 = MagicMock()
    mock_chunk_3.text = "!"
    
    mock_client.models.generate_content_stream.return_value = [mock_chunk_1, mock_chunk_2, mock_chunk_3]
    
    chunks = list(client.stream(system="sys-prompt", messages=[{"role": "user", "content": "hi"}]))
    
    assert chunks == ["Hello", " world", "!"]
    
    # Verify Content & Config mock calls
    mock_client.models.generate_content_stream.assert_called_once()
    call_args, call_kwargs = mock_client.models.generate_content_stream.call_args
    assert call_kwargs["model"] == "gemini-3.5-flash"
    assert call_kwargs["config"].system_instruction == "sys-prompt"
    assert call_kwargs["config"].max_output_tokens == 4096


def test_stream_groq():
    config = Config(
        provider="groq",
        gemini_api_key=None,
        gemini_model="gemini-3.5-flash",
        groq_api_key="fake-key",
        groq_model="llama-3.3-70b-versatile",
        max_tokens=4096,
    )
    
    mock_client = MagicMock()
    mock_openai_module.OpenAI.return_value = mock_client
    
    client = LLMClient(config)
    
    # Mock chat.completions.create to return an iterator of chunks
    mock_chunk_1 = MagicMock()
    mock_chunk_1.choices = [MagicMock()]
    mock_chunk_1.choices[0].delta.content = "Hello"
    
    mock_chunk_2 = MagicMock()
    mock_chunk_2.choices = [MagicMock()]
    mock_chunk_2.choices[0].delta.content = " world"
    
    mock_chunk_empty_choices = MagicMock()
    mock_chunk_empty_choices.choices = []
    
    mock_chunk_3 = MagicMock()
    mock_chunk_3.choices = [MagicMock()]
    mock_chunk_3.choices[0].delta.content = "!"
    
    # Mock stream manager
    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__.return_value = [mock_chunk_1, mock_chunk_2, mock_chunk_empty_choices, mock_chunk_3]
    mock_client.chat.completions.create.return_value = mock_stream_ctx
    
    chunks = list(client.stream(system="sys-prompt", messages=[{"role": "user", "content": "hi"}]))
    
    assert chunks == ["Hello", " world", "!"]
    mock_client.chat.completions.create.assert_called_once_with(
        model="llama-3.3-70b-versatile",
        max_tokens=4096,
        messages=[
            {"role": "system", "content": "sys-prompt"},
            {"role": "user", "content": "hi"}
        ],
        stream=True,
    )
