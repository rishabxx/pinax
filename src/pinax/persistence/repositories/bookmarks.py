"""Repository for `bookmarks`."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from ...documents.normalization import new_id


@dataclass(slots=True)
class Bookmark:
    id: str
    document_id: str
    block_id: str | None
    page: int | None
    section_id: str | None
    preview: str | None
    label: str | None
    created_at: str


def _row_to_bookmark(row: sqlite3.Row) -> Bookmark:
    return Bookmark(
        id=row["id"],
        document_id=row["document_id"],
        block_id=row["block_id"],
        page=row["page"],
        section_id=row["section_id"],
        preview=row["preview"],
        label=row["label"],
        created_at=row["created_at"],
    )


def create(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    block_id: str | None,
    page: int | None,
    section_id: str | None,
    preview: str | None,
    label: str | None = None,
) -> Bookmark:
    bookmark = Bookmark(
        id=new_id("bm"),
        document_id=document_id,
        block_id=block_id,
        page=page,
        section_id=section_id,
        preview=preview,
        label=label,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    conn.execute(
        """INSERT INTO bookmarks (id, document_id, block_id, page, section_id, preview, label, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (bookmark.id, bookmark.document_id, bookmark.block_id, bookmark.page, bookmark.section_id, bookmark.preview, bookmark.label, bookmark.created_at),
    )
    conn.commit()
    return bookmark


def list_for_document(conn: sqlite3.Connection, document_id: str) -> list[Bookmark]:
    rows = conn.execute(
        "SELECT * FROM bookmarks WHERE document_id = ? ORDER BY created_at ASC", (document_id,)
    ).fetchall()
    return [_row_to_bookmark(r) for r in rows]


def delete(conn: sqlite3.Connection, bookmark_id: str) -> None:
    conn.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))
    conn.commit()


__all__ = ["Bookmark", "create", "list_for_document", "delete"]
