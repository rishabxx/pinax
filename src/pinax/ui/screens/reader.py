"""The primary reading screen — reader + TOC + status bar + contextual overlays.

Deliberately avoids panel overload (brief §70): the AI column is reserved but not rendered
in Phase 1, and TOC/search/command-palette/help only ever occupy space while active.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from textual import events
from textual.containers import Horizontal
from textual.screen import Screen

from ...app.document_service import open_document
from ...app.events import LocationChanged, SectionChanged
from ...app.keybindings import READER_BINDINGS, RESERVED_HINTS
from ...app.state import ReaderViewMode, ReadingContext
from ...config.models import Settings
from ...config.settings import save_settings
from ...documents.models import Document
from ...persistence.repositories import reading_progress as progress_repo
from ...search.lexical import search as run_search
from ..themes import THEMES, get_theme
from ..widgets.ai_panel import AIPanel
from ..widgets.bottom_bar import BottomBar
from ..widgets.command_palette import Command, CommandPalette
from ..widgets.reader_view import ReaderView
from ..widgets.search_bar import SearchBar
from ..widgets.sidebar import Sidebar
from ..widgets.top_bar import TopBar

PROGRESS_SAVE_DELAY = 1.2
GG_CHORD_WINDOW = 0.6


class ReaderScreen(Screen):
    BINDINGS = READER_BINDINGS

    def __init__(
        self,
        path: str,
        conn,
        cache_dir: Path,
        settings: Settings,
        *,
        initial_page: int | None = None,
        initial_search: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.path = path
        self.conn = conn
        self.cache_dir = cache_dir
        self.settings = settings
        self.theme = get_theme(settings.reader.theme)
        self.document: Document | None = None
        self.reading_context: ReadingContext | None = None
        self.focus_mode = False
        self._last_g_press = 0.0
        self._progress_timer = None
        self._last_progress_write = time.monotonic()
        self._search_results: list = []
        self._search_index = -1
        self._initial_page = initial_page
        self._initial_search = initial_search

    def compose(self):
        yield TopBar(self.theme, id="top-bar")
        with Horizontal(id="body"):
            yield Sidebar(self.theme, id="toc-panel")
            yield ReaderView(self.theme, reading_width=self.settings.reader.width, id="reader-view")
            yield AIPanel(self.theme, id="ai-panel")
        yield BottomBar(self.theme, id="bottom-bar")

    async def on_mount(self) -> None:
        self.styles.background = self.theme.background
        if not self.settings.reader.show_toc:
            self.query_one("#toc-panel", Sidebar).display = False
        if not self.settings.reader.show_agent:
            self.query_one("#ai-panel", AIPanel).display = False
        await self._open_document()

    async def _open_document(self) -> None:
        self.query_one("#top-bar", TopBar).update_status(doc_title="Loading…")
        document = await asyncio.to_thread(open_document, self.path, self.conn, self.cache_dir)
        self.document = document

        self.query_one("#toc-panel", Sidebar).load_document(document)

        progress = progress_repo.get(self.conn, document.id)
        initial_block = progress.block_id if progress else None
        if self._initial_page is not None:
            page_blocks = sorted(
                (b for b in document.blocks if b.source_page == self._initial_page), key=lambda b: b.order
            )
            if page_blocks:
                initial_block = page_blocks[0].id

        reader = self.query_one("#reader-view", ReaderView)
        await reader.load_document(document, initial_block_id=initial_block)

        self.reading_context = ReadingContext(
            document_id=document.id,
            current_page=progress.page if progress else None,
            current_section_id=progress.section_id if progress else None,
        )
        self._refresh_status_bar()

        if self._initial_search:
            await self.action_open_search()
            self.on_search_bar_search_submitted(SearchBar.SearchSubmitted(self._initial_search))
            self.query_one("#search-bar", SearchBar).query_one("Input").value = self._initial_search
        else:
            reader.focus()

    # -- location / progress -------------------------------------------------

    def on_location_changed(self, message: LocationChanged) -> None:
        if self.reading_context is None:
            return
        self.reading_context.cursor_block_id = message.block_id
        self.reading_context.current_page = message.page
        self.reading_context.current_section_id = message.section_id
        self._refresh_status_bar()
        self._schedule_progress_save()

    def on_section_changed(self, message: SectionChanged) -> None:
        self.query_one("#toc-panel", Sidebar).highlight_section(message.section_id)

    def _refresh_status_bar(self) -> None:
        if self.document is None or self.reading_context is None:
            return
        reader = self.query_one("#reader-view", ReaderView)
        cursor_id = self.reading_context.cursor_block_id
        percent = 0.0
        if cursor_id and reader.block_count:
            idx = reader._flat_blocks_index(cursor_id)
            percent = idx / max(1, reader.block_count - 1)

        self.query_one("#top-bar", TopBar).update_status(
            doc_title=self.document.title,
            page=self.reading_context.current_page,
            page_count=self.document.page_count,
            percent=percent,
            reading_width=self.settings.reader.width,
            mode=reader.view_mode.value,
        )

    def _schedule_progress_save(self) -> None:
        if self._progress_timer is not None:
            self._progress_timer.stop()
        self._progress_timer = self.set_timer(PROGRESS_SAVE_DELAY, self._save_progress)

    def _save_progress(self) -> None:
        if self.document is None or self.reading_context is None:
            return
        now = time.monotonic()
        elapsed = max(0, int(now - self._last_progress_write))
        self._last_progress_write = now
        reader = self.query_one("#reader-view", ReaderView)
        cursor_id = self.reading_context.cursor_block_id
        percent = 0.0
        if cursor_id and reader.block_count:
            percent = reader._flat_blocks_index(cursor_id) / max(1, reader.block_count - 1)
        progress_repo.upsert(
            self.conn,
            document_id=self.document.id,
            block_id=cursor_id,
            page=self.reading_context.current_page,
            section_id=self.reading_context.current_section_id,
            scroll_offset=self.query_one("#reader-view", ReaderView).scroll_y,
            progress=percent,
            reading_time_delta_s=elapsed,
        )

    # -- chords ----------------------------------------------------------------

    def on_key(self, event: events.Key) -> None:
        if event.key == "g":
            now = time.monotonic()
            if now - self._last_g_press < GG_CHORD_WINDOW:
                self._last_g_press = 0.0
                self.query_one("#reader-view", ReaderView).action_goto_start()
                event.stop()
            else:
                self._last_g_press = now

    # -- scrolling actions (delegate to ReaderView) -----------------------------

    def action_scroll_down_line(self) -> None:
        self.query_one("#reader-view", ReaderView).action_scroll_down_line()

    def action_scroll_up_line(self) -> None:
        self.query_one("#reader-view", ReaderView).action_scroll_up_line()

    def action_half_page_down(self) -> None:
        self.query_one("#reader-view", ReaderView).action_half_page_down()

    def action_half_page_up(self) -> None:
        self.query_one("#reader-view", ReaderView).action_half_page_up()

    def action_page_down(self) -> None:
        self.query_one("#reader-view", ReaderView).action_page_down()

    def action_page_up(self) -> None:
        self.query_one("#reader-view", ReaderView).action_page_up()

    def action_goto_end(self) -> None:
        self.query_one("#reader-view", ReaderView).action_goto_end()

    # -- page / section navigation ---------------------------------------------

    def action_prev_source_page(self) -> None:
        self._jump_to_page(delta=-1)

    def action_next_source_page(self) -> None:
        self._jump_to_page(delta=1)

    def _jump_to_page(self, delta: int) -> None:
        if self.document is None or self.reading_context is None:
            return
        current = self.reading_context.current_page
        if current is None:
            return
        target_page = current + delta
        candidates = sorted(
            (b for b in self.document.blocks if b.source_page == target_page),
            key=lambda b: b.order,
        )
        if candidates:
            self.run_worker(self.query_one("#reader-view", ReaderView).jump_to_block(candidates[0].id))

    def action_next_section(self) -> None:
        self._jump_section(delta=1)

    def action_prev_section(self) -> None:
        self._jump_section(delta=-1)

    def _jump_section(self, delta: int) -> None:
        if self.document is None or self.reading_context is None:
            return
        sections = sorted(self.document.sections, key=lambda s: s.order)
        if not sections:
            return
        current_id = self.reading_context.current_section_id
        idx = next((i for i, s in enumerate(sections) if s.id == current_id), 0)
        target = idx + delta
        if 0 <= target < len(sections):
            self.run_worker(self.query_one("#reader-view", ReaderView).jump_to_section(sections[target].id))

    # -- search ------------------------------------------------------------------

    async def action_open_search(self) -> None:
        if self.query("SearchBar"):
            return
        bar = SearchBar(self.theme, id="search-bar")
        await self.mount(bar)
        bar.focus_input()

    def on_search_bar_search_submitted(self, message: SearchBar.SearchSubmitted) -> None:
        if self.document is None:
            return
        results = run_search(self.conn, self.document.id, message.query)
        self._search_results = results
        self._search_index = -1
        bar = self.query_one("#search-bar", SearchBar)
        bar.show_results(message.query, results)
        self.query_one("#top-bar", TopBar).update_status(
            search_info=f"search: {message.query}  {len(results)} results"
        )

    def on_search_bar_result_activated(self, message: SearchBar.ResultActivated) -> None:
        if message.block_id:
            self.run_worker(self.query_one("#reader-view", ReaderView).jump_to_block(message.block_id))
        self._close_search()

    def action_search_next(self) -> None:
        self._cycle_search(1)

    def action_search_prev(self) -> None:
        self._cycle_search(-1)

    def _cycle_search(self, delta: int) -> None:
        if not self._search_results:
            return
        self._search_index = (self._search_index + delta) % len(self._search_results)
        result = self._search_results[self._search_index]
        if result.block_id:
            self.run_worker(self.query_one("#reader-view", ReaderView).jump_to_block(result.block_id))
        self.query_one("#top-bar", TopBar).update_status(
            search_info=f"{self._search_index + 1}/{len(self._search_results)}  [n]"
        )

    def _close_search(self) -> None:
        for bar in self.query("SearchBar"):
            bar.remove()
        self.query_one("#top-bar", TopBar).update_status(search_info="")
        self.query_one("#reader-view", ReaderView).focus()

    # -- TOC / focus mode / page mode --------------------------------------------

    def action_toggle_toc(self) -> None:
        panel = self.query_one("#toc-panel", Sidebar)
        panel.display = not panel.display

    def action_toggle_ai_panel(self) -> None:
        panel = self.query_one("#ai-panel", AIPanel)
        panel.display = not panel.display

    def action_toggle_focus_mode(self) -> None:
        self.focus_mode = not self.focus_mode
        self.query_one("#top-bar", TopBar).display = not self.focus_mode
        self.query_one("#bottom-bar", BottomBar).display = not self.focus_mode
        toc = self.query_one("#toc-panel", Sidebar)
        ai = self.query_one("#ai-panel", AIPanel)
        reader = self.query_one("#reader-view", ReaderView)
        reader.set_centered(self.focus_mode)
        if self.focus_mode:
            self._toc_was_visible = toc.display
            self._ai_was_visible = ai.display
            toc.display = False
            ai.display = False
        else:
            toc.display = getattr(self, "_toc_was_visible", self.settings.reader.show_toc)
            ai.display = getattr(self, "_ai_was_visible", self.settings.reader.show_agent)

    def action_toggle_page_mode(self) -> None:
        reader = self.query_one("#reader-view", ReaderView)
        new_mode = ReaderViewMode.SOURCE_PAGE if reader.view_mode == ReaderViewMode.REFLOW else ReaderViewMode.REFLOW
        reader.set_view_mode(new_mode)
        self._refresh_status_bar()
        self.notify(f"View mode: {new_mode.value.replace('_', ' ')}")

    # -- command palette / help / file picker -------------------------------------

    async def action_open_command_palette(self) -> None:
        if self.query("CommandPalette"):
            return
        palette = CommandPalette(self.theme, self._build_commands(), id="command-palette")
        await self.mount(palette)
        palette.focus_input()

    def _build_commands(self) -> list[Command]:
        commands = [
            Command("search", "Search document", self.action_open_search),
            Command("toggle-toc", "Toggle table of contents", self.action_toggle_toc),
            Command("toggle-ai-panel", "Toggle AI panel", self.action_toggle_ai_panel),
            Command("focus-mode", "Toggle focus mode", self.action_toggle_focus_mode),
            Command("page-mode", "Toggle source page mode", self.action_toggle_page_mode),
            Command("goto-start", "Go to beginning", lambda: self.query_one("#reader-view", ReaderView).action_goto_start()),
            Command("goto-end", "Go to end", lambda: self.query_one("#reader-view", ReaderView).action_goto_end()),
            Command("open-file", "Open another document", self.action_open_file_picker),
            Command("help", "Show keyboard shortcuts", self.action_open_help),
            Command("library", "Back to library", self.action_back_to_library),
        ]
        for key in THEMES:
            theme = THEMES[key]
            commands.append(Command(f"theme-{key}", f"Theme: {theme.name}", lambda k=key: self.action_set_theme(k)))
        return commands

    def on_command_palette_command_activated(self, message: CommandPalette.CommandActivated) -> None:
        commands = {c.id: c for c in self._build_commands()}
        self._close_palette()
        command = commands.get(message.command_id)
        if command is None:
            return
        result = command.handler()
        if asyncio.iscoroutine(result):
            self.run_worker(result)

    def _close_palette(self) -> None:
        for palette in self.query("CommandPalette"):
            palette.remove()
        self.query_one("#reader-view", ReaderView).focus()

    def action_open_help(self) -> None:
        from .help import HelpScreen

        self.app.push_screen(HelpScreen(self.theme))

    def action_open_file_picker(self) -> None:
        from .file_picker import FilePickerScreen

        def on_selected(path: str | None) -> None:
            if path:
                self.app.open_document_path(path)

        self.app.push_screen(FilePickerScreen(self.theme), on_selected)

    def action_back_to_library(self) -> None:
        self.app.pop_screen()

    # -- themes -------------------------------------------------------------------

    def action_set_theme(self, name: str) -> None:
        self.theme = get_theme(name)
        self.settings.reader.theme = name
        save_settings(self.settings)

        self.styles.background = self.theme.background
        self.query_one("#top-bar", TopBar).apply_theme(self.theme)
        self.query_one("#bottom-bar", BottomBar).apply_theme(self.theme)
        self.query_one("#toc-panel", Sidebar).apply_theme(self.theme)
        self.query_one("#ai-panel", AIPanel).apply_theme(self.theme)

        reader = self.query_one("#reader-view", ReaderView)
        reader.theme = self.theme
        self.run_worker(reader._rebuild_window())
        self._refresh_status_bar()
        self.notify(f"Theme: {self.theme.name}")

    # -- AI panel (Phase 2 not implemented — see AIPanel) --------------------------

    def on_ai_panel_question_submitted(self, message: AIPanel.QuestionSubmitted) -> None:
        self.notify(RESERVED_HINTS["reserved_ai"])

    # -- reserved (Phase 2/4) -----------------------------------------------------

    def action_reserved_ai(self) -> None:
        panel = self.query_one("#ai-panel", AIPanel)
        panel.display = True
        panel.query_one("#ai-input").focus()

    def action_reserved_bookmark(self) -> None:
        self.notify(RESERVED_HINTS["reserved_bookmark"])

    def action_reserved_notes(self) -> None:
        self.notify(RESERVED_HINTS["reserved_notes"])

    # -- overlay dismissal --------------------------------------------------------

    def action_close_overlay(self) -> None:
        from .library import LibraryScreen

        if self.query("SearchBar"):
            self._close_search()
        elif self.query("CommandPalette"):
            self._close_palette()
        elif self.focus_mode:
            self.action_toggle_focus_mode()
        elif len(self.app.screen_stack) > 1 and isinstance(self.app.screen_stack[-2], LibraryScreen):
            self.app.pop_screen()
        else:
            self.app.exit()
