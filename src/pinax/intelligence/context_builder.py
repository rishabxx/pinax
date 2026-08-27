"""Builds the AI prompt from `ReadingContext` (brief §25/§26/§40) — the only place that
decides what the model sees. Never called on scroll (brief §73); only when a question is
actually submitted, using a snapshot of the reading context at that moment.

Token-budget aware (brief §40): each tier gets a character budget (a plain len//4 estimate —
not a real tokenizer, not worth a dependency for a soft budget), and higher-priority tiers
(selected text, visible content) are never dropped, only truncated if they somehow exceed
their own slice.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from ..app.state import ReadingContext
from ..documents.models import Document
from .prompts import SYSTEM_PROMPT
from .providers.base import Message


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class ContextBudget:
    selected_text: int = 4_000
    visible_content: int = 5_000
    neighboring_context: int = 2_000
    retrieval: int = 6_000
    history: int = 1_000


@dataclass
class ContextTier:
    name: str
    included: bool
    tokens: int
    detail: str = ""


@dataclass
class PromptContext:
    messages: list[Message]
    tiers: list[ContextTier] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return sum(t.tokens for t in self.tiers if t.included)


def _truncate(text: str, budget_tokens: int) -> str:
    max_chars = budget_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + " …"


def _resolve_text(document: Document, block_ids: list[str]) -> str:
    parts = []
    for block_id in block_ids:
        block = document.block_by_id(block_id)
        if block and block.text:
            parts.append(block.text)
    return "\n\n".join(parts)


def build_context(
    *,
    question: str,
    document: Document,
    reading_context: ReadingContext,
    conn: sqlite3.Connection,
    history: list[tuple[str, str]],
    budget: ContextBudget = ContextBudget(),
    explanation_level: str = "intermediate",
) -> PromptContext:
    from ..search.lexical import search as lexical_search

    tiers: list[ContextTier] = []
    parts: list[str] = [f"DOCUMENT\n{document.title}"]

    section = document.section_by_id(reading_context.current_section_id) if reading_context.current_section_id else None
    location_lines = ["CURRENT LOCATION"]
    if section:
        location_lines.append(f"Section: {section.title}")
    if reading_context.current_page:
        location_lines.append(f"Source page: {reading_context.current_page}" + (f" / {document.page_count}" if document.page_count else ""))
    parts.append("\n".join(location_lines))

    # 1. Selected text — highest priority, never dropped if present.
    selected_text = _resolve_text(document, reading_context.selected_block_ids)
    if selected_text:
        selected_text = _truncate(selected_text, budget.selected_text)
        parts.append(f"SELECTED TEXT\n{selected_text}")
        tiers.append(ContextTier("selected_text", True, estimate_tokens(selected_text)))
    else:
        tiers.append(ContextTier("selected_text", False, 0))

    # 2. Currently visible blocks.
    visible_text = _resolve_text(document, reading_context.visible_block_ids)
    if visible_text:
        visible_text = _truncate(visible_text, budget.visible_content)
        parts.append(f"CURRENTLY VISIBLE CONTENT\n{visible_text}")
        tiers.append(ContextTier("visible_blocks", True, estimate_tokens(visible_text)))
    else:
        tiers.append(ContextTier("visible_blocks", False, 0))

    # 3. Nearby blocks (immediately before/after what's visible).
    prev_text = _resolve_text(document, reading_context.previous_block_ids)
    next_text = _resolve_text(document, reading_context.next_block_ids)
    nearby_sections = []
    if prev_text:
        nearby_sections.append(f"Preceding:\n{prev_text}")
    if next_text:
        nearby_sections.append(f"Following:\n{next_text}")
    nearby_text = "\n\n".join(nearby_sections)
    if nearby_text:
        nearby_text = _truncate(nearby_text, budget.neighboring_context)
        parts.append(f"NEARBY CONTEXT\n{nearby_text}")
        tiers.append(ContextTier("nearby_blocks", True, estimate_tokens(nearby_text)))
    else:
        tiers.append(ContextTier("nearby_blocks", False, 0))

    # 4. Retrieved chunks from elsewhere in the document (brief §26 "RELATED DOCUMENT CONTEXT").
    exclude_ids = (
        set(reading_context.visible_block_ids) | set(reading_context.previous_block_ids) | set(reading_context.next_block_ids)
    )
    try:
        results = lexical_search(conn, document.id, question, limit=6)
    except Exception:
        results = []
    fresh = [r for r in results if r.block_id not in exclude_ids]
    if fresh:
        chunk_texts = []
        for r in fresh:
            label = f"[p.{r.page}] " if r.page else ""
            heading = f"{r.section_title} " if r.section_title else ""
            chunk_texts.append(f"{label}{heading}\n{r.snippet}".strip())
        retrieved_text = _truncate("\n\n".join(chunk_texts), budget.retrieval)
        parts.append(f"RELEVANT DOCUMENT CONTEXT\n{retrieved_text}")
        tiers.append(ContextTier("retrieved_chunks", True, estimate_tokens(retrieved_text), detail=f"{len(fresh)} chunks"))
    else:
        tiers.append(ContextTier("retrieved_chunks", False, 0))

    # 5. Conversation history — most recent turns that fit the budget, oldest dropped first.
    history_entries: list[str] = []
    remaining = budget.history
    for q, a in reversed(history):
        entry = f"Q: {q}\nA: {a}"
        entry_tokens = estimate_tokens(entry)
        if entry_tokens > remaining:
            break
        history_entries.insert(0, entry)
        remaining -= entry_tokens
    if history_entries:
        history_text = "\n\n".join(history_entries)
        parts.append(f"CONVERSATION HISTORY\n{history_text}")
        tiers.append(ContextTier("history", True, estimate_tokens(history_text)))
    else:
        tiers.append(ContextTier("history", False, 0))

    context_block = "\n\n".join(parts)
    messages = [
        Message(role="system", content=SYSTEM_PROMPT.format(explanation_level=explanation_level)),
        Message(role="user", content=f"{context_block}\n\nQUESTION\n{question}"),
    ]
    return PromptContext(messages=messages, tiers=tiers)


__all__ = ["build_context", "ContextBudget", "ContextTier", "PromptContext", "estimate_tokens"]
