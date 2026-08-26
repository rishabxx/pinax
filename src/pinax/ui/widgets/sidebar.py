"""Left sidebar — OUTLINE / PAGES tabs plus a document-info footer (matches the reference
layout). Owns the id `#toc-panel` for backward compatibility: `ReaderScreen` only ever calls
`load_document()` / `highlight_section()` / toggles `.display`, so this wrapper exposes the
same surface as the tree used to and nothing downstream needed to change.
"""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.containers import Vertical
from textual.widgets import Static, TabbedContent, TabPane

from ...documents.models import Document
from ..themes import Theme
from .pages_panel import PagesPanel
from .toc import TOCTree


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class Sidebar(Vertical):
    DEFAULT_CSS = """
    Sidebar {
        width: 34;
        border-right: solid $border;
    }
    Sidebar TabbedContent { height: 1fr; }
    Sidebar > .doc-info {
        height: auto;
        border-top: solid $border;
        padding: 1 2;
    }
    """

    def __init__(self, theme: Theme, **kwargs) -> None:
        super().__init__(**kwargs)
        self.theme = theme

    def compose(self):
        with TabbedContent(id="sidebar-tabs"):
            with TabPane("OUTLINE", id="tab-outline"):
                yield TOCTree(self.theme, id="toc-tree")
            with TabPane("PAGES", id="tab-pages"):
                yield PagesPanel(self.theme, id="pages-panel")
        yield Static(id="doc-info", classes="doc-info")

    def on_mount(self) -> None:
        self.styles.background = self.theme.surface
        self.styles.border_right = ("solid", self.theme.border)

    def apply_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.styles.background = theme.surface
        self.styles.border_right = ("solid", theme.border)

    def load_document(self, document: Document) -> None:
        self.query_one("#toc-tree", TOCTree).load_document(document)
        self.run_worker(self.query_one("#pages-panel", PagesPanel).load_document(document))
        self._render_doc_info(document)

    def highlight_section(self, section_id: str | None) -> None:
        self.query_one("#toc-tree", TOCTree).highlight_section(section_id)

    def _render_doc_info(self, document: Document) -> None:
        meta = document.metadata
        t = self.theme
        text = Text()
        text.append("DOCUMENT INFO\n\n", style=f"bold {t.muted}")

        rows = [
            ("File", Path(document.path).name),
            ("Format", meta.format.upper()),
        ]
        if document.page_count:
            rows.append(("Pages", str(document.page_count)))
        if meta.author:
            rows.append(("Author", meta.author))
        if meta.producer:
            rows.append(("Producer", meta.producer))
        rows.append(("Size", _format_size(meta.file_size)))
        if meta.created_at:
            rows.append(("Modified", meta.created_at.strftime("%b %d, %Y")))

        for label, value in rows:
            text.append(f"{label}: ", style=t.muted)
            text.append(f"{value}\n", style=t.foreground)

        self.query_one("#doc-info", Static).update(text)
