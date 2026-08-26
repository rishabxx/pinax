"""Repository for the `documents` table — the library index."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from ...documents.models import Document
from ...documents.normalization import new_id


@dataclass(slots=True)
class DocumentRecord:
    id: str
    path: str
    file_hash: str
    title: str
    author: str | None
    format: str
    page_count: int | None
    created_at: str
    last_opened_at: str | None


def _row_to_record(row: sqlite3.Row) -> DocumentRecord:
    return DocumentRecord(
        id=row["id"],
        path=row["path"],
        file_hash=row["file_hash"],
        title=row["title"],
        author=row["author"],
        format=row["format"],
        page_count=row["page_count"],
        created_at=row["created_at"],
        last_opened_at=row["last_opened_at"],
    )


def get_by_path(conn: sqlite3.Connection, path: str) -> DocumentRecord | None:
    row = conn.execute("SELECT * FROM documents WHERE path = ?", (path,)).fetchone()
    return _row_to_record(row) if row else None


def get_by_id(conn: sqlite3.Connection, document_id: str) -> DocumentRecord | None:
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    return _row_to_record(row) if row else None


def upsert_from_document(conn: sqlite3.Connection, document: Document) -> DocumentRecord:
    """Insert the library entry for a freshly parsed Document, or refresh it if the file
    changed on disk (different file_hash) while keeping the original id/history."""
    existing = get_by_path(conn, document.path)
    now = datetime.now(timezone.utc).isoformat()

    if existing is None:
        record = DocumentRecord(
            id=document.id,
            path=document.path,
            file_hash=document.metadata.file_hash,
            title=document.title,
            author=document.metadata.author,
            format=document.metadata.format,
            page_count=document.page_count,
            created_at=now,
            last_opened_at=now,
        )
        conn.execute(
            """INSERT INTO documents (id, path, file_hash, title, author, format, page_count, created_at, last_opened_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.path,
                record.file_hash,
                record.title,
                record.author,
                record.format,
                record.page_count,
                record.created_at,
                record.last_opened_at,
            ),
        )
        conn.commit()
        return record

    conn.execute(
        """UPDATE documents SET file_hash = ?, title = ?, author = ?, page_count = ?, last_opened_at = ?
           WHERE id = ?""",
        (document.metadata.file_hash, document.title, document.metadata.author, document.page_count, now, existing.id),
    )
    conn.commit()
    existing.file_hash = document.metadata.file_hash
    existing.title = document.title
    existing.page_count = document.page_count
    existing.last_opened_at = now
    return existing


def touch_last_opened(conn: sqlite3.Connection, document_id: str) -> None:
    conn.execute(
        "UPDATE documents SET last_opened_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), document_id),
    )
    conn.commit()


def list_recent(conn: sqlite3.Connection, limit: int = 50) -> list[DocumentRecord]:
    rows = conn.execute(
        "SELECT * FROM documents ORDER BY last_opened_at DESC NULLS LAST LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_record(r) for r in rows]


def delete(conn: sqlite3.Connection, document_id: str) -> None:
    conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    conn.commit()


__all__ = ["DocumentRecord", "get_by_path", "get_by_id", "upsert_from_document", "touch_last_opened", "list_recent", "delete", "new_id"]
