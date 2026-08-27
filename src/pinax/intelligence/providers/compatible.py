"""Any OpenAI-compatible endpoint (LM Studio, vLLM, OpenRouter, a self-hosted proxy, …) —
the wire format is identical to OpenAI's, so this is a thin, explicit alias rather than a
copy: it exists so `provider = "compatible"` in config reads clearly and a missing
`base_url` fails with a specific message instead of silently hitting api.openai.com.
"""

from __future__ import annotations

from .base import ProviderError
from .openai import OpenAIProvider


class CompatibleProvider(OpenAIProvider):
    def __init__(self, base_url: str | None, api_key: str | None = None) -> None:
        if not base_url:
            raise ProviderError("provider = \"compatible\" requires ai.base_url to be set in config.toml.")
        super().__init__(api_key=api_key, base_url=base_url)


__all__ = ["CompatibleProvider"]
