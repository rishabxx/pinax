"""Provider factory — the only place that knows how to turn `AIConfig` into a concrete
`LLMProvider`. API keys come from environment variables only, never from config.toml or
source (brief §34/§65): a `PINAX_*_API_KEY` override takes precedence over the provider's
standard env var, for people who want a key scoped to this tool specifically.
"""

from __future__ import annotations

import os

from ...config.models import AIConfig
from .anthropic import AnthropicProvider
from .base import LLMProvider, Message, ProviderError, Role
from .compatible import CompatibleProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider


def get_provider(config: AIConfig) -> LLMProvider:
    if config.provider == "openai":
        key = os.environ.get("PINAX_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ProviderError("No OpenAI API key found. Set the OPENAI_API_KEY environment variable.")
        return OpenAIProvider(api_key=key, base_url=config.base_url)

    if config.provider == "anthropic":
        key = os.environ.get("PINAX_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError("No Anthropic API key found. Set the ANTHROPIC_API_KEY environment variable.")
        return AnthropicProvider(api_key=key, base_url=config.base_url)

    if config.provider == "ollama":
        return OllamaProvider(base_url=config.base_url)

    if config.provider == "compatible":
        key = os.environ.get("PINAX_COMPATIBLE_API_KEY")
        return CompatibleProvider(base_url=config.base_url, api_key=key)

    raise ProviderError(f"Unknown AI provider: {config.provider!r}")


__all__ = [
    "get_provider",
    "LLMProvider",
    "Message",
    "Role",
    "ProviderError",
    "OpenAIProvider",
    "AnthropicProvider",
    "OllamaProvider",
    "CompatibleProvider",
]
