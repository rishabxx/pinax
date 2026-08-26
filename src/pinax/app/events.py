"""Semantic events (brief §72).

Widgets post these instead of screens reaching into each other's internals. Only the
events Phase 1 actually raises are defined here; the AI-era events (`AIQuestionSubmitted`,
`CitationActivated`, ...) are added alongside the code that raises/handles them in Phase 2
rather than declared empty ahead of time.
"""

from __future__ import annotations

from textual.message import Message


class LocationChanged(Message):
    """The reader's current block/page/section changed (from scrolling or navigation)."""

    def __init__(self, block_id: str | None, page: int | None, section_id: str | None) -> None:
        super().__init__()
        self.block_id = block_id
        self.page = page
        self.section_id = section_id


class SectionChanged(Message):
    """The dominant visible section changed — distinct from LocationChanged so the TOC
    only needs to re-highlight, not re-render, on ordinary within-section scrolling."""

    def __init__(self, section_id: str | None) -> None:
        super().__init__()
        self.section_id = section_id


class BookmarkCreated(Message):
    def __init__(self, bookmark_id: str) -> None:
        super().__init__()
        self.bookmark_id = bookmark_id


class SearchExecuted(Message):
    def __init__(self, query: str, result_count: int) -> None:
        super().__init__()
        self.query = query
        self.result_count = result_count


class TOCJumpRequested(Message):
    def __init__(self, section_id: str) -> None:
        super().__init__()
        self.section_id = section_id


class SearchResultSelected(Message):
    def __init__(self, block_id: str | None, page: int | None) -> None:
        super().__init__()
        self.block_id = block_id
        self.page = page
