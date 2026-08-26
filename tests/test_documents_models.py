from pinax.documents.models import (
    BlockType,
    Document,
    DocumentBlock,
    DocumentMetadata,
    Section,
)


def _doc() -> Document:
    blocks = [
        DocumentBlock(id="b1", type=BlockType.HEADING, text="Intro", order=0, level=1, section_id="s1"),
        DocumentBlock(id="b2", type=BlockType.PARAGRAPH, text="Hello world", order=1, section_id="s1"),
        DocumentBlock(id="b3", type=BlockType.PARAGRAPH, text="Second para", order=2, section_id="s2"),
    ]
    sections = [
        Section(id="s1", title="Intro", level=1, order=0, block_ids=["b1", "b2"]),
        Section(id="s2", title="Details", level=1, order=1, block_ids=["b3"]),
    ]
    return Document(
        id="doc1",
        path="/tmp/x.md",
        title="Test",
        metadata=DocumentMetadata(format="markdown", file_hash="abc", file_size=10),
        sections=sections,
        blocks=blocks,
    )


def test_block_by_id():
    doc = _doc()
    assert doc.block_by_id("b2").text == "Hello world"
    assert doc.block_by_id("missing") is None


def test_section_by_id():
    doc = _doc()
    assert doc.section_by_id("s2").title == "Details"


def test_blocks_for_section():
    doc = _doc()
    blocks = doc.blocks_for_section("s1")
    assert [b.id for b in blocks] == ["b1", "b2"]


def test_blocks_for_missing_section_returns_empty():
    doc = _doc()
    assert doc.blocks_for_section("nope") == []
