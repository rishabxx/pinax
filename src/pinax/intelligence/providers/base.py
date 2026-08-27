"""The provider abstraction (brief §34) — the UI and context builder only ever depend on
this Protocol, never on a concrete SDK. Adding a fifth provider means adding one adapter
here; nothing else in the app changes.
"""

from __future__ import annotations

from typing import AsyncIterator, Literal, Protocol

from pydantic import BaseModel

Role = Literal["system", "user", "assistant"]


class Message(BaseModel):
    role: Role
    content: str


class ProviderError(Exception):
    """Raised when a provider request fails (network, auth, bad model name, …) — the AI
    panel catches this and shows a clean message instead of a raw traceback (brief §63)."""


class LLMProvider(Protocol):
    async def chat(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream a chat completion as it's generated, one text chunk at a time."""
        ...


__all__ = ["Message", "Role", "LLMProvider", "ProviderError"]
