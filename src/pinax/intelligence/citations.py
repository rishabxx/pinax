"""Parses `[p.41 · §3.2]`-style citations out of an AI answer and resolves them back to a
navigable block (brief §29/§43) — the whole point of citations is that pressing Enter on one
jumps you there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..documents.models import Document

_CITATION_RE = re.compile(r"\[\s*(?:p\.\s*(\d+)\s*)?(?:[·\-,]\s*)?(?:§\s*([^\]]+?))?\s*\]")


@dataclass
class Citation:
    raw: str
    page: int | None
    section_label: str | None
    block_id: str | None
    section_id: str | None

    @property
    def label(self) -> str:
        if self.page and self.section_label:
            return f"p.{self.page} · §{self.section_label}"
        if self.page:
            return f"p.{self.page}"
        if self.section_label:
            return f"§{self.section_label}"
        return self.raw


def _resolve(document: Document, page: int | None, section_label: str | None) -> tuple[str | None, str | None]:
    section_id = None
    if section_label:
        needle = section_label.strip().lower()
        for section in document.sections:
            if needle in section.title.lower():
                section_id = section.id
                break

    if page is not None:
        candidates = sorted((b for b in document.blocks if b.source_page == page), key=lambda b: b.order)
        if candidates:
            return candidates[0].id, section_id or candidates[0].section_id

    if section_id:
        section = document.section_by_id(section_id)
        if section and section.block_ids:
            return section.block_ids[0], section_id

    return None, section_id


def parse_citations(text: str, document: Document) -> list[Citation]:
    citations: list[Citation] = []
    seen: set[tuple[int | None, str | None]] = set()

    for match in _CITATION_RE.finditer(text):
        page_str, section_label = match.groups()
        if not page_str and not section_label:
            continue
        page = int(page_str) if page_str else None
        section_label = section_label.strip() if section_label else None
        key = (page, section_label)
        if key in seen:
            continue
        seen.add(key)
        block_id, section_id = _resolve(document, page, section_label)
        citations.append(
            Citation(raw=match.group(0), page=page, section_label=section_label, block_id=block_id, section_id=section_id)
        )

    return citations


__all__ = ["Citation", "parse_citations"]
