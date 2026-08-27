"""TUI-level test for the Phase 2 ask-AI flow, using a fake provider so no network/API key
is needed (brief §80: use Textual's testing facilities; brief §92: providers are swappable)."""

from __future__ import annotations

from pinax.app.app import PinaxApp
from pinax.ui.widgets.ai_panel import AIPanel


class _FakeProvider:
    async def chat(self, messages, *, model, temperature=0.3, max_tokens=None):
        for chunk in ["The dominant approach ", "uses recurrence ", "[p.1 · §1 Introduction]."]:
            yield chunk


async def test_ask_ai_streams_answer_and_persists(isolated_home, md_file, monkeypatch):
    monkeypatch.setattr("pinax.ui.screens.reader.get_provider", lambda config: _FakeProvider())

    app = PinaxApp(initial_path=str(md_file))
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        screen = app.screen
        screen.settings.ai.enabled = True
        screen.settings.ai.provider = "ollama"
        screen.settings.ai.model = "fake-model"

        panel = screen.query_one("#ai-panel", AIPanel)
        panel.query_one("#ai-input").focus()
        for ch in "what approach is used":
            await pilot.press("space" if ch == " " else ch)
        await pilot.press("enter")
        await pilot.pause(0.3)

        assert not panel.streaming
        assert "uses recurrence" in panel._answer_buffer

        from pinax.persistence.repositories import ai_messages as ai_messages_repo

        history = ai_messages_repo.list_for_document(screen.conn, screen.document.id)
        assert len(history) == 1
        assert history[0].question == "what approach is used"
        assert "p.1" in history[0].sources[0]
    app.conn.close()


async def test_ask_ai_without_provider_configured_shows_hint(isolated_home, md_file):
    app = PinaxApp(initial_path=str(md_file))
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        screen = app.screen
        assert screen.settings.ai.enabled is False

        panel = screen.query_one("#ai-panel", AIPanel)
        panel.query_one("#ai-input").focus()
        for ch in "hello":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause(0.2)

        assert not panel.streaming
        assert panel._answer_buffer == ""
    app.conn.close()
