"""Top status bar — colored badges instead of plain text (matches the reference design)."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from ..themes import Theme

_CHIP_TEXT = "#0a0a0a"  # dark text reads on every theme's bright accent colors


def _chip(label: str, value: str, bg: str) -> Text:
    content = f" {label} {value} " if value else f" {label} "
    return Text(content, style=f"bold {_CHIP_TEXT} on {bg}")


class TopBar(Static):
    DEFAULT_CSS = """
    TopBar {
        height: 1;
        padding: 0 1;
        content-align: left middle;
    }
    """

    def __init__(self, theme: Theme, **kwargs) -> None:
        super().__init__(**kwargs)
        self.theme = theme
        self.doc_title = ""
        self.page: int | None = None
        self.page_count: int | None = None
        self.percent = 0.0
        self.reading_width: int | str = 86
        self.mode = "reflow"
        self.search_info = ""
        self.styles.background = theme.surface

    def apply_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.styles.background = theme.surface
        self._refresh()

    def update_status(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)
        self._refresh()

    def _refresh(self) -> None:
        t = self.theme
        text = Text()
        text.append(" pinax ", style=f"bold {t.accent}")
        text.append(" › ", style=t.muted)
        text.append(self.doc_title or "—", style=f"bold {t.foreground}")
        text.append("   ")

        if self.page and self.page_count:
            text.append_text(_chip("PAGE", f"{self.page} / {self.page_count}", t.heading_color(3)))
            text.append(" ")
        text.append_text(_chip("PROGRESS", f"{self.percent:.0%}", t.accent))
        text.append(" ")
        width_label = "auto" if self.reading_width == "auto" else str(self.reading_width)
        text.append_text(_chip("WIDTH", width_label, t.heading_color(2)))
        text.append(" ")
        text.append_text(_chip("MODE", self.mode.replace("_", " ").upper(), t.heading_color(4)))

        if self.search_info:
            width = self.size.width or 100
            used = len(text.plain)
            pad = max(1, width - used - len(self.search_info) - 3)
            text.append(" " * pad)
            text.append(self.search_info, style=f"bold {t.quote_color}")

        self.update(text)
