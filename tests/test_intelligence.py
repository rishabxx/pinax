from __future__ import annotations

from pinax.app.state import ReadingContext
from pinax.documents.parser import parse_document
from pinax.intelligence.citations import parse_citations
from pinax.intelligence.context_builder import build_context
from pinax.persistence.database import connect
from pinax.search.lexical import index_document


def _doc_and_conn(db_path, path):
    doc = parse_document(str(path))
    conn = connect(db_path)
    index_document(conn, doc)
    return doc, conn


def test_build_context_includes_visible_and_nearby_blocks(db_path, md_file):
    doc, conn = _doc_and_conn(db_path, md_file)
    heading = next(b for b in doc.blocks if b.type.value == "heading" and b.level == 2)
    idx = doc.blocks.index(heading)

    rc = ReadingContext(
        document_id=doc.id,
        current_section_id=heading.section_id,
        visible_block_ids=[heading.id],
        cursor_block_id=heading.id,
        previous_block_ids=[b.id for b in doc.blocks[max(0, idx - 2) : idx]],
        next_block_ids=[b.id for b in doc.blocks[idx + 1 : idx + 3]],
    )

    ctx = build_context(question="What is this about?", document=doc, reading_context=rc, conn=conn, history=[])

    tier_names = {t.name: t for t in ctx.tiers}
    assert tier_names["visible_blocks"].included
    assert tier_names["selected_text"].included is False

    user_message = ctx.messages[-1].content
    assert heading.text in user_message
    assert "CURRENTLY VISIBLE CONTENT" in user_message
    assert "QUESTION" in user_message
    assert ctx.messages[0].role == "system"


def test_build_context_pulls_in_retrieved_chunks_for_unrelated_question(db_path, md_file):
    doc, conn = _doc_and_conn(db_path, md_file)
    first_block = doc.blocks[0]

    rc = ReadingContext(document_id=doc.id, visible_block_ids=[first_block.id], cursor_block_id=first_block.id)
    ctx = build_context(question="attention", document=doc, reading_context=rc, conn=conn, history=[])

    tier_names = {t.name: t for t in ctx.tiers}
    # "attention" appears elsewhere in the fixture, away from block 0 — should be retrieved.
    assert tier_names["retrieved_chunks"].included


def test_build_context_respects_history_budget(db_path, md_file):
    from pinax.intelligence.context_builder import ContextBudget

    doc, conn = _doc_and_conn(db_path, md_file)
    rc = ReadingContext(document_id=doc.id, visible_block_ids=[doc.blocks[0].id], cursor_block_id=doc.blocks[0].id)

    long_history = [(f"question {i}", "a" * 500) for i in range(10)]
    ctx = build_context(
        question="new question",
        document=doc,
        reading_context=rc,
        conn=conn,
        history=long_history,
        budget=ContextBudget(history=50),
    )
    tier = next(t for t in ctx.tiers if t.name == "history")
    assert tier.tokens <= 60  # small overshoot tolerance from the last included entry


def test_parse_citations_resolves_page_and_section(pdf_file):
    doc = parse_document(str(pdf_file))
    answer = "Multi-head attention is explained here [p.1 · §3.2 Multi-Head Attention]."
    citations = parse_citations(answer, doc)
    assert len(citations) == 1
    assert citations[0].page == 1
    assert citations[0].block_id is not None


def test_parse_citations_ignores_non_citation_brackets():
    from pinax.documents.models import Document, DocumentMetadata

    doc = Document(id="d", path="x", title="t", metadata=DocumentMetadata(format="md", file_hash="h", file_size=1), sections=[], blocks=[])
    citations = parse_citations("See reference [1] and note [2] for details.", doc)
    assert citations == []


def test_parse_citations_deduplicates():
    from pinax.documents.models import Document, DocumentMetadata

    doc = Document(id="d", path="x", title="t", metadata=DocumentMetadata(format="md", file_hash="h", file_size=1), sections=[], blocks=[])
    text = "As shown [p.5] and again [p.5], this holds."
    citations = parse_citations(text, doc)
    assert len(citations) == 1
