"""Repository for `reading_progress` — one row per document, upserted on every navigation.

Writes are expected to be debounced by the caller (the reader screen), not on every
scroll event, per the brief's "don't hammer the DB on scroll" principle.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(slots=True)
class ReadingProgress:
    document_id: str
    block_id: str | None
    page: int | None
    section_id: str | None
    scroll_offset: float
    progress: float
    reading_time_s: int
    updated_at: str


def _row_to_progress(row: sqlite3.Row) -> ReadingProgress:
    return ReadingProgress(
        document_id=row["document_id"],
        block_id=row["block_id"],
        page=row["page"],
        section_id=row["section_id"],
        scroll_offset=row["scroll_offset"],
        progress=row["progress"],
        reading_time_s=row["reading_time_s"],
        updated_at=row["updated_at"],
    )


def get(conn: sqlite3.Connection, document_id: str) -> ReadingProgress | None:
    row = conn.execute("SELECT * FROM reading_progress WHERE document_id = ?", (document_id,)).fetchone()
    return _row_to_progress(row) if row else None


def upsert(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    block_id: str | None,
    page: int | None,
    section_id: str | None,
    scroll_offset: float,
    progress: float,
    reading_time_delta_s: int = 0,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO reading_progress (document_id, block_id, page, section_id, scroll_offset, progress, reading_time_s, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(document_id) DO UPDATE SET
            block_id = excluded.block_id,
            page = excluded.page,
            section_id = excluded.section_id,
            scroll_offset = excluded.scroll_offset,
            progress = excluded.progress,
            reading_time_s = reading_time_s + ?,
            updated_at = excluded.updated_at
        """,
        (document_id, block_id, page, section_id, scroll_offset, progress, reading_time_delta_s, now, reading_time_delta_s),
    )
    conn.commit()


__all__ = ["ReadingProgress", "get", "upsert"]
