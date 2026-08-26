from pinax.documents.parser import parse_document
from pinax.persistence.database import connect
from pinax.persistence.repositories import bookmarks as bookmark_repo
from pinax.persistence.repositories import documents as doc_repo
from pinax.persistence.repositories import reading_progress as progress_repo


def test_migration_is_idempotent(db_path):
    conn1 = connect(db_path)
    conn1.close()
    # Reconnecting to an already-migrated database must not raise or duplicate schema.
    conn2 = connect(db_path)
    version = conn2.execute("PRAGMA user_version").fetchone()[0]
    assert version >= 1
    conn2.close()


def test_document_upsert_and_lookup(db_path, md_file):
    conn = connect(db_path)
    doc = parse_document(str(md_file))
    record = doc_repo.upsert_from_document(conn, doc)
    assert record.path == str(md_file)

    by_path = doc_repo.get_by_path(conn, str(md_file))
    assert by_path.id == record.id

    by_id = doc_repo.get_by_id(conn, record.id)
    assert by_id.title == doc.title


def test_reopening_same_path_preserves_id(db_path, md_file):
    conn = connect(db_path)
    doc = parse_document(str(md_file))
    first = doc_repo.upsert_from_document(conn, doc)
    doc2 = parse_document(str(md_file))
    second = doc_repo.upsert_from_document(conn, doc2)
    assert first.id == second.id


def test_reading_progress_upsert_and_get(db_path, md_file):
    conn = connect(db_path)
    doc = parse_document(str(md_file))
    record = doc_repo.upsert_from_document(conn, doc)

    progress_repo.upsert(
        conn,
        document_id=record.id,
        block_id=doc.blocks[2].id,
        page=None,
        section_id=doc.blocks[2].section_id,
        scroll_offset=12.5,
        progress=0.4,
        reading_time_delta_s=30,
    )
    saved = progress_repo.get(conn, record.id)
    assert saved.block_id == doc.blocks[2].id
    assert saved.progress == 0.4
    assert saved.reading_time_s == 30

    # A second upsert accumulates reading time rather than overwriting it.
    progress_repo.upsert(
        conn,
        document_id=record.id,
        block_id=doc.blocks[3].id,
        page=None,
        section_id=doc.blocks[3].section_id,
        scroll_offset=20.0,
        progress=0.6,
        reading_time_delta_s=15,
    )
    saved2 = progress_repo.get(conn, record.id)
    assert saved2.block_id == doc.blocks[3].id
    assert saved2.reading_time_s == 45


def test_bookmark_crud(db_path, md_file):
    conn = connect(db_path)
    doc = parse_document(str(md_file))
    record = doc_repo.upsert_from_document(conn, doc)

    bm = bookmark_repo.create(
        conn,
        document_id=record.id,
        block_id=doc.blocks[0].id,
        page=None,
        section_id=doc.blocks[0].section_id,
        preview="Attention Is All You Need",
    )
    listed = bookmark_repo.list_for_document(conn, record.id)
    assert len(listed) == 1
    assert listed[0].id == bm.id

    bookmark_repo.delete(conn, bm.id)
    assert bookmark_repo.list_for_document(conn, record.id) == []


def test_document_delete_cascades_progress_and_bookmarks(db_path, md_file):
    conn = connect(db_path)
    doc = parse_document(str(md_file))
    record = doc_repo.upsert_from_document(conn, doc)
    progress_repo.upsert(
        conn, document_id=record.id, block_id=doc.blocks[0].id, page=None,
        section_id=None, scroll_offset=0, progress=0.0,
    )
    bookmark_repo.create(conn, document_id=record.id, block_id=doc.blocks[0].id, page=None, section_id=None, preview="x")

    doc_repo.delete(conn, record.id)

    assert progress_repo.get(conn, record.id) is None
    assert bookmark_repo.list_for_document(conn, record.id) == []
