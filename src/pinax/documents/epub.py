"""EPUB parser, built on ebooklib + BeautifulSoup.

EPUB is reflowable — there is no physical page concept, so `source_page` stays None
throughout (per the brief's Document Model rationale). Chapter boundaries come from the
book's own spine + nav TOC where available, falling back to in-chapter heading tags.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from bs4 import BeautifulSoup, NavigableString, Tag
from ebooklib import epub, ITEM_DOCUMENT

from .models import BlockType, Document, DocumentBlock, DocumentMetadata
from .normalization import build_sections_from_headings, file_hash, guess_title_from_filename, new_id

_CONTAINER_TAGS = {"div", "section", "article", "body", "main", "header", "footer", "figure"}
_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


def _text(tag: Tag) -> str:
    return " ".join(tag.get_text(" ").split())


def _walk_list(tag: Tag, blocks: list[DocumentBlock], order: list[int], depth: int) -> None:
    ordered = tag.name == "ol"
    blocks.append(
        DocumentBlock(id=new_id("blk"), type=BlockType.LIST, text="", order=order[0], level=depth, metadata={"ordered": ordered})
    )
    order[0] += 1
    for li in tag.find_all("li", recursive=False):
        nested_lists = li.find_all(["ul", "ol"], recursive=False)
        own_text_tags = [c for c in li.children if isinstance(c, NavigableString) or (isinstance(c, Tag) and c.name not in ("ul", "ol"))]
        text = " ".join(
            (str(c).strip() if isinstance(c, NavigableString) else _text(c)) for c in own_text_tags
        ).strip()
        if text:
            blocks.append(DocumentBlock(id=new_id("blk"), type=BlockType.LIST_ITEM, text=text, order=order[0], level=depth))
            order[0] += 1
        for nested in nested_lists:
            _walk_list(nested, blocks, order, depth + 1)


def _walk(node: Tag, blocks: list[DocumentBlock], order: list[int]) -> None:
    for child in node.children:
        if not isinstance(child, Tag):
            continue
        name = child.name.lower() if child.name else ""

        if name in _HEADING_TAGS:
            text = _text(child)
            if text:
                blocks.append(DocumentBlock(id=new_id("blk"), type=BlockType.HEADING, text=text, order=order[0], level=_HEADING_TAGS[name]))
                order[0] += 1
        elif name == "p":
            img = child.find("img")
            text = _text(child)
            if not text and img is not None:
                blocks.append(
                    DocumentBlock(id=new_id("blk"), type=BlockType.IMAGE, text=img.get("alt", "") or "", order=order[0], metadata={"src": img.get("src", "")})
                )
                order[0] += 1
            elif text:
                blocks.append(DocumentBlock(id=new_id("blk"), type=BlockType.PARAGRAPH, text=text, order=order[0]))
                order[0] += 1
        elif name in ("ul", "ol"):
            _walk_list(child, blocks, order, depth=0)
        elif name == "blockquote":
            text = _text(child)
            if text:
                blocks.append(DocumentBlock(id=new_id("blk"), type=BlockType.QUOTE, text=text, order=order[0]))
                order[0] += 1
        elif name == "pre":
            code = child.get_text()
            blocks.append(DocumentBlock(id=new_id("blk"), type=BlockType.CODE, text=code.rstrip("\n"), order=order[0]))
            order[0] += 1
        elif name == "table":
            rows = [[_text(cell) for cell in tr.find_all(["th", "td"])] for tr in child.find_all("tr")]
            headers = rows[0] if rows else []
            body = rows[1:] if len(rows) > 1 else []
            preview = " | ".join(headers) + "\n" + "\n".join(" | ".join(r) for r in body)
            blocks.append(DocumentBlock(id=new_id("blk"), type=BlockType.TABLE, text=preview, order=order[0], metadata={"headers": headers, "rows": body}))
            order[0] += 1
        elif name == "img":
            blocks.append(DocumentBlock(id=new_id("blk"), type=BlockType.IMAGE, text=child.get("alt", "") or "", order=order[0], metadata={"src": child.get("src", "")}))
            order[0] += 1
        elif name in _CONTAINER_TAGS:
            _walk(child, blocks, order)
        # else: inline-only or non-content tags (script, style, nav, ...) are skipped


def _nav_titles(book: epub.EpubBook) -> dict[str, str]:
    titles: dict[str, str] = {}

    def visit(entries) -> None:
        for entry in entries:
            if isinstance(entry, tuple):
                link, children = entry
                visit(children)
            else:
                link = entry
            href = getattr(link, "href", None)
            title = getattr(link, "title", None)
            if href and title:
                file_part = href.split("#")[0]
                titles.setdefault(file_part, title)

    visit(book.toc)
    return titles


def parse(path: str) -> Document:
    book = epub.read_epub(path, options={"ignore_ncx": True})
    nav_titles = _nav_titles(book)

    blocks: list[DocumentBlock] = []
    order = [0]
    chapter_index = 0

    for item in book.get_items_of_type(ITEM_DOCUMENT):
        chapter_index += 1
        soup = BeautifulSoup(item.get_content(), "html.parser")
        body = soup.find("body") or soup

        chapter_start = len(blocks)
        _walk(body, blocks, order)

        starts_with_heading = chapter_start < len(blocks) and blocks[chapter_start].type == BlockType.HEADING
        if not starts_with_heading and chapter_start < len(blocks):
            title = nav_titles.get(item.get_name())
            if not title:
                title_tag = soup.find("title")
                title = title_tag.get_text().strip() if title_tag and title_tag.get_text().strip() else None
            if title:
                heading = DocumentBlock(id=new_id("blk"), type=BlockType.HEADING, text=title, order=-1, level=1)
                # Insert as the first block of this chapter, then renumber.
                blocks.insert(chapter_start, heading)
                for i, b in enumerate(blocks):
                    b.order = i
                order[0] = len(blocks)

    sections = build_sections_from_headings(blocks)

    metadata_title = book.get_metadata("DC", "title")
    title = metadata_title[0][0] if metadata_title else guess_title_from_filename(path)
    metadata_author = book.get_metadata("DC", "creator")
    author = metadata_author[0][0] if metadata_author else None

    stat = os.stat(path)
    return Document(
        id=new_id("doc"),
        path=str(path),
        title=title,
        metadata=DocumentMetadata(
            author=author,
            format="epub",
            file_hash=file_hash(path),
            file_size=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        ),
        sections=sections,
        blocks=blocks,
        page_count=None,
    )
