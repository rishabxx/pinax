"""Fuzzy-searchable command palette (brief §15)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, ListItem, ListView, Static

from ..themes import Theme


@dataclass
class Command:
    id: str
    title: str
    handler: Callable[[], None]


def _fuzzy_score(query: str, text: str) -> int | None:
    """Very small subsequence fuzzy matcher: returns a score (lower is better) or None."""
    query = query.lower()
    text_lower = text.lower()
    if not query:
        return 0
    pos = 0
    first_match = None
    last_match = 0
    for ch in query:
        pos = text_lower.find(ch, pos)
        if pos == -1:
            return None
        if first_match is None:
            first_match = pos
        last_match = pos
        pos += 1
    return last_match - (first_match or 0)


class CommandPalette(Vertical):
    DEFAULT_CSS = """
    CommandPalette {
        dock: top;
        height: auto;
        max-height: 60%;
        padding: 1 2;
        border-bottom: solid $border;
    }
    CommandPalette Input { margin-bottom: 1; }
    """

    class CommandActivated(Message):
        def __init__(self, command_id: str) -> None:
            super().__init__()
            self.command_id = command_id

    def __init__(self, theme: Theme, commands: list[Command], **kwargs) -> None:
        super().__init__(**kwargs)
        self.theme = theme
        self.commands = commands
        self._filtered: list[Command] = list(commands)

    def compose(self):
        yield Input(placeholder="Type a command…", id="palette-input")
        yield ListView(id="palette-results")

    def on_mount(self) -> None:
        self.styles.background = self.theme.surface
        self.styles.border_bottom = ("solid", self.theme.border)
        self._render_results()

    def focus_input(self) -> None:
        self.query_one("#palette-input", Input).focus()
        self.query_one("#palette-input", Input).value = ""
        self._filtered = list(self.commands)
        self._render_results()

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value
        scored = []
        for cmd in self.commands:
            score = _fuzzy_score(query, cmd.title)
            if score is not None:
                scored.append((score, cmd))
        scored.sort(key=lambda pair: pair[0])
        self._filtered = [cmd for _, cmd in scored] if query else list(self.commands)
        self._render_results()

    def _render_results(self) -> None:
        list_view = self.query_one("#palette-results", ListView)
        list_view.clear()
        for cmd in self._filtered[:20]:
            list_view.append(ListItem(Static(cmd.title)))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._filtered:
            self.post_message(self.CommandActivated(self._filtered[0].id))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if 0 <= event.index < len(self._filtered):
            self.post_message(self.CommandActivated(self._filtered[event.index].id))
