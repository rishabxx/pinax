"""Provider tests. No real network calls — the Ollama provider is tested against a mocked
httpx transport (its NDJSON stream-parsing is the one bit of custom protocol logic here);
OpenAI/Anthropic are official SDKs, so we only verify our error-wrapping and factory wiring.
"""

from __future__ import annotations

import json

import pytest

from pinax.config.models import AIConfig
from pinax.intelligence.providers import get_provider
from pinax.intelligence.providers.base import Message, ProviderError
from pinax.intelligence.providers.ollama import OllamaProvider


async def _collect(agen):
    return "".join([chunk async for chunk in agen])


async def test_ollama_provider_streams_ndjson_chunks():
    import httpx

    lines = [
        json.dumps({"message": {"content": "Hello"}, "done": False}),
        json.dumps({"message": {"content": ", world"}, "done": False}),
        json.dumps({"message": {"content": "!"}, "done": True}),
    ]
    body = "\n".join(lines).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    provider = OllamaProvider(base_url="http://fake-ollama:11434")
    transport = httpx.MockTransport(handler)

    original_client = httpx.AsyncClient
    httpx.AsyncClient = lambda *a, **kw: original_client(*a, transport=transport, **kw)
    try:
        result = await _collect(provider.chat([Message(role="user", content="hi")], model="llama3.1"))
    finally:
        httpx.AsyncClient = original_client

    assert result == "Hello, world!"


async def test_ollama_provider_raises_clean_error_on_non_200():
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"internal error")

    provider = OllamaProvider(base_url="http://fake-ollama:11434")
    transport = httpx.MockTransport(handler)

    original_client = httpx.AsyncClient
    httpx.AsyncClient = lambda *a, **kw: original_client(*a, transport=transport, **kw)
    try:
        with pytest.raises(ProviderError):
            await _collect(provider.chat([Message(role="user", content="hi")], model="llama3.1"))
    finally:
        httpx.AsyncClient = original_client


async def test_ollama_provider_connect_error_message_is_actionable():
    provider = OllamaProvider(base_url="http://127.0.0.1:1")  # nothing listens here
    with pytest.raises(ProviderError, match="ollama serve"):
        await _collect(provider.chat([Message(role="user", content="hi")], model="llama3.1"))


def test_factory_dispatches_ollama_without_api_key():
    provider = get_provider(AIConfig(provider="ollama"))
    assert isinstance(provider, OllamaProvider)


def test_factory_requires_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PINAX_OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        get_provider(AIConfig(provider="openai", model="gpt-4o-mini"))


def test_factory_uses_pinax_prefixed_key_override(monkeypatch):
    monkeypatch.setenv("PINAX_OPENAI_API_KEY", "sk-test-123")
    provider = get_provider(AIConfig(provider="openai", model="gpt-4o-mini"))
    assert provider._api_key == "sk-test-123"


def test_factory_requires_base_url_for_compatible():
    with pytest.raises(ProviderError, match="base_url"):
        get_provider(AIConfig(provider="compatible", model="local-model"))
