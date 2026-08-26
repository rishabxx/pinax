from pinax.documents.models import BlockType
from pinax.documents.parser import UnsupportedFormatError, parse_document


def test_markdown_parses_headings_and_sections(md_file):
    doc = parse_document(str(md_file))
    assert doc.title == "Attention Is All You Need"
    headings = [b for b in doc.blocks if b.type == BlockType.HEADING]
    assert [h.text for h in headings] == [
        "Attention Is All You Need",
        "1 Introduction",
        "2 Background",
        "2.1 Self Attention",
    ]
    # nested section under "2 Background"
    self_attention = next(s for s in doc.sections if s.title == "2.1 Self Attention")
    parent = doc.section_by_id(self_attention.parent_id)
    assert parent.title == "2 Background"


def test_markdown_parses_code_list_quote_table(md_file):
    doc = parse_document(str(md_file))
    types = {b.type for b in doc.blocks}
    assert BlockType.CODE in types
    assert BlockType.LIST_ITEM in types
    assert BlockType.QUOTE in types
    assert BlockType.TABLE in types

    table = next(b for b in doc.blocks if b.type == BlockType.TABLE)
    assert table.metadata["headers"] == ["Model", "BLEU"]
    assert table.metadata["rows"][0] == ["Transformer", "28.4"]


def test_text_parser_splits_paragraphs(txt_file):
    doc = parse_document(str(txt_file))
    assert len(doc.blocks) == 3
    assert all(b.type == BlockType.PARAGRAPH for b in doc.blocks)
    assert len(doc.sections) == 1


def test_docx_parser_uses_heading_styles(docx_file):
    doc = parse_document(str(docx_file))
    assert doc.title == "Designing Data-Intensive Applications"
    headings = [b for b in doc.blocks if b.type == BlockType.HEADING]
    assert [h.text for h in headings] == [
        "Designing Data-Intensive Applications",
        "Chapter 5: Replication",
        "Leaderless Replication",
    ]
    list_items = [b for b in doc.blocks if b.type == BlockType.LIST_ITEM]
    assert [b.text for b in list_items] == ["First bullet", "Second bullet"]
    table = next(b for b in doc.blocks if b.type == BlockType.TABLE)
    assert table.metadata["headers"] == ["Model", "BLEU"]


def test_pdf_parser_infers_headings_from_font_size(pdf_file):
    doc = parse_document(str(pdf_file))
    assert doc.page_count == 2
    headings = [b for b in doc.blocks if b.type == BlockType.HEADING]
    assert any("Attention Is All You Need" in h.text for h in headings)
    assert any("3.2 Multi-Head Attention" in h.text for h in headings)
    assert any("3.3 Masked Attention" in h.text for h in headings)
    # page 2 content is tagged with source_page 2
    page2_blocks = [b for b in doc.blocks if b.source_page == 2]
    assert page2_blocks


def test_epub_parser_uses_headings_and_synthesizes_chapter_titles(epub_file):
    doc = parse_document(str(epub_file))
    assert doc.title == "Test Book"
    assert doc.metadata.author == "Jane Doe"
    headings = [b for b in doc.blocks if b.type == BlockType.HEADING]
    # Chapter 1 has its own <h1>; Chapter 2 has none and should get a synthesized heading
    assert any(h.text == "Chapter 1" for h in headings)
    assert any(h.text == "Chapter 2" for h in headings)
    assert doc.page_count is None


def test_pdf_code_lines_detected_by_font_and_merged(tmp_path):
    # Regression: PDF code listings extract as one text block per line (PyMuPDF splits on
    # line spacing), so without font-based detection + merging a JSON snippet rendered as
    # dozens of separate one-line "paragraphs" instead of one code block.
    import pymupdf

    pdf = pymupdf.open()
    page = pdf.new_page()
    y = 72
    for line in ['{', '  "id": "call_def456",', '  "type": "function",', "}"]:
        page.insert_text((72, y), line, fontsize=10, fontname="Courier")
        y += 20
    page.insert_text((72, y + 10), "A normal prose paragraph follows the snippet above.", fontsize=10)
    path = tmp_path / "code.pdf"
    pdf.save(path)

    doc = parse_document(str(path))
    code_blocks = [b for b in doc.blocks if b.type == BlockType.CODE]
    assert len(code_blocks) == 1
    assert code_blocks[0].text.count("\n") == 3
    assert code_blocks[0].metadata["language"] == "json"
    assert any(b.type == BlockType.PARAGRAPH for b in doc.blocks)


def test_pdf_outline_with_duplicate_page_numbers_does_not_crash(pdf_with_duplicate_outline_pages):
    # Regression: sections were previously sorted as (page, Section) tuples, so ties on
    # page fell back to comparing Section objects directly and raised
    # `TypeError: '<' not supported between instances of 'Section' and 'Section'`.
    doc = parse_document(str(pdf_with_duplicate_outline_pages))
    assert [s.title for s in doc.sections] == [
        "Prerequisites",
        "Acknowledgments",
        "Chapter One",
        "Section 1.1",
    ]
    front_matter_block = next(b for b in doc.blocks if b.text == "Front Matter")
    assert doc.section_by_id(front_matter_block.section_id).title == "Acknowledgments"


def test_unsupported_format_raises():
    try:
        parse_document("/tmp/whatever.xyz")
    except UnsupportedFormatError as exc:
        assert exc.suffix == ".xyz"
    else:
        raise AssertionError("expected UnsupportedFormatError")
