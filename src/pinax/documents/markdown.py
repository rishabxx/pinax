"""Markdown (.md) parser, built on markdown-it-py's syntax tree.

Headings map directly to Section boundaries — no heuristics needed, unlike PDF.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from .models import BlockType, Document, DocumentBlock, DocumentMetadata
from .normalization import (
    build_sections_from_headings,
    file_hash,
    guess_title_from_filename,
    new_id,
)

_EMPHASIS = re.compile(r"(\*\*\*|\*\*|\*|___|__|_)(.+?)\1")
_CODE_SPAN = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _plain_text(inline_source: str) -> str:
    """Strip common inline markup for the plain-text representation stored on a block.

    The reader UI is free to re-derive rich styling from the original file later; this is
    what search/AI-context/plain reflow rendering consume.
    """
    text = _IMAGE.sub(r"\1", inline_source)
    text = _LINK.sub(r"\1", text)
    text = _CODE_SPAN.sub(r"\1", text)
    text = _EMPHASIS.sub(r"\2", text)
    return text.strip()


def _inline_text(node: SyntaxTreeNode) -> str:
    for child in node.children:
        if child.type == "inline":
            return _plain_text(child.content)
    return ""


def _walk_list(node: SyntaxTreeNode, blocks: list[DocumentBlock], order: list[int], depth: int) -> None:
    ordered = node.type == "ordered_list"
    blocks.append(
        DocumentBlock(
            id=new_id("blk"),
            type=BlockType.LIST,
            text="",
            order=order[0],
            level=depth,
            metadata={"ordered": ordered},
        )
    )
    order[0] += 1
    for item in node.children:
        if item.type != "list_item":
            continue
        item_text_parts = []
        for child in item.children:
            if child.type in ("paragraph", "heading"):
                item_text_parts.append(_inline_text(child))
        blocks.append(
            DocumentBlock(
                id=new_id("blk"),
                type=BlockType.LIST_ITEM,
                text=" ".join(p for p in item_text_parts if p),
                order=order[0],
                level=depth,
            )
        )
        order[0] += 1
        for child in item.children:
            if child.type in ("bullet_list", "ordered_list"):
                _walk_list(child, blocks, order, depth + 1)


def _walk_table(node: SyntaxTreeNode) -> tuple[list[str], list[list[str]]]:
    headers: list[str] = []
    rows: list[list[str]] = []
    for section in node.children:
        if section.type == "thead":
            for tr in section.children:
                headers = [_inline_text(cell) for cell in tr.children]
        elif section.type == "tbody":
            for tr in section.children:
                rows.append([_inline_text(cell) for cell in tr.children])
    return headers, rows


def _walk(root: SyntaxTreeNode) -> list[DocumentBlock]:
    blocks: list[DocumentBlock] = []
    order = [0]

    for node in root.children:
        if node.type == "heading":
            level = int(node.tag[1:]) if node.tag and node.tag[0] == "h" else 1
            blocks.append(
                DocumentBlock(
                    id=new_id("blk"),
                    type=BlockType.HEADING,
                    text=_inline_text(node),
                    order=order[0],
                    level=level,
                )
            )
            order[0] += 1
        elif node.type == "paragraph":
            inline = next((c for c in node.children if c.type == "inline"), None)
            if inline and len(inline.children) == 1 and inline.children[0].type == "image":
                img = inline.children[0]
                blocks.append(
                    DocumentBlock(
                        id=new_id("blk"),
                        type=BlockType.IMAGE,
                        text=img.attrs.get("alt", "") or "",
                        order=order[0],
                        metadata={"src": img.attrs.get("src", "")},
                    )
                )
            else:
                text = _inline_text(node)
                if text:
                    blocks.append(
                        DocumentBlock(id=new_id("blk"), type=BlockType.PARAGRAPH, text=text, order=order[0])
                    )
            order[0] += 1
        elif node.type in ("bullet_list", "ordered_list"):
            _walk_list(node, blocks, order, depth=0)
        elif node.type == "fence" or node.type == "code_block":
            blocks.append(
                DocumentBlock(
                    id=new_id("blk"),
                    type=BlockType.CODE,
                    text=node.content.rstrip("\n"),
                    order=order[0],
                    metadata={"language": node.info.strip() if node.info else ""},
                )
            )
            order[0] += 1
        elif node.type == "blockquote":
            parts = [_inline_text(c) for c in node.children if c.type == "paragraph"]
            blocks.append(
                DocumentBlock(
                    id=new_id("blk"),
                    type=BlockType.QUOTE,
                    text="\n".join(p for p in parts if p),
                    order=order[0],
                )
            )
            order[0] += 1
        elif node.type == "table":
            headers, rows = _walk_table(node)
            preview = " | ".join(headers) + "\n" + "\n".join(" | ".join(r) for r in rows)
            blocks.append(
                DocumentBlock(
                    id=new_id("blk"),
                    type=BlockType.TABLE,
                    text=preview,
                    order=order[0],
                    metadata={"headers": headers, "rows": rows},
                )
            )
            order[0] += 1
        # hr, html_block, etc. are intentionally skipped in Phase 1

    return blocks


def parse(path: str) -> Document:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    md = MarkdownIt("commonmark").enable("table")
    tree = SyntaxTreeNode(md.parse(raw))
    blocks = _walk(tree)
    sections = build_sections_from_headings(blocks)

    title = guess_title_from_filename(path)
    first_h1 = next((b for b in blocks if b.type == BlockType.HEADING and b.level == 1), None)
    if first_h1:
        title = first_h1.text

    stat = os.stat(path)
    return Document(
        id=new_id("doc"),
        path=str(path),
        title=title,
        metadata=DocumentMetadata(
            format="markdown",
            file_hash=file_hash(path),
            file_size=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        ),
        sections=sections,
        blocks=blocks,
        page_count=None,
    )
