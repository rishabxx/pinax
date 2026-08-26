"""Format dispatch: path -> normalized Document.

This module is the only place that knows which suffix maps to which parser. Adding a new
format means adding one entry to `_PARSERS` and one module — nothing else in the app changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .models import Document


class UnsupportedFormatError(Exception):
    def __init__(self, suffix: str):
        super().__init__(f"No parser registered for '{suffix}' files")
        self.suffix = suffix


class ParseError(Exception):
    """Raised by a parser when a document (or a page/section of it) cannot be read.

    Carries enough detail for the UI to show a clean recoverable error (brief §63) instead
    of a raw traceback.
    """

    def __init__(self, message: str, *, reason: str | None = None, recoverable: bool = False):
        super().__init__(message)
        self.reason = reason
        self.recoverable = recoverable


def _load_parsers() -> dict[str, Callable[[str], Document]]:
    # Imported lazily so `import pinax.documents.parser` doesn't pull in every
    # third-party parsing library (fitz, docx, ebooklib) just to resolve one suffix.
    from . import docx as docx_parser
    from . import epub as epub_parser
    from . import markdown as markdown_parser
    from . import pdf as pdf_parser
    from . import text as text_parser

    return {
        ".pdf": pdf_parser.parse,
        ".docx": docx_parser.parse,
        ".md": markdown_parser.parse,
        ".markdown": markdown_parser.parse,
        ".txt": text_parser.parse,
        ".epub": epub_parser.parse,
    }


SUPPORTED_SUFFIXES = (".pdf", ".docx", ".md", ".markdown", ".txt", ".epub")


def parse_document(path: str) -> Document:
    suffix = Path(path).suffix.lower()
    parsers = _load_parsers()
    parser = parsers.get(suffix)
    if parser is None:
        raise UnsupportedFormatError(suffix)
    return parser(path)
