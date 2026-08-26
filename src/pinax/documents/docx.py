"""DOCX parser, built on python-docx.

Uses heading *styles* directly for section structure (brief §16) rather than any
font-size heuristic — DOCX headings are unambiguous, unlike PDF.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

import docx
from docx.document import Document as _WordDocument
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table as _Table
from docx.text.paragraph import Paragraph as _Paragraph

from .models import BlockType, Document, DocumentBlock, DocumentMetadata
from .normalization import build_sections_from_headings, file_hash, new_id

_HEADING_RE = re.compile(r"^Heading\s*(\d+)$", re.IGNORECASE)


def _iter_block_items(parent):
    parent_elm = parent.element.body if isinstance(parent, _WordDocument) else parent._element
    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield _Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield _Table(child, parent)


def _heading_level(paragraph: _Paragraph) -> int | None:
    style_name = paragraph.style.name if paragraph.style else ""
    if style_name.lower() == "title":
        return 1
    match = _HEADING_RE.match(style_name or "")
    return int(match.group(1)) if match else None


def _has_image(paragraph: _Paragraph) -> bool:
    return bool(paragraph._element.findall(f".//{qn('w:drawing')}"))


def parse(path: str) -> Document:
    document = docx.Document(path)
    blocks: list[DocumentBlock] = []
    order = 0

    for item in _iter_block_items(document):
        if isinstance(item, _Paragraph):
            text = item.text.strip()
            style_name = (item.style.name if item.style else "") or ""
            level = _heading_level(item)

            if level is not None and text:
                blocks.append(
                    DocumentBlock(id=new_id("blk"), type=BlockType.HEADING, text=text, order=order, level=level)
                )
                order += 1
            elif "list" in style_name.lower() and text:
                numbering = item._element.find(f".//{qn('w:numPr')}/{qn('w:ilvl')}")
                depth = int(numbering.get(qn("w:val"))) if numbering is not None else 0
                blocks.append(
                    DocumentBlock(
                        id=new_id("blk"),
                        type=BlockType.LIST_ITEM,
                        text=text,
                        order=order,
                        level=depth,
                        metadata={"ordered": "number" in style_name.lower()},
                    )
                )
                order += 1
            elif "quote" in style_name.lower() and text:
                blocks.append(
                    DocumentBlock(id=new_id("blk"), type=BlockType.QUOTE, text=text, order=order)
                )
                order += 1
            elif "code" in style_name.lower() and text:
                blocks.append(
                    DocumentBlock(id=new_id("blk"), type=BlockType.CODE, text=text, order=order)
                )
                order += 1
            elif text:
                blocks.append(
                    DocumentBlock(id=new_id("blk"), type=BlockType.PARAGRAPH, text=text, order=order)
                )
                order += 1
            elif _has_image(item):
                blocks.append(
                    DocumentBlock(id=new_id("blk"), type=BlockType.IMAGE, text="", order=order)
                )
                order += 1
        elif isinstance(item, _Table):
            rows = [[cell.text.strip() for cell in row.cells] for row in item.rows]
            headers = rows[0] if rows else []
            body = rows[1:] if len(rows) > 1 else []
            preview = " | ".join(headers) + "\n" + "\n".join(" | ".join(r) for r in body)
            blocks.append(
                DocumentBlock(
                    id=new_id("blk"),
                    type=BlockType.TABLE,
                    text=preview,
                    order=order,
                    metadata={"headers": headers, "rows": body},
                )
            )
            order += 1

    sections = build_sections_from_headings(blocks)

    core_props = document.core_properties
    title = core_props.title or None
    if not title:
        first_heading = next((b for b in blocks if b.type == BlockType.HEADING), None)
        title = first_heading.text if first_heading else _title_from_filename(path)

    stat = os.stat(path)
    return Document(
        id=new_id("doc"),
        path=str(path),
        title=title,
        metadata=DocumentMetadata(
            author=core_props.author or None,
            format="docx",
            file_hash=file_hash(path),
            file_size=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        ),
        sections=sections,
        blocks=blocks,
        page_count=None,
    )


def _title_from_filename(path: str) -> str:
    from .normalization import guess_title_from_filename

    return guess_title_from_filename(path)
