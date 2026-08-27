"""OpenAI provider — also the base for any OpenAI-compatible endpoint (brief §31), since the
only difference is `base_url`/`api_key`."""

from __future__ import annotations

from typing import AsyncIterator

from .base import Message, ProviderError


class OpenAIProvider:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise ProviderError("The 'openai' package is not installed.") from exc
            self._client = AsyncOpenAI(api_key=self._api_key or "not-needed", base_url=self._base_url)
        return self._client

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:
            raise ProviderError(f"OpenAI request failed: {exc}") from exc


__all__ = ["OpenAIProvider"]
