"""Keyboard shortcut help overlay (brief §13 / `?`)."""

from __future__ import annotations

from rich.text import Text
from textual.containers import Center, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from ...app.keybindings import READER_BINDINGS
from ..themes import Theme

_EXTRA_HELP = [
    ("gg", "Beginning of document"),
    ("G", "End of document"),
    ("j / k", "Scroll down / up"),
    ("Ctrl+d / Ctrl+u", "Half page down / up"),
]


class HelpScreen(Screen):
    BINDINGS = [("escape,q,question_mark", "dismiss", "Close")]

    def __init__(self, theme: Theme, **kwargs) -> None:
        super().__init__(**kwargs)
        self.theme = theme

    def compose(self):
        with Center():
            with VerticalScroll(id="help-body"):
                yield Static(self._build_help_text(), id="help-text")

    def on_mount(self) -> None:
        self.styles.background = self.theme.background
        self.query_one("#help-body").styles.width = 64
        self.query_one("#help-body").styles.padding = (2, 4)

    def _build_help_text(self) -> Text:
        text = Text()
        text.append("KEYBOARD SHORTCUTS\n\n", style=f"bold {self.theme.heading_color(1)}")
        seen = set()
        for key, label in _EXTRA_HELP:
            text.append(f"  {key:<18}", style=self.theme.accent)
            text.append(f"{label}\n", style=self.theme.foreground)
        for binding in READER_BINDINGS:
            if binding.description and binding.description not in seen:
                seen.add(binding.description)
                key_display = binding.key_display or binding.key.split(",")[0]
                text.append(f"  {key_display:<18}", style=self.theme.accent)
                text.append(f"{binding.description}\n", style=self.theme.foreground)
        text.append("\nPress q / Esc to close.", style=self.theme.muted)
        return text

    def action_dismiss(self) -> None:
        self.dismiss()
