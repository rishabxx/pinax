"""AI context panel — visual scaffolding for Phase 2 (brief §67: the reader stays fully
usable with AI "not configured"; this panel is honest about that rather than faking answers).

Reserved space matches the reference layout (right-hand column), but shows a real "not
configured" state instead of fabricated page summaries — no AI backend exists yet.
"""

from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, Static

from ..themes import Theme


class AIPanel(Vertical):
    DEFAULT_CSS = """
    AIPanel {
        width: 46;
        border-left: solid $border;
        padding: 1 2;
    }
    AIPanel > .ai-header { height: 1; }
    AIPanel > .ai-body { height: 1fr; }
    AIPanel > .ai-ask-label { padding-top: 1; text-style: bold; }
    AIPanel Input { margin-top: 1; }
    """

    class QuestionSubmitted(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def __init__(self, theme: Theme, **kwargs) -> None:
        super().__init__(**kwargs)
        self.theme = theme

    def compose(self):
        yield Static(self._header_text(), classes="ai-header")
        yield Static(self._body_text(), classes="ai-body", id="ai-body")
        yield Static("ASK ABOUT THIS PAGE", classes="ai-ask-label")
        yield Input(placeholder="Ask a question about this page…", id="ai-input")

    def on_mount(self) -> None:
        self.styles.background = self.theme.surface
        self.styles.border_left = ("solid", self.theme.border)

    def apply_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.styles.background = theme.surface
        self.styles.border_left = ("solid", theme.border)
        self.query_one(".ai-header", Static).update(self._header_text())
        self.query_one("#ai-body", Static).update(self._body_text())

    def _header_text(self) -> Text:
        text = Text()
        text.append("AI CONTEXT", style=f"bold {self.theme.foreground}")
        text.append("   ")
        text.append("● OFFLINE", style=f"bold {self.theme.muted}")
        return text

    def _body_text(self) -> Text:
        text = Text()
        text.append("No AI provider configured.\n\n", style=self.theme.foreground)
        text.append(
            "The reader is fully usable without it. Run ",
            style=self.theme.muted,
        )
        text.append("tr config", style=f"bold {self.theme.accent}")
        text.append(" to set one up once the AI assistant ships.", style=self.theme.muted)
        return text

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value.strip():
            self.post_message(self.QuestionSubmitted(event.value.strip()))
            event.input.value = ""
