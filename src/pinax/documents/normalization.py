"""Shared helpers used by every format-specific parser.

Kept format-agnostic on purpose: pdf.py/docx.py/epub.py/markdown.py/text.py all lean on
these instead of re-implementing whitespace cleanup or id generation.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid

_WHITESPACE_RUN = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_NUMBERED_HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+\S")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def clean_text(text: str) -> str:
    """Normalize whitespace/unicode without destroying intentional line breaks."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE_RUN.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def numbering_depth(text: str) -> int | None:
    """Infer a heading's nesting level from a leading numbering pattern like '3.2.1'."""
    match = _NUMBERED_HEADING.match(text)
    if not match:
        return None
    return match.group(1).count(".") + 1


def guess_title_from_filename(path: str) -> str:
    from pathlib import Path

    stem = Path(path).stem
    stem = re.sub(r"[_-]+", " ", stem)
    return stem.strip().title() if stem else "Untitled"


def build_sections_from_headings(blocks: list) -> list:
    """Derive a Section tree from HEADING blocks in reading order.

    Mutates each block's `section_id` in place and returns the sections, each carrying
    its own `block_ids` (heading block included). Blocks before the first heading are
    grouped into an implicit root section. Shared by every parser so TOC generation is
    identical regardless of source format.
    """
    from .models import BlockType, Section

    sections: list[Section] = []
    stack: list[Section] = []  # open sections by level, for parent linkage
    current: Section | None = None
    order = 0

    def open_root() -> Section:
        nonlocal order
        root = Section(id=new_id("sec"), title="", level=0, order=order)
        order += 1
        sections.append(root)
        return root

    for block in blocks:
        if block.type == BlockType.HEADING:
            level = block.level or 1
            while stack and stack[-1].level >= level:
                stack.pop()
            parent = stack[-1] if stack else None
            section = Section(
                id=new_id("sec"),
                title=block.text.strip(),
                level=level,
                order=order,
                parent_id=parent.id if parent else None,
                source_page_start=block.source_page,
            )
            order += 1
            sections.append(section)
            stack.append(section)
            current = section
        elif current is None:
            current = open_root()
            stack.append(current)

        block.section_id = current.id
        current.block_ids.append(block.id)
        if block.source_page is not None:
            if current.source_page_start is None:
                current.source_page_start = block.source_page
            current.source_page_end = block.source_page

    return sections
