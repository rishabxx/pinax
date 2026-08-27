"""AI context panel (Phase 2).

Deliberately dumb: this widget never talks to a provider or builds context itself (brief
§92: "LLM calls directly from widgets" is exactly the anti-pattern the layer boundaries
exist to prevent). `ReaderScreen` owns the provider call and drives this widget through
`start_turn` / `append_chunk` / `finish_turn` / `show_error`.
"""

from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Input, ListItem, ListView, Static

from ...intelligence.citations import Citation
from ..themes import Theme


def _render_answer(text: str, citations: list[Citation], theme: Theme) -> Text:
    rendered = Text(text, style=theme.foreground)
    for citation in citations:
        start = rendered.plain.find(citation.raw)
        if start != -1:
            rendered.stylize(f"bold {theme.accent}", start, start + len(citation.raw))
    return rendered


class AIPanel(Vertical):
    DEFAULT_CSS = """
    AIPanel {
        width: 46;
        border-left: solid $border;
        padding: 1 2;
    }
    AIPanel > .ai-header { height: 1; }
    AIPanel > #ai-log { height: 1fr; }
    AIPanel > #ai-log > Static { margin-bottom: 1; }
    AIPanel > #ai-sources { height: auto; max-height: 8; }
    AIPanel > .ai-ask-label { padding-top: 1; text-style: bold; }
    AIPanel Input { margin-top: 1; }
    """

    class QuestionSubmitted(Message, namespace="ai_panel"):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class SourceActivated(Message, namespace="ai_panel"):
        def __init__(self, citation: Citation) -> None:
            super().__init__()
            self.citation = citation

    class CancelRequested(Message, namespace="ai_panel"):
        pass

    def __init__(self, theme: Theme, **kwargs) -> None:
        super().__init__(**kwargs)
        self.theme = theme
        self.online = False
        self.streaming = False
        self._answer_widget: Static | None = None
        self._answer_buffer = ""
        self._citations: list[Citation] = []

    def compose(self):
        yield Static(self._header_text(), classes="ai-header")
        yield VerticalScroll(id="ai-log")
        yield ListView(id="ai-sources")
        yield Static("ASK ABOUT THIS PAGE", classes="ai-ask-label")
        yield Input(placeholder="Ask a question about this page…", id="ai-input")

    def on_mount(self) -> None:
        self.styles.background = self.theme.surface
        self.styles.border_left = ("solid", self.theme.border)
        self.query_one("#ai-sources", ListView).display = False
        if not self.online:
            self._show_offline_notice()

    def apply_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.styles.background = theme.surface
        self.styles.border_left = ("solid", theme.border)
        self.query_one(".ai-header", Static).update(self._header_text())

    def set_online(self, online: bool) -> None:
        self.online = online
        self.query_one(".ai-header", Static).update(self._header_text())
        if not online:
            self._show_offline_notice()

    def _header_text(self) -> Text:
        text = Text()
        text.append("AI CONTEXT", style=f"bold {self.theme.foreground}")
        text.append("   ")
        if self.online:
            text.append("● ONLINE", style="bold #4ade80")
        else:
            text.append("● OFFLINE", style=f"bold {self.theme.muted}")
        return text

    def _show_offline_notice(self) -> None:
        log = self.query_one("#ai-log", VerticalScroll)
        log.remove_children()
        text = Text()
        text.append("No AI provider configured.\n\n", style=self.theme.foreground)
        text.append("The reader is fully usable without it. Run ", style=self.theme.muted)
        text.append("pinax config", style=f"bold {self.theme.accent}")
        text.append(" to set one up once the AI assistant ships.", style=self.theme.muted)
        log.mount(Static(text))

    # -- turn lifecycle, driven entirely by ReaderScreen --------------------------

    def load_history(self, messages) -> None:
        if not messages:
            return
        log = self.query_one("#ai-log", VerticalScroll)
        log.remove_children()
        for msg in messages:
            log.mount(Static(Text(f"You: {msg.question}", style=f"bold {self.theme.foreground}")))
            answer = Text("AI: ", style=self.theme.muted)
            answer.append(msg.answer, style=self.theme.foreground)
            log.mount(Static(answer))
        log.scroll_end(animate=False)

    def start_turn(self, question: str) -> None:
        self.streaming = True
        self._answer_buffer = ""
        self._citations = []
        log = self.query_one("#ai-log", VerticalScroll)
        log.mount(Static(Text(f"You: {question}", style=f"bold {self.theme.foreground}")))
        self._answer_widget = Static(Text("AI: ", style=self.theme.muted))
        log.mount(self._answer_widget)
        log.scroll_end(animate=False)
        self.query_one("#ai-sources", ListView).display = False

    def append_chunk(self, text: str) -> None:
        if self._answer_widget is None:
            return
        self._answer_buffer += text
        rendered = Text("AI: ", style=self.theme.muted)
        rendered.append_text(_render_answer(self._answer_buffer, self._citations, self.theme))
        self._answer_widget.update(rendered)
        self.query_one("#ai-log", VerticalScroll).scroll_end(animate=False)

    def finish_turn(self, citations: list[Citation]) -> None:
        self.streaming = False
        self._citations = citations
        if self._answer_widget is not None:
            rendered = Text("AI: ", style=self.theme.muted)
            rendered.append_text(_render_answer(self._answer_buffer, citations, self.theme))
            self._answer_widget.update(rendered)
        self._answer_widget = None

        sources = self.query_one("#ai-sources", ListView)
        sources.clear()
        if citations:
            for citation in citations:
                sources.append(ListItem(Static(Text(f"→ {citation.label}", style=self.theme.accent))))
            sources.display = True
        else:
            sources.display = False

    def show_error(self, message: str) -> None:
        self.streaming = False
        log = self.query_one("#ai-log", VerticalScroll)
        if self._answer_widget is not None:
            self._answer_widget.update(Text(f"AI: {self._answer_buffer}", style=self.theme.muted))
            self._answer_widget = None
        log.mount(Static(Text(f"⚠ {message}", style="bold #f87171")))
        log.scroll_end(animate=False)

    def cancelled(self) -> None:
        self.streaming = False
        if self._answer_widget is not None:
            note = Text("AI: ", style=self.theme.muted)
            note.append_text(_render_answer(self._answer_buffer, self._citations, self.theme))
            note.append(" [cancelled]", style=f"italic {self.theme.muted}")
            self._answer_widget.update(note)
            self._answer_widget = None

    # -- input handling -------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.streaming:
            return
        if event.value.strip():
            self.post_message(self.QuestionSubmitted(event.value.strip()))
            event.input.value = ""

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if 0 <= event.index < len(self._citations):
            self.post_message(self.SourceActivated(self._citations[event.index]))

    def focus_input(self) -> None:
        self.query_one("#ai-input", Input).focus()
