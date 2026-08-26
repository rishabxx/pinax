"""Document library (brief §19, §68) — `tr` with no arguments opens here."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from rich.text import Text
from textual.containers import Center, Horizontal, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Footer, ListItem, ListView, Static

from ...config.models import Settings
from ...persistence.repositories import documents as doc_repo
from ...persistence.repositories import reading_progress as progress_repo
from ..themes import get_theme
from ..widgets.progress_bar import ReadingProgressBar

_EMPTY_STATE = """\
                          PINAX

                   Read without leaving
                     your terminal.

              Drop a document here or press O

                 PDF · DOCX · EPUB · MD
"""


class LibraryScreen(Screen):
    BINDINGS = [
        ("enter", "open_selected", "Open"),
        ("d", "remove_selected", "Remove"),
        ("r", "reveal_selected", "Reveal"),
        ("o,ctrl+o", "open_file_picker", "Open file"),
        ("q,escape", "quit_app", "Quit"),
    ]

    def __init__(self, conn, cache_dir: Path, settings: Settings, **kwargs) -> None:
        super().__init__(**kwargs)
        self.conn = conn
        self.cache_dir = cache_dir
        self.settings = settings
        self.theme = get_theme(settings.reader.theme)
        self._records: list[doc_repo.DocumentRecord] = []

    def compose(self):
        with Vertical(id="library-root"):
            yield Static("RECENTLY READ", id="library-title")
            yield ListView(id="library-list")
        yield Footer()

    def on_mount(self) -> None:
        self.styles.background = self.theme.background
        self.query_one("#library-root").styles.padding = (1, 3)
        self.query_one("#library-title").styles.color = self.theme.muted
        self.query_one("#library-title").styles.text_style = "bold"
        self._reload()

    def on_screen_resume(self) -> None:
        self._reload()

    def _reload(self) -> None:
        self._records = doc_repo.list_recent(self.conn)
        list_view = self.query_one("#library-list", ListView)
        list_view.clear()

        if not self._records:
            list_view.display = False
            if not self.query("#empty-state"):
                self.mount(Center(Middle(Static(_EMPTY_STATE, id="empty-state")), id="empty-wrap"))
            return

        for wrap in self.query("#empty-wrap"):
            wrap.remove()
        list_view.display = True

        for record in self._records:
            progress = progress_repo.get(self.conn, record.id)
            percent = progress.progress if progress else 0.0
            last_read = _format_last_opened(record.last_opened_at)
            row = Vertical(
                Static(Text(record.title, style=f"bold {self.theme.foreground}")),
                Horizontal(
                    ReadingProgressBar(percent, self.theme),
                    Static(Text(f"  Last read {last_read}", style=self.theme.muted)),
                ),
            )
            list_view.append(ListItem(row))

    def action_open_selected(self) -> None:
        list_view = self.query_one("#library-list", ListView)
        if list_view.index is not None and 0 <= list_view.index < len(self._records):
            self.app.open_document_path(self._records[list_view.index].path)

    def action_remove_selected(self) -> None:
        list_view = self.query_one("#library-list", ListView)
        if list_view.index is not None and 0 <= list_view.index < len(self._records):
            doc_repo.delete(self.conn, self._records[list_view.index].id)
            self._reload()

    def action_reveal_selected(self) -> None:
        list_view = self.query_one("#library-list", ListView)
        if list_view.index is None or not (0 <= list_view.index < len(self._records)):
            return
        path = self._records[list_view.index].path
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", "-R", path], check=False)
            elif sys.platform.startswith("linux"):
                subprocess.run(["xdg-open", str(Path(path).parent)], check=False)
        except FileNotFoundError:
            pass

    def action_open_file_picker(self) -> None:
        from .file_picker import FilePickerScreen

        def on_selected(path: str | None) -> None:
            if path:
                self.app.open_document_path(path)

        self.app.push_screen(FilePickerScreen(self.theme), on_selected)

    def action_quit_app(self) -> None:
        self.app.exit()


def _format_last_opened(value: str | None) -> str:
    if not value:
        return "never"
    return value.split("T")[0]
