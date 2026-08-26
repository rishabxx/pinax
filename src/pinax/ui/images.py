"""On-demand extraction of embedded images for terminal rendering.

Deliberately lazy and cached rather than extracted during parsing: `documents/pdf.py`
only records the xref of images large enough to matter (brief §49), and the actual bytes
are pulled from the source file the first time a block scrolls into view. This keeps the
parser free of cache-directory side effects and avoids decoding images nobody ever looks at.
"""

from __future__ import annotations

import functools
import io


def _normalize_to_png(data: bytes) -> bytes | None:
    """Decode + re-encode as RGB/RGBA PNG so every downstream consumer sees one predictable
    format, regardless of the original PDF encoding (CMYK JPEG, indexed/1-bit, JBIG2, odd
    colorspaces, …). Returns None if the bytes aren't a decodable image at all — the caller
    falls back to the placeholder panel instead of ever handing bad bytes to the image widget.
    """
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            img.load()
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if img.mode in ("P", "LA", "PA") else "RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        return None


@functools.lru_cache(maxsize=128)
def extract_pdf_image(pdf_path: str, xref: int) -> bytes | None:
    import pymupdf

    try:
        doc = pymupdf.open(pdf_path)
    except Exception:
        return None
    try:
        info = doc.extract_image(xref)
        raw = info.get("image") if info else None
    except Exception:
        raw = None
    finally:
        doc.close()

    return _normalize_to_png(raw) if raw else None


def extract_block_image(document_path: str, document_format: str, metadata: dict) -> bytes | None:
    if document_format == "pdf" and metadata.get("xref") is not None:
        return extract_pdf_image(document_path, metadata["xref"])
    return None


@functools.lru_cache(maxsize=256)
def render_pdf_page_thumbnail(pdf_path: str, page_number: int, scale: float) -> bytes | None:
    """Rasterize one PDF page to a small PNG for the PAGES sidebar tab."""
    import pymupdf

    try:
        doc = pymupdf.open(pdf_path)
    except Exception:
        return None
    try:
        if not (1 <= page_number <= doc.page_count):
            return None
        pixmap = doc[page_number - 1].get_pixmap(matrix=pymupdf.Matrix(scale, scale))
        return pixmap.tobytes("png")
    except Exception:
        return None
    finally:
        doc.close()


__all__ = ["extract_pdf_image", "extract_block_image", "render_pdf_page_thumbnail"]
