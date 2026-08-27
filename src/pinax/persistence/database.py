"""SQLite connection + schema migrations.

A single file database at the platform data directory. Migrations are plain SQL strings
applied in order, tracked via `PRAGMA user_version` — enough for a single-user local app;
no migration framework needed.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_MIGRATIONS: list[str] = [
    # 1: initial schema
    """
    CREATE TABLE documents (
        id              TEXT PRIMARY KEY,
        path            TEXT NOT NULL UNIQUE,
        file_hash       TEXT NOT NULL,
        title           TEXT NOT NULL,
        author          TEXT,
        format          TEXT NOT NULL,
        page_count      INTEGER,
        created_at      TEXT NOT NULL,
        last_opened_at  TEXT
    );

    CREATE TABLE reading_progress (
        document_id     TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
        block_id        TEXT,
        page            INTEGER,
        section_id      TEXT,
        scroll_offset   REAL NOT NULL DEFAULT 0,
        progress        REAL NOT NULL DEFAULT 0,
        reading_time_s  INTEGER NOT NULL DEFAULT 0,
        updated_at      TEXT NOT NULL
    );

    CREATE TABLE bookmarks (
        id              TEXT PRIMARY KEY,
        document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        block_id        TEXT,
        page            INTEGER,
        section_id      TEXT,
        preview         TEXT,
        label           TEXT,
        created_at      TEXT NOT NULL
    );

    CREATE TABLE annotations (
        id                TEXT PRIMARY KEY,
        document_id       TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        block_id          TEXT,
        selection_start   INTEGER,
        selection_end     INTEGER,
        selected_text     TEXT,
        note              TEXT NOT NULL,
        created_at        TEXT NOT NULL,
        updated_at        TEXT NOT NULL
    );

    CREATE TABLE document_cache (
        document_id     TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
        file_hash       TEXT NOT NULL,
        parser_version  TEXT NOT NULL,
        blob_path       TEXT NOT NULL,
        created_at      TEXT NOT NULL
    );

    CREATE VIRTUAL TABLE blocks_fts USING fts5(
        document_id UNINDEXED,
        block_id UNINDEXED,
        section_title,
        text,
        page UNINDEXED
    );

    CREATE INDEX idx_bookmarks_document ON bookmarks(document_id);
    CREATE INDEX idx_annotations_document ON annotations(document_id);
    """,
    # 2: AI conversation history (Phase 2, brief §39/§41)
    """
    CREATE TABLE ai_messages (
        id              TEXT PRIMARY KEY,
        document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        block_id        TEXT,
        page            INTEGER,
        section_id      TEXT,
        question        TEXT NOT NULL,
        answer          TEXT NOT NULL,
        sources         TEXT NOT NULL DEFAULT '[]',
        provider        TEXT,
        model           TEXT,
        created_at      TEXT NOT NULL
    );

    CREATE INDEX idx_ai_messages_document ON ai_messages(document_id, created_at);
    """,
]


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, script in enumerate(_MIGRATIONS[current:], start=current + 1):
        conn.executescript(script)
        conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
