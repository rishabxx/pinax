"""Structure-respecting chunking.

Chunks never split a block, and prefer to break on section boundaries — never a blind
every-N-characters cut (brief §37). Used today by `search/lexical.py` to index at a coarser,
more search-relevant granularity than single blocks; Phase 3's semantic retrieval reuses the
same chunks for embeddings.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .models import BlockType, Document, Section
from .normalization import new_id

DEFAULT_MAX_CHARS = 4800  # ~ 900-1200 tokens for English prose


class Chunk(BaseModel):
    id: str
    document_id: str
    text: str
    section_id: str | None = None
    source_pages: list[int] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)
    heading_path: list[str] = Field(default_factory=list)


def _heading_path(document: Document, section_id: str | None) -> list[str]:
    path: list[str] = []
    seen: set[str] = set()
    current: Section | None = document.section_by_id(section_id) if section_id else None
    while current is not None and current.id not in seen:
        seen.add(current.id)
        if current.title:
            path.append(current.title)
        current = document.section_by_id(current.parent_id) if current.parent_id else None
    return list(reversed(path))


def chunk_document(document: Document, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []

    sections = document.sections or [None]  # type: ignore[list-item]
    for section in sections:
        section_id = section.id if section else None
        blocks = document.blocks_for_section(section_id) if section else document.blocks
        heading_path = _heading_path(document, section_id)

        buf_text: list[str] = []
        buf_pages: set[int] = set()
        buf_block_ids: list[str] = []
        buf_len = 0

        def flush() -> None:
            nonlocal buf_text, buf_pages, buf_block_ids, buf_len
            if not buf_text:
                return
            chunks.append(
                Chunk(
                    id=new_id("chk"),
                    document_id=document.id,
                    text="\n\n".join(buf_text).strip(),
                    section_id=section_id,
                    source_pages=sorted(buf_pages),
                    block_ids=list(buf_block_ids),
                    heading_path=list(heading_path),
                )
            )
            buf_text, buf_pages, buf_block_ids, buf_len = [], set(), [], 0

        for block in blocks:
            if block.type == BlockType.PAGE_BREAK or not block.text:
                continue
            piece = block.text
            if buf_len + len(piece) > max_chars and buf_text:
                flush()
            buf_text.append(piece)
            buf_block_ids.append(block.id)
            buf_len += len(piece)
            if block.source_page is not None:
                buf_pages.add(block.source_page)

        flush()

    return chunks
