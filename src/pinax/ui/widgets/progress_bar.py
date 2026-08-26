"""Small horizontal progress bar used in the library screen (brief §19)."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from ..themes import Theme


class ReadingProgressBar(Static):
    def __init__(self, percent: float, theme: Theme, width: int = 28, **kwargs) -> None:
        super().__init__(**kwargs)
        self.percent = max(0.0, min(1.0, percent))
        self.theme = theme
        self.bar_width = width

    def render(self) -> Text:
        filled = round(self.percent * self.bar_width)
        text = Text()
        text.append("█" * filled, style=self.theme.accent)
        text.append("░" * (self.bar_width - filled), style=self.theme.border)
        text.append(f"  {self.percent:.0%}", style=self.theme.muted)
        return text
