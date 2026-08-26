"""PDF parser, built on PyMuPDF (fitz).

Never calls `page.get_text()` and dumps it flat (brief §6). Instead:

1. Prefer the PDF's own outline (bookmarks) for section structure when present.
2. Otherwise infer headings from font-size/weight clustering relative to the document's
   body text size (brief §16).
3. Reconstruct block reading order per page from block/line bboxes rather than raw stream
   order, and detect tables via PyMuPDF's table finder.
4. Flag pages that look scanned (little/no extractable text, large image coverage) so the
   UI can show "OCR required for this page" (brief §7) — Phase 1 detects only; actually
   running OCR is a Phase 5 concern per the architecture doc's phased plan.

A page's bbox origin is top-left with y increasing downward, so blocks are ordered by
(row-bucketed y0, x0).
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from statistics import median

import pymupdf as fitz

from .models import BlockType, BoundingBox, Document, DocumentBlock, DocumentMetadata
from .normalization import build_sections_from_headings, file_hash, guess_title_from_filename, new_id

_BULLET_RE = re.compile(r"^\s*[•▪●○◦‣·-]\s+")
_NUMBERED_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]\s+")
_ROW_BUCKET_PT = 3.0
_BOLD_FLAG = 1 << 4
_MIN_FIGURE_AREA_RATIO = 0.03
_SCANNED_TEXT_WORD_THRESHOLD = 10
_SCANNED_IMAGE_COVERAGE = 0.5
_MONOSPACE_FONT_HINTS = (
    "courier",
    "mono",
    "consolas",
    "menlo",
    "inconsolata",
    "sourcecodepro",
    "source code",
    "firacode",
    "fira code",
    "jetbrains",
    "dejavusansmono",
    "cascadia",
    "ubuntumono",
    "robotomono",
    "spacemono",
    "ibmplexmono",
    "andale",
    "lucidaconsole",
)


def _is_monospace_font(font_name: str) -> bool:
    name = font_name.lower()
    return any(hint in name for hint in _MONOSPACE_FONT_HINTS)


def _guess_code_language(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "json"
    if re.search(r"^\s*(def |import |from \w+ import|class \w+[:(])", text, re.MULTILINE):
        return "python"
    if re.search(r"^\s*(function |const |let |var |export |=>)", text, re.MULTILINE):
        return "javascript"
    return "text"


def _span_text(span: dict) -> str:
    return span.get("text", "")


def _block_plain_text(block: dict) -> str:
    lines = []
    for line in block.get("lines", []):
        line_text = "".join(_span_text(s) for s in line.get("spans", [])).strip()
        if line_text:
            lines.append(line_text)
    return "\n".join(lines).strip()


def _block_font_stats(block: dict) -> tuple[float, float, str]:
    sizes = []
    bold_chars = 0
    total_chars = 0
    font_char_counts: dict[str, int] = {}
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text = span.get("text", "")
            if not text.strip():
                continue
            sizes.append(span.get("size", 10.0))
            total_chars += len(text)
            if span.get("flags", 0) & _BOLD_FLAG:
                bold_chars += len(text)
            font = span.get("font", "")
            font_char_counts[font] = font_char_counts.get(font, 0) + len(text)
    avg_size = median(sizes) if sizes else 10.0
    bold_ratio = (bold_chars / total_chars) if total_chars else 0.0
    dominant_font = max(font_char_counts, key=font_char_counts.get) if font_char_counts else ""
    return avg_size, bold_ratio, dominant_font


def _collect_font_profile(doc: fitz.Document) -> tuple[float, dict[float, int]]:
    """One pass over the document to find the body text size and heading-size clusters."""
    all_sizes: list[float] = []
    for page in doc:
        raw = page.get_text("dict")
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("text", "").strip():
                        all_sizes.append(round(span.get("size", 10.0), 1))

    if not all_sizes:
        return 10.0, {}

    body_size = median(all_sizes)
    heading_sizes = sorted({s for s in all_sizes if s > body_size * 1.08}, reverse=True)
    level_by_size = {size: min(i + 1, 6) for i, size in enumerate(heading_sizes)}
    return body_size, level_by_size


def _looks_scanned(page: fitz.Page) -> bool:
    words = page.get_text("words")
    if len(words) > _SCANNED_TEXT_WORD_THRESHOLD:
        return False
    page_area = page.rect.width * page.rect.height
    if page_area <= 0:
        return False
    image_area = 0.0
    for img in page.get_image_info():
        bbox = img.get("bbox")
        if bbox:
            image_area += max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])
    return (image_area / page_area) >= _SCANNED_IMAGE_COVERAGE


def _find_tables(page: fitz.Page):
    finder = getattr(page, "find_tables", None)
    if finder is None:
        return []
    try:
        return list(finder().tables)
    except Exception:
        return []


def _bbox_contains(outer: tuple[float, float, float, float], inner: tuple[float, float, float, float]) -> bool:
    return outer[0] - 1 <= inner[0] and outer[1] - 1 <= inner[1] and outer[2] + 1 >= inner[2] and outer[3] + 1 >= inner[3]


def _classify_text_block(
    text: str, avg_size: float, bold_ratio: float, body_size: float, level_by_size: dict[float, int], font_name: str
) -> tuple[BlockType, int | None]:
    if _is_monospace_font(font_name):
        return BlockType.CODE, None

    rounded = round(avg_size, 1)
    heading_level = level_by_size.get(rounded)
    if heading_level is None:
        for size, level in level_by_size.items():
            if abs(size - rounded) < 0.3:
                heading_level = level
                break

    is_short = len(text) < 140 and "\n" not in text
    if heading_level is not None and is_short:
        return BlockType.HEADING, heading_level
    if bold_ratio > 0.7 and is_short and avg_size >= body_size and not text.rstrip().endswith((".", ",", ";")):
        return BlockType.HEADING, 6
    if _BULLET_RE.match(text) or _NUMBERED_RE.match(text):
        return BlockType.LIST_ITEM, 0
    return BlockType.PARAGRAPH, None


def parse(path: str) -> Document:
    doc = fitz.open(path)
    body_size, level_by_size = _collect_font_profile(doc)

    blocks: list[DocumentBlock] = []
    order = 0

    for page_index in range(doc.page_count):
        page = doc[page_index]
        page_no = page_index + 1

        if _looks_scanned(page):
            blocks.append(
                DocumentBlock(
                    id=new_id("blk"),
                    type=BlockType.PARAGRAPH,
                    text="OCR required for this page",
                    source_page=page_no,
                    order=order,
                    metadata={"ocr_required": True},
                )
            )
            order += 1
            continue

        raw = page.get_text("dict")
        text_blocks = [b for b in raw.get("blocks", []) if b.get("type") == 0]

        tables = _find_tables(page)
        table_items = []
        covered_bboxes = []
        for table in tables:
            try:
                bbox = tuple(table.bbox)
                extracted = table.extract()
            except Exception:
                continue
            headers = extracted[0] if extracted else []
            rows = extracted[1:] if len(extracted) > 1 else []
            preview = " | ".join(str(c or "") for c in headers) + "\n" + "\n".join(
                " | ".join(str(c or "") for c in row) for row in rows
            )
            table_items.append((bbox, "table", {"headers": headers, "rows": rows, "text": preview}))
            covered_bboxes.append(bbox)

        page_area = page.rect.width * page.rect.height
        image_items = []
        for img in page.get_image_info(xrefs=True):
            bbox = tuple(img.get("bbox", (0, 0, 0, 0)))
            area = max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])
            if page_area > 0 and (area / page_area) >= _MIN_FIGURE_AREA_RATIO:
                image_items.append((bbox, "image", {"xref": img.get("xref")}))

        items: list[tuple[tuple[float, float, float, float], str, dict]] = []
        for block in text_blocks:
            bbox = tuple(block.get("bbox", (0, 0, 0, 0)))
            if any(_bbox_contains(t_bbox, bbox) for t_bbox in covered_bboxes):
                continue
            text = _block_plain_text(block)
            if not text:
                continue
            avg_size, bold_ratio, font_name = _block_font_stats(block)
            items.append(
                (bbox, "text", {"text": text, "avg_size": avg_size, "bold_ratio": bold_ratio, "font_name": font_name})
            )

        items.extend(table_items)
        items.extend(image_items)
        items.sort(key=lambda it: (round(it[0][1] / _ROW_BUCKET_PT), it[0][0]))

        for bbox, kind, payload in items:
            box = BoundingBox(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3])
            if kind == "text":
                block_type, level = _classify_text_block(
                    payload["text"], payload["avg_size"], payload["bold_ratio"], body_size, level_by_size, payload["font_name"]
                )
                block_text = payload["text"]
                if block_type == BlockType.LIST_ITEM:
                    block_text = _strip_list_marker(block_text)
                blocks.append(
                    DocumentBlock(
                        id=new_id("blk"),
                        type=block_type,
                        text=block_text,
                        source_page=page_no,
                        order=order,
                        level=level,
                        bbox=box,
                        metadata={"language": _guess_code_language(block_text)} if block_type == BlockType.CODE else {},
                    )
                )
            elif kind == "table":
                blocks.append(
                    DocumentBlock(
                        id=new_id("blk"),
                        type=BlockType.TABLE,
                        text=payload["text"],
                        source_page=page_no,
                        order=order,
                        bbox=box,
                        metadata={"headers": payload["headers"], "rows": payload["rows"]},
                    )
                )
            elif kind == "image":
                blocks.append(
                    DocumentBlock(
                        id=new_id("blk"),
                        type=BlockType.IMAGE,
                        text=f"Figure (page {page_no})",
                        source_page=page_no,
                        order=order,
                        bbox=box,
                        metadata={"xref": payload.get("xref")},
                    )
                )
            order += 1

    blocks = _merge_consecutive_code_blocks(blocks)
    sections = _sections_from_outline(doc, blocks) or build_sections_from_headings(blocks)

    meta = doc.metadata or {}
    title = meta.get("title") or guess_title_from_filename(path)
    stat = os.stat(path)

    return Document(
        id=new_id("doc"),
        path=str(path),
        title=title,
        metadata=DocumentMetadata(
            author=meta.get("author") or None,
            producer=meta.get("producer") or None,
            format="pdf",
            file_hash=file_hash(path),
            file_size=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        ),
        sections=sections,
        blocks=blocks,
        page_count=doc.page_count,
    )


def _merge_consecutive_code_blocks(blocks: list[DocumentBlock]) -> list[DocumentBlock]:
    """PDF code listings usually come back as one block per line (extra line spacing makes
    PyMuPDF treat each line as its own text block) — without this, a JSON snippet renders
    as dozens of separate one-line "paragraphs" instead of one code panel."""
    merged: list[DocumentBlock] = []
    for block in blocks:
        if merged and merged[-1].type == BlockType.CODE and block.type == BlockType.CODE and merged[-1].source_page == block.source_page:
            prev = merged[-1]
            prev.text = f"{prev.text}\n{block.text}"
            if prev.bbox and block.bbox:
                prev.bbox = BoundingBox(
                    x0=min(prev.bbox.x0, block.bbox.x0),
                    y0=min(prev.bbox.y0, block.bbox.y0),
                    x1=max(prev.bbox.x1, block.bbox.x1),
                    y1=max(prev.bbox.y1, block.bbox.y1),
                )
            continue
        merged.append(block)

    for i, block in enumerate(merged):
        block.order = i
    return merged


def _strip_list_marker(text: str) -> str:
    text = _BULLET_RE.sub("", text)
    text = _NUMBERED_RE.sub("", text)
    return text.strip()


def _sections_from_outline(doc: fitz.Document, blocks: list[DocumentBlock]):
    from .models import Section

    toc = doc.get_toc(simple=True)
    if not toc:
        return None

    blocks_by_page: dict[int, list[DocumentBlock]] = {}
    for b in blocks:
        if b.source_page is not None:
            blocks_by_page.setdefault(b.source_page, []).append(b)

    sections: list[Section] = []
    stack: list[Section] = []

    for order, (level, title, page) in enumerate(toc):
        while stack and stack[-1].level >= level:
            stack.pop()
        parent = stack[-1] if stack else None
        section = Section(
            id=new_id("sec"),
            title=title.strip(),
            level=level,
            order=order,
            parent_id=parent.id if parent else None,
            source_page_start=page if page > 0 else None,
        )
        sections.append(section)
        stack.append(section)

    # Assign every block to the last section whose start page is <= the block's page.
    # Sorted by page only (via `key=`, not tuple comparison) so ties — very common when
    # several outline entries share a page, e.g. front-matter sections — never fall back
    # to comparing Section objects, which have no defined ordering.
    ordered_sections = sorted(sections, key=lambda s: s.source_page_start or 1)
    for block in blocks:
        page = block.source_page or 1
        owner = None
        for section in ordered_sections:
            if (section.source_page_start or 1) <= page:
                owner = section
            else:
                break
        if owner is None and sections:
            owner = sections[0]
        if owner is not None:
            block.section_id = owner.id
            owner.block_ids.append(block.id)
            owner.source_page_end = max(owner.source_page_end or page, page)

    return sections
