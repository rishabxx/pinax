"""DocumentBlock -> Rich renderable.

Pure functions only: no Textual imports here, so this stays trivially unit-testable and
keeps the "widgets don't know how parsing works" boundary honest in the other direction too
— rendering doesn't reach back into `documents.parser`.
"""

from __future__ import annotations

import re

from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from ..documents.models import BlockType, DocumentBlock
from .themes import Theme

_NARROW_TABLE_THRESHOLD = 3  # columns beyond which a narrow reader column stacks records
_HEADING_NUMBER_RE = re.compile(r"^(\d+(?:\.\d+)*\.?)\s+(.+)$")


def css_class_for(block: DocumentBlock) -> str:
    """CSS class assigned to the mounted widget so `reader_view.py` can give each block
    type its own margin (extra breathing room above headings, tight list items, …) without
    this module needing to know anything about Textual."""
    classes = [f"block-{block.type.value}"]
    if block.type == BlockType.HEADING:
        classes.append(f"block-heading-{block.level or 1}")
    return " ".join(classes)


def render_block(block: DocumentBlock, theme: Theme, width: int) -> RenderableType | None:
    """Never let one malformed block take the whole reader down (brief §63: clean
    recoverable errors, not raw tracebacks) — a bad table/code/image block degrades to a
    plain-text placeholder instead of propagating out of the render pass."""
    try:
        return _render_block_unsafe(block, theme, width)
    except Exception as exc:
        return Text(f"[Could not render this {block.type.value} block: {exc}]", style=f"italic {theme.muted}")


def _render_block_unsafe(block: DocumentBlock, theme: Theme, width: int) -> RenderableType | None:
    if block.type == BlockType.HEADING:
        return _render_heading(block, theme)
    if block.type == BlockType.PARAGRAPH:
        return _render_paragraph(block, theme)
    if block.type == BlockType.LIST:
        return None  # container marker only; LIST_ITEM children render themselves
    if block.type == BlockType.LIST_ITEM:
        return _render_list_item(block, theme)
    if block.type == BlockType.CODE:
        return _render_code(block, theme)
    if block.type == BlockType.QUOTE:
        return _render_quote(block, theme)
    if block.type == BlockType.TABLE:
        return _render_table(block, theme, width)
    if block.type == BlockType.IMAGE:
        return _render_image(block, theme)
    if block.type == BlockType.CAPTION:
        return Text(block.text, style=f"italic {theme.muted}")
    if block.type == BlockType.FOOTNOTE:
        return Text(f"[{block.order}] {block.text}", style=theme.muted)
    if block.type == BlockType.EQUATION:
        return Padding(Syntax(block.text, "text", theme=theme.code_theme, word_wrap=True), (0, 2))
    if block.type == BlockType.PAGE_BREAK:
        return None
    return Text(block.text)


def _render_heading(block: DocumentBlock, theme: Theme) -> RenderableType:
    level = block.level or 1
    color = theme.heading_color(level)
    raw = block.text.strip()
    match = _HEADING_NUMBER_RE.match(raw)

    text = Text()
    if match:
        number, rest = match.groups()
        text.append(f"{number}  ", style=color)
        title = rest.upper() if level == 1 else rest
    else:
        title = raw.upper() if level == 1 else raw
    text.append(title, style=f"bold {color}")
    return text


def _render_paragraph(block: DocumentBlock, theme: Theme) -> RenderableType:
    style = "dim " + theme.foreground if block.metadata.get("ocr_required") else theme.foreground
    return Text(block.text, style=style)


def _render_list_item(block: DocumentBlock, theme: Theme) -> RenderableType:
    depth = block.level or 0
    indent = "  " * depth
    ordered = block.metadata.get("ordered", False)
    marker = f"{block.order}." if ordered else "•"
    bullet = Text(f"{indent}{marker} ", style=theme.accent)
    bullet.append(block.text, style=theme.foreground)
    return bullet


def _render_code(block: DocumentBlock, theme: Theme) -> RenderableType:
    language = block.metadata.get("language") or "text"
    syntax = Syntax(block.text, language, theme=theme.code_theme, word_wrap=False, background_color=theme.surface)
    return Panel(syntax, border_style=theme.border, padding=(0, 1), expand=True)


def _render_quote(block: DocumentBlock, theme: Theme) -> RenderableType:
    lines = block.text.split("\n")
    quoted = Text()
    for i, line in enumerate(lines):
        if i:
            quoted.append("\n")
        quoted.append("│ ", style=theme.quote_color)
        quoted.append(line, style=f"italic {theme.foreground}")
    return quoted


def _render_table(block: DocumentBlock, theme: Theme, width: int) -> RenderableType:
    headers: list[str] = block.metadata.get("headers", [])
    rows: list[list[str]] = block.metadata.get("rows", [])

    if headers and len(headers) > _NARROW_TABLE_THRESHOLD and width < 70:
        return _render_stacked(headers, rows, theme)

    table = Table(border_style=theme.border, header_style=f"bold {theme.accent}", expand=False)
    for h in headers or (["Column"] * (len(rows[0]) if rows else 1)):
        table.add_column(h)
    for row in rows:
        table.add_row(*[str(c) for c in row])
    return table


def _render_stacked(headers: list[str], rows: list[list[str]], theme: Theme) -> RenderableType:
    blocks = []
    for row in rows:
        record = Text()
        for h, cell in zip(headers, row):
            record.append(f"{h}\n", style=f"bold {theme.accent}")
            record.append(f"  {cell}\n", style=theme.foreground)
        blocks.append(record)
    return Group(*blocks)


def _render_image(block: DocumentBlock, theme: Theme) -> RenderableType:
    caption = block.text or "Image"
    body = Text(f"{caption}\n", style=f"bold {theme.foreground}")
    body.append("[Press Enter to view image]", style=theme.muted)
    return Panel(body, border_style=theme.border, title="Figure", title_align="left")


__all__ = ["render_block"]
