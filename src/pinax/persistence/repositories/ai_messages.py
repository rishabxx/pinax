"""Repository for `ai_messages` — one row per Q&A turn, scoped to a document (brief §41:
"Store conversations per document")."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from ...documents.normalization import new_id


@dataclass(slots=True)
class AIMessage:
    id: str
    document_id: str
    block_id: str | None
    page: int | None
    section_id: str | None
    question: str
    answer: str
    sources: list[str]
    provider: str | None
    model: str | None
    created_at: str


def _row_to_message(row: sqlite3.Row) -> AIMessage:
    return AIMessage(
        id=row["id"],
        document_id=row["document_id"],
        block_id=row["block_id"],
        page=row["page"],
        section_id=row["section_id"],
        question=row["question"],
        answer=row["answer"],
        sources=json.loads(row["sources"]),
        provider=row["provider"],
        model=row["model"],
        created_at=row["created_at"],
    )


def create(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    block_id: str | None,
    page: int | None,
    section_id: str | None,
    question: str,
    answer: str,
    sources: list[str] | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> AIMessage:
    message = AIMessage(
        id=new_id("msg"),
        document_id=document_id,
        block_id=block_id,
        page=page,
        section_id=section_id,
        question=question,
        answer=answer,
        sources=sources or [],
        provider=provider,
        model=model,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    conn.execute(
        """INSERT INTO ai_messages
           (id, document_id, block_id, page, section_id, question, answer, sources, provider, model, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            message.id,
            message.document_id,
            message.block_id,
            message.page,
            message.section_id,
            message.question,
            message.answer,
            json.dumps(message.sources),
            message.provider,
            message.model,
            message.created_at,
        ),
    )
    conn.commit()
    return message


def list_for_document(conn: sqlite3.Connection, document_id: str, limit: int = 50) -> list[AIMessage]:
    rows = conn.execute(
        "SELECT * FROM ai_messages WHERE document_id = ? ORDER BY created_at ASC LIMIT ?",
        (document_id, limit),
    ).fetchall()
    return [_row_to_message(r) for r in rows]


__all__ = ["AIMessage", "create", "list_for_document"]
