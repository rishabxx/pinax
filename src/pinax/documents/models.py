"""The normalized document model.

Every parser (pdf.py, docx.py, markdown.py, text.py, epub.py) produces a `Document`.
Every UI widget consumes only a `Document` — never a format-specific object.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    LIST_ITEM = "list_item"
    CODE = "code"
    QUOTE = "quote"
    TABLE = "table"
    IMAGE = "image"
    CAPTION = "caption"
    FOOTNOTE = "footnote"
    EQUATION = "equation"
    PAGE_BREAK = "page_break"


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class DocumentBlock(BaseModel):
    id: str
    type: BlockType
    text: str
    source_page: int | None = None
    section_id: str | None = None
    order: int
    level: int | None = None
    bbox: BoundingBox | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Section(BaseModel):
    id: str
    title: str
    level: int
    order: int
    parent_id: str | None = None
    block_ids: list[str] = Field(default_factory=list)
    source_page_start: int | None = None
    source_page_end: int | None = None


class DocumentMetadata(BaseModel):
    author: str | None = None
    producer: str | None = None
    format: str
    language: str | None = None
    file_hash: str
    file_size: int
    created_at: datetime | None = None


class Document(BaseModel):
    id: str
    path: str
    title: str
    metadata: DocumentMetadata
    sections: list[Section] = Field(default_factory=list)
    blocks: list[DocumentBlock] = Field(default_factory=list)
    page_count: int | None = None

    _block_index_cache: dict[str, DocumentBlock] | None = PrivateAttr(default=None)
    _section_index_cache: dict[str, Section] | None = PrivateAttr(default=None)

    def block_by_id(self, block_id: str) -> DocumentBlock | None:
        return self._block_index().get(block_id)

    def section_by_id(self, section_id: str) -> Section | None:
        return self._section_index().get(section_id)

    def blocks_for_section(self, section_id: str) -> list[DocumentBlock]:
        section = self.section_by_id(section_id)
        if section is None:
            return []
        index = self._block_index()
        return [index[bid] for bid in section.block_ids if bid in index]

    def _block_index(self) -> dict[str, DocumentBlock]:
        if self._block_index_cache is None:
            self._block_index_cache = {b.id: b for b in self.blocks}
        return self._block_index_cache

    def _section_index(self) -> dict[str, Section]:
        if self._section_index_cache is None:
            self._section_index_cache = {s.id: s for s in self.sections}
        return self._section_index_cache
