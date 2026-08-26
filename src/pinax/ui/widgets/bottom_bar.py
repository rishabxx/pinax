"""Bottom key-hint bar — colored key badges, replacing Textual's plain-text Footer
(brief §46: hints should change with context, and read as a designed strip, not a wall
of gray text)."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from ..themes import Theme

DEFAULT_HINTS: list[tuple[str, str]] = [
    ("q", "Quit"),
    ("j/k", "Scroll"),
    ("h/l", "Page"),
    ("[/]", "Section"),
    ("/", "Search"),
    ("t", "TOC"),
    ("z", "Focus"),
    (":", "Commands"),
    ("?", "Help"),
]


class BottomBar(Static):
    DEFAULT_CSS = """
    BottomBar {
        height: 1;
        padding: 0 1;
        content-align: left middle;
    }
    """

    def __init__(self, theme: Theme, **kwargs) -> None:
        super().__init__(**kwargs)
        self.theme = theme
        self.hints = DEFAULT_HINTS
        self.right_text = ""
        self.styles.background = theme.surface

    def apply_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.styles.background = theme.surface
        self._refresh()

    def set_hints(self, hints: list[tuple[str, str]]) -> None:
        self.hints = hints
        self._refresh()

    def set_right_text(self, text: str) -> None:
        self.right_text = text
        self._refresh()

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        t = self.theme
        text = Text()
        for key, label in self.hints:
            text.append(f" {key} ", style=f"bold {t.background} on {t.muted}")
            text.append(f" {label}  ", style=t.foreground)

        if self.right_text:
            width = self.size.width or 100
            used = len(text.plain)
            pad = max(1, width - used - len(self.right_text) - 1)
            text.append(" " * pad)
            text.append(self.right_text, style=t.muted)

        self.update(text)
