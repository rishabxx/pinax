"""In-document search overlay (brief §17).

Deliberately doesn't touch the database itself — it posts `SearchSubmitted` and the screen
(which owns the sqlite connection) runs the query and calls `show_results()`. Keeps
"widgets don't talk to persistence" honest.
"""

from __future__ import annotations

from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, ListItem, ListView, Static

from ...search.lexical import SearchResult
from ..themes import Theme


class SearchBar(Vertical):
    DEFAULT_CSS = """
    SearchBar {
        dock: top;
        height: auto;
        max-height: 70%;
        padding: 1 2;
        border-bottom: solid $border;
    }
    SearchBar > .search-summary {
        color: $text-muted;
        padding: 1 0;
    }
    SearchBar Input { margin-bottom: 1; }
    """

    class SearchSubmitted(Message):
        def __init__(self, query: str) -> None:
            super().__init__()
            self.query = query

    class ResultActivated(Message):
        def __init__(self, block_id: str | None, page: int | None) -> None:
            super().__init__()
            self.block_id = block_id
            self.page = page

    def __init__(self, theme: Theme, **kwargs) -> None:
        super().__init__(**kwargs)
        self.theme = theme
        self._results: list[SearchResult] = []

    def compose(self):
        yield Input(placeholder="Search this document…", id="search-input")
        yield Static("", classes="search-summary", id="search-summary")
        yield ListView(id="search-results")

    def on_mount(self) -> None:
        self.styles.background = self.theme.surface
        self.styles.border_bottom = ("solid", self.theme.border)

    def focus_input(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value.strip():
            self.post_message(self.SearchSubmitted(event.value.strip()))

    def show_results(self, query: str, results: list[SearchResult]) -> None:
        self._results = results
        summary = self.query_one("#search-summary", Static)
        summary.update(f"{len(results)} result{'s' if len(results) != 1 else ''} for \"{query}\"")

        list_view = self.query_one("#search-results", ListView)
        list_view.clear()
        for r in results[:50]:
            page_label = f"p.{r.page}" if r.page else "—"
            label = f"{page_label}  {r.section_title + '  ' if r.section_title else ''}{r.snippet}"
            list_view.append(ListItem(Static(label)))

        if results:
            list_view.index = 0
            list_view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if 0 <= event.index < len(self._results):
            result = self._results[event.index]
            self.post_message(self.ResultActivated(result.block_id, result.page))
