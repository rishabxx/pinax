"""Page-thumbnail sidebar tab (brief §7.5 / the reference mockup's PAGES tab).

Thumbnails are only meaningful for PDFs (other formats are reflowable and have no fixed
page images). Generation is capped and runs off the event loop — a 600-page PDF must not
freeze the UI or rasterize pages nobody will scroll to.
"""

from __future__ import annotations

import asyncio
import io

from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from ...documents.models import Document
from ..images import render_pdf_page_thumbnail
from ..themes import Theme
from .reader_view import AutoImage, _AutoImageRenderable

MAX_THUMBNAILS = 40
THUMB_SCALE = 0.28


class _ThumbnailImage(AutoImage, Renderable=_AutoImageRenderable):
    DEFAULT_CSS = """
    _ThumbnailImage { width: 100%; height: auto; }
    """


class _PageThumbnail(Vertical):
    DEFAULT_CSS = """
    _PageThumbnail {
        height: auto;
        margin-bottom: 1;
        padding: 1;
        border: round $border;
    }
    _PageThumbnail:hover { border: round $accent; }
    _PageThumbnail > .page-number { text-align: center; padding-top: 1; }
    """

    class Selected(Message):
        def __init__(self, page_number: int) -> None:
            super().__init__()
            self.page_number = page_number

    def __init__(self, page_number: int, image_bytes: bytes, theme: Theme, **kwargs) -> None:
        super().__init__(**kwargs)
        self.page_number = page_number
        self._image_bytes = image_bytes
        self.theme = theme

    def compose(self):
        yield _ThumbnailImage(io.BytesIO(self._image_bytes))
        yield Static(Text(str(self.page_number), style=self.theme.muted), classes="page-number")

    def on_click(self) -> None:
        self.post_message(self.Selected(self.page_number))


class PagesPanel(VerticalScroll):
    DEFAULT_CSS = """
    PagesPanel { padding: 1; }
    """

    def __init__(self, theme: Theme, **kwargs) -> None:
        super().__init__(**kwargs)
        self.theme = theme
        self._built_for: str | None = None

    async def load_document(self, document: Document) -> None:
        if self._built_for == document.id:
            return
        self._built_for = document.id
        await self.remove_children()

        if document.metadata.format != "pdf" or not document.page_count:
            await self.mount(Static(Text("Thumbnails are available for PDFs only.", style=self.theme.muted)))
            return

        count = min(document.page_count, MAX_THUMBNAILS)
        for page_no in range(1, count + 1):
            image_bytes = await asyncio.to_thread(render_pdf_page_thumbnail, document.path, page_no, THUMB_SCALE)
            if self._built_for != document.id:
                return  # a newer document was loaded while we were still rendering
            if image_bytes is None:
                continue
            await self.mount(_PageThumbnail(page_no, image_bytes, self.theme))

        if document.page_count > MAX_THUMBNAILS:
            remaining = document.page_count - MAX_THUMBNAILS
            await self.mount(Static(Text(f"… {remaining} more pages not shown", style=self.theme.muted)))
