"""Ollama provider — talks to a local Ollama server over its REST API. No API key, no
network egress by default (brief §65: local mode keeps document content on-machine)."""

from __future__ import annotations

import json
from typing import AsyncIterator

from .base import Message, ProviderError

DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider:
    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        import httpx

        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {"temperature": temperature, **({"num_predict": max_tokens} if max_tokens else {})},
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", f"{self._base_url}/api/chat", json=payload) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        raise ProviderError(f"Ollama returned {response.status_code}: {body.decode(errors='replace')}")
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content")
                        if content:
                            yield content
                        if chunk.get("done"):
                            break
        except ProviderError:
            raise
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Could not reach Ollama at {self._base_url} — is `ollama serve` running?"
            ) from exc
        except Exception as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc


__all__ = ["OllamaProvider", "DEFAULT_BASE_URL"]
