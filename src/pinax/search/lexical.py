"""Lexical search via SQLite FTS5, indexed at chunk (not raw-block) granularity.

Chunking respects section/heading boundaries (brief §37), which gives noticeably better
search snippets than one FTS row per tiny block. Semantic retrieval (Phase 3) will reuse the
same `chunk_document()` output for embeddings, so this stays the single source of chunks.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from ..documents.chunking import chunk_document
from ..documents.models import Document

_TOKEN_RE = re.compile(r"\w+")


@dataclass(slots=True)
class SearchResult:
    block_id: str | None
    section_title: str
    snippet: str
    page: int | None
    rank: float


def index_document(conn: sqlite3.Connection, document: Document) -> int:
    conn.execute("DELETE FROM blocks_fts WHERE document_id = ?", (document.id,))
    chunks = chunk_document(document)
    rows = [
        (
            document.id,
            chunk.block_ids[0] if chunk.block_ids else None,
            " › ".join(chunk.heading_path),
            chunk.text,
            chunk.source_pages[0] if chunk.source_pages else None,
        )
        for chunk in chunks
        if chunk.text
    ]
    conn.executemany(
        "INSERT INTO blocks_fts (document_id, block_id, section_title, text, page) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def is_indexed(conn: sqlite3.Connection, document_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM blocks_fts WHERE document_id = ? LIMIT 1", (document_id,)).fetchone()
    return row is not None


def _fts_query(raw: str) -> str | None:
    tokens = _TOKEN_RE.findall(raw)
    if not tokens:
        return None
    return " ".join(f'"{t}"' for t in tokens)


def search(conn: sqlite3.Connection, document_id: str, query: str, limit: int = 50) -> list[SearchResult]:
    fts_query = _fts_query(query)
    if fts_query is None:
        return []

    try:
        rows = conn.execute(
            """
            SELECT block_id, section_title, page,
                   snippet(blocks_fts, 3, '«', '»', '…', 10) AS snip,
                   bm25(blocks_fts) AS rank
            FROM blocks_fts
            WHERE document_id = ? AND blocks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (document_id, fts_query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    return [
        SearchResult(block_id=r["block_id"], section_title=r["section_title"] or "", snippet=r["snip"], page=r["page"], rank=r["rank"])
        for r in rows
    ]


__all__ = ["SearchResult", "index_document", "is_indexed", "search"]
