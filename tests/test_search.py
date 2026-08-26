from pinax.documents.parser import parse_document
from pinax.persistence.database import connect
from pinax.search.lexical import index_document, is_indexed, search


def test_index_and_search_finds_matching_chunks(db_path, pdf_file):
    conn = connect(db_path)
    doc = parse_document(str(pdf_file))
    assert not is_indexed(conn, doc.id)

    count = index_document(conn, doc)
    assert count > 0
    assert is_indexed(conn, doc.id)

    results = search(conn, doc.id, "attention")
    assert results
    assert any(r.page == 1 for r in results)
    assert any(r.page == 2 for r in results)


def test_search_scoped_to_document(db_path, pdf_file, md_file):
    conn = connect(db_path)
    doc1 = parse_document(str(pdf_file))
    doc2 = parse_document(str(md_file))
    index_document(conn, doc1)
    index_document(conn, doc2)

    results = search(conn, doc1.id, "attention")
    assert results
    assert all(r.snippet for r in results)

    # Same query against the other document must not return doc1's rows.
    results2 = search(conn, doc2.id, "masked")
    assert results2 == []


def test_search_empty_query_returns_nothing(db_path, pdf_file):
    conn = connect(db_path)
    doc = parse_document(str(pdf_file))
    index_document(conn, doc)
    assert search(conn, doc.id, "   ") == []


def test_reindex_replaces_old_rows(db_path, pdf_file):
    conn = connect(db_path)
    doc = parse_document(str(pdf_file))
    index_document(conn, doc)
    n1 = index_document(conn, doc)
    row_count = conn.execute(
        "SELECT COUNT(*) FROM blocks_fts WHERE document_id = ?", (doc.id,)
    ).fetchone()[0]
    assert row_count == n1
