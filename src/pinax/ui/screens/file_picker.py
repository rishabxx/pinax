"""Terminal file picker (brief §59), built on Textual's DirectoryTree."""

from __future__ import annotations

from pathlib import Path

from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DirectoryTree, Static

from ...documents.parser import SUPPORTED_SUFFIXES
from ..themes import Theme


class DocumentDirectoryTree(DirectoryTree):
    def filter_paths(self, paths):
        return [
            p for p in paths if p.is_dir() or p.suffix.lower() in SUPPORTED_SUFFIXES
        ]


class FilePickerScreen(Screen[str]):
    BINDINGS = [("escape,q", "dismiss_empty", "Cancel")]

    def __init__(self, theme: Theme, start_dir: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.theme = theme
        self.start_dir = start_dir or str(Path.home())

    def compose(self):
        with Vertical(id="picker-body"):
            yield Static("OPEN A DOCUMENT", id="picker-title")
            yield DocumentDirectoryTree(self.start_dir, id="picker-tree")

    def on_mount(self) -> None:
        self.styles.background = self.theme.background
        self.query_one("#picker-body").styles.padding = (1, 2)
        self.query_one("#picker-title").styles.color = self.theme.heading_color(1)
        self.query_one("#picker-title").styles.text_style = "bold"

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.dismiss(str(event.path))

    def action_dismiss_empty(self) -> None:
        self.dismiss(None)
