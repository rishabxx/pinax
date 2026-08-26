"""Orchestrates parser + cache + library + search-index on document open.

This is composition, not a new layer: `documents/` stays parser-only and `persistence/`
stays storage-only. Living in `app/` keeps that boundary intact while still giving
"reopen a 500-page PDF instantly" (brief §55/§61) a single obvious home.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..documents.models import Document
from ..documents.normalization import file_hash as compute_file_hash
from ..documents.parser import parse_document
from ..persistence.repositories import documents as doc_repo
from ..search.lexical import index_document, is_indexed

PARSER_VERSION = "1"


def open_document(path: str, conn: sqlite3.Connection, cache_dir: Path) -> Document:
    resolved_path = str(Path(path).expanduser().resolve())
    current_hash = compute_file_hash(resolved_path)
    existing = doc_repo.get_by_path(conn, resolved_path)

    ast_dir = cache_dir / "ast"
    ast_dir.mkdir(parents=True, exist_ok=True)

    if existing is not None:
        blob_path = ast_dir / f"{existing.id}.json"
        cache_row = conn.execute(
            "SELECT file_hash, parser_version FROM document_cache WHERE document_id = ?",
            (existing.id,),
        ).fetchone()
        cache_fresh = (
            cache_row is not None
            and cache_row["file_hash"] == current_hash
            and cache_row["parser_version"] == PARSER_VERSION
            and blob_path.exists()
        )
        if cache_fresh:
            document = Document.model_validate_json(blob_path.read_text())
            doc_repo.touch_last_opened(conn, existing.id)
            if not is_indexed(conn, existing.id):
                index_document(conn, document)
            return document

    document = parse_document(resolved_path)
    if existing is not None:
        document = document.model_copy(update={"id": existing.id})

    record = doc_repo.upsert_from_document(conn, document)
    document = document.model_copy(update={"id": record.id})

    blob_path = ast_dir / f"{record.id}.json"
    blob_path.write_text(document.model_dump_json())
    _store_cache_row(conn, record.id, current_hash, blob_path)
    index_document(conn, document)

    return document


def _store_cache_row(conn: sqlite3.Connection, document_id: str, file_hash_value: str, blob_path: Path) -> None:
    conn.execute(
        """
        INSERT INTO document_cache (document_id, file_hash, parser_version, blob_path, created_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(document_id) DO UPDATE SET
            file_hash = excluded.file_hash,
            parser_version = excluded.parser_version,
            blob_path = excluded.blob_path,
            created_at = excluded.created_at
        """,
        (document_id, file_hash_value, PARSER_VERSION, str(blob_path)),
    )
    conn.commit()


__all__ = ["open_document"]
