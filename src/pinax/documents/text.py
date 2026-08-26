"""Plain text (.txt) parser."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from .models import Document, DocumentBlock, DocumentMetadata
from .normalization import (
    build_sections_from_headings,
    clean_text,
    file_hash,
    guess_title_from_filename,
    new_id,
)

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def parse(path: str) -> Document:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    text = clean_text(raw)
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]

    blocks: list[DocumentBlock] = []
    for order, para in enumerate(paragraphs):
        blocks.append(
            DocumentBlock(id=new_id("blk"), type="paragraph", text=para, order=order)
        )

    sections = build_sections_from_headings(blocks)
    stat = os.stat(path)

    return Document(
        id=new_id("doc"),
        path=str(path),
        title=guess_title_from_filename(path),
        metadata=DocumentMetadata(
            format="txt",
            file_hash=file_hash(path),
            file_size=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        ),
        sections=sections,
        blocks=blocks,
        page_count=None,
    )
