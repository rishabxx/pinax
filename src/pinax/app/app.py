"""The Textual application shell — screen stack only, no document/AI logic of its own."""

from __future__ import annotations

from textual.app import App

from ..config.settings import cache_dir, database_path, load_settings
from ..persistence.database import connect


class PinaxApp(App):
    TITLE = "pinax"
    CSS = """
    Screen {
        background: $background;
    }
    """

    def __init__(
        self,
        initial_path: str | None = None,
        initial_page: int | None = None,
        initial_search: str | None = None,
    ) -> None:
        super().__init__()
        self.settings = load_settings()
        self.conn = connect(database_path())
        self.cache_dir = cache_dir()
        self._initial_path = initial_path
        self._initial_page = initial_page
        self._initial_search = initial_search

    def on_mount(self) -> None:
        from ..ui.screens.library import LibraryScreen

        if self._initial_path:
            self.open_document_path(self._initial_path, page=self._initial_page, search=self._initial_search)
        else:
            self.push_screen(LibraryScreen(self.conn, self.cache_dir, self.settings))

    def open_document_path(self, path: str, *, page: int | None = None, search: str | None = None) -> None:
        from ..ui.screens.reader import ReaderScreen

        if isinstance(self.screen, ReaderScreen):
            self.pop_screen()
        self.push_screen(
            ReaderScreen(path, self.conn, self.cache_dir, self.settings, initial_page=page, initial_search=search)
        )

    def on_unmount(self) -> None:
        self.conn.close()
