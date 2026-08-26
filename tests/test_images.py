"""Defensive image extraction — a bad/corrupt embedded image must degrade to the
placeholder panel, never crash the extend batch (and with it, the reader's ability to
scroll any further past that page)."""

from __future__ import annotations

from pinax.ui.images import _normalize_to_png, extract_pdf_image


def test_normalize_rejects_garbage_bytes():
    assert _normalize_to_png(b"not an image, just garbage bytes") is None


def test_normalize_accepts_valid_png_and_reencodes():
    from PIL import Image
    import io

    img = Image.new("RGB", (10, 10), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    result = _normalize_to_png(buf.getvalue())
    assert result is not None
    # Round-trips back through PIL cleanly.
    Image.open(io.BytesIO(result)).load()


def test_normalize_converts_cmyk_to_rgb():
    from PIL import Image
    import io

    img = Image.new("CMYK", (10, 10))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    result = _normalize_to_png(buf.getvalue())
    assert result is not None
    with Image.open(io.BytesIO(result)) as out:
        assert out.mode in ("RGB", "RGBA")


def test_extract_pdf_image_missing_xref_returns_none(tmp_path):
    import pymupdf

    pdf = pymupdf.open()
    pdf.new_page()
    path = tmp_path / "empty.pdf"
    pdf.save(path)

    assert extract_pdf_image(str(path), 9999) is None
