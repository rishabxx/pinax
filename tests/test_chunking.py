from pinax.documents.chunking import chunk_document
from pinax.documents.parser import parse_document


def test_chunks_never_split_a_block(pdf_file):
    doc = parse_document(str(pdf_file))
    chunks = chunk_document(doc, max_chars=10)  # tiny budget forces many chunks
    seen_blocks = set()
    for chunk in chunks:
        for block_id in chunk.block_ids:
            assert block_id not in seen_blocks, "a block appeared in more than one chunk"
            seen_blocks.add(block_id)
    assert seen_blocks == {b.id for b in doc.blocks if b.text}


def test_chunk_heading_path_reflects_section_nesting(md_file):
    doc = parse_document(str(md_file))
    chunks = chunk_document(doc, max_chars=20)
    nested = next(c for c in chunks if "Self-attention relates" in c.text)
    assert nested.heading_path[-1] == "2.1 Self Attention"
    assert "2 Background" in nested.heading_path


def test_chunk_source_pages_recorded(pdf_file):
    doc = parse_document(str(pdf_file))
    chunks = chunk_document(doc)
    pages = {p for c in chunks for p in c.source_pages}
    assert pages == {1, 2}
