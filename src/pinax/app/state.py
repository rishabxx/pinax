"""Reader state machine (brief §71) and the ReadingContext (brief §24).

`AppMode` drives keybinding dispatch so screens don't grow one giant conditional. Every
mode gets its own handler; `ReaderScreen` looks up the active mode to decide which handler
runs for a keypress.

`ReadingContext` is intentionally a plain mutable object, not rebuilt from a query on every
frame — cheap to update on scroll, and it is the only thing Phase 2's AI context builder will
ever read (brief §73: scrolling must never itself trigger an LLM call).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AppMode(str, Enum):
    READING = "reading"
    SEARCH = "search"
    AI = "ai"
    COMMAND_PALETTE = "command_palette"
    TOC = "toc"
    SELECTION = "selection"
    ANNOTATION = "annotation"
    HELP = "help"
    LIBRARY = "library"


class ReaderViewMode(str, Enum):
    REFLOW = "reflow"
    SOURCE_PAGE = "source_page"


@dataclass
class ReadingContext:
    document_id: str
    current_page: int | None = None
    current_section_id: str | None = None
    visible_block_ids: list[str] = field(default_factory=list)
    cursor_block_id: str | None = None
    selected_block_ids: list[str] = field(default_factory=list)
    scroll_position: float = 0.0
    previous_block_ids: list[str] = field(default_factory=list)
    next_block_ids: list[str] = field(default_factory=list)
