"""Anthropic provider. Anthropic's API takes the system prompt as a separate parameter
rather than a message with role="system", so that message (if present) is split out."""

from __future__ import annotations

from typing import AsyncIterator

from .base import Message, ProviderError


class AnthropicProvider:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError as exc:
                raise ProviderError("The 'anthropic' package is not installed.") from exc
            kwargs = {"api_key": self._api_key} if self._api_key else {}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncAnthropic(**kwargs)
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
        system = "\n\n".join(m.content for m in messages if m.role == "system") or None
        conversation = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]

        try:
            async with client.messages.stream(
                model=model,
                system=system or "",
                messages=conversation,
                temperature=temperature,
                max_tokens=max_tokens or 4096,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            raise ProviderError(f"Anthropic request failed: {exc}") from exc


__all__ = ["AnthropicProvider"]
