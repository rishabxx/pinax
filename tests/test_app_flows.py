"""TUI interaction tests via Textual's Pilot (brief §80: "use Textual's testing facilities")."""

from __future__ import annotations

from pinax.app.app import PinaxApp
from pinax.ui.screens.library import LibraryScreen
from pinax.ui.screens.reader import ReaderScreen
from pinax.ui.widgets.command_palette import CommandPalette
from pinax.ui.widgets.reader_view import ReaderView
from pinax.ui.widgets.search_bar import SearchBar


async def test_opening_a_document_shows_reader_screen(isolated_home, md_file):
    app = PinaxApp(initial_path=str(md_file))
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        assert isinstance(app.screen, ReaderScreen)
        assert app.screen.document.title == "Attention Is All You Need"
    app.conn.close()


async def test_library_opens_when_no_path_given(isolated_home):
    app = PinaxApp()
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        assert isinstance(app.screen, LibraryScreen)
    app.conn.close()


async def test_scrolling_moves_cursor_forward(isolated_home, big_md_file):
    app = PinaxApp(initial_path=str(big_md_file))
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        reader = app.screen.query_one("#reader-view", ReaderView)
        start_idx = reader._flat_blocks_index(app.screen.reading_context.cursor_block_id)
        for _ in range(5):
            await pilot.press("space")
        await pilot.pause(0.3)
        end_idx = reader._flat_blocks_index(app.screen.reading_context.cursor_block_id)
        assert end_idx > start_idx
    app.conn.close()


async def test_goto_end_and_start(isolated_home, big_md_file):
    app = PinaxApp(initial_path=str(big_md_file))
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        reader = app.screen.query_one("#reader-view", ReaderView)
        await pilot.press("G")
        await pilot.pause(0.3)
        # The very last block can't be scrolled all the way to the top of the viewport
        # (there's no more content below it to fill the rest of the screen), so "at the
        # end" just means scroll_y advanced and the cursor landed near the last block —
        # exactly how far short of max_scroll_y that lands depends on viewport height.
        assert reader.scroll_y > 0
        assert reader._flat_blocks_index(app.screen.reading_context.cursor_block_id) >= reader.block_count - 15

        await pilot.press("g")
        await pilot.press("g")
        await pilot.pause(0.3)
        assert reader._flat_blocks_index(app.screen.reading_context.cursor_block_id) == 0
    app.conn.close()


async def test_window_stays_bounded_for_large_documents(isolated_home, big_md_file):
    from pinax.ui.widgets.reader_view import MAX_MOUNTED

    app = PinaxApp(initial_path=str(big_md_file))
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        reader = app.screen.query_one("#reader-view", ReaderView)
        await pilot.press("G")
        await pilot.pause(0.3)
        assert (reader._window_end - reader._window_start) <= MAX_MOUNTED
    app.conn.close()


async def test_search_opens_shows_results_and_jumps(isolated_home, md_file):
    app = PinaxApp(initial_path=str(md_file))
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        await pilot.press("/")
        await pilot.pause(0.1)
        assert app.screen.query("SearchBar")

        for ch in "attention":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause(0.3)

        bar = app.screen.query_one("#search-bar", SearchBar)
        assert len(bar._results) > 0

        await pilot.press("enter")
        await pilot.pause(0.2)
        assert not app.screen.query("SearchBar")
        assert app.focused is app.screen.query_one("#reader-view", ReaderView)
    app.conn.close()


async def test_command_palette_toggle_focus_mode(isolated_home, md_file):
    app = PinaxApp(initial_path=str(md_file))
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        await pilot.press(":")
        await pilot.pause(0.1)
        assert app.screen.query("CommandPalette")

        for ch in "focus":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause(0.2)

        assert not app.screen.query("CommandPalette")
        assert app.screen.focus_mode is True
    app.conn.close()


async def test_help_screen_opens_and_closes(isolated_home, md_file):
    app = PinaxApp(initial_path=str(md_file))
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        await pilot.press("?")
        await pilot.pause(0.2)
        assert app.screen.__class__.__name__ == "HelpScreen"

        await pilot.press("q")
        await pilot.pause(0.2)
        assert isinstance(app.screen, ReaderScreen)
    app.conn.close()


async def test_toc_toggle(isolated_home, md_file):
    app = PinaxApp(initial_path=str(md_file))
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        toc = app.screen.query_one("#toc-panel")
        assert toc.display is True
        await pilot.press("t")
        await pilot.pause(0.1)
        assert toc.display is False
    app.conn.close()


async def test_reading_progress_round_trips_across_sessions(isolated_home, big_md_file):
    app1 = PinaxApp(initial_path=str(big_md_file))
    async with app1.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        for _ in range(15):
            await pilot.press("space")
        await pilot.pause(0.3)
        cursor = app1.screen.reading_context.cursor_block_id
        app1.screen._save_progress()
    app1.conn.close()

    app2 = PinaxApp(initial_path=str(big_md_file))
    async with app2.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.3)
        assert app2.screen.reading_context.cursor_block_id == cursor
    app2.conn.close()


async def test_theme_switch_via_command_palette_persists(isolated_home, md_file):
    from pinax.ui.widgets.top_bar import TopBar

    app = PinaxApp(initial_path=str(md_file))
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        assert app.screen.theme.name == "Midnight"

        await pilot.press(":")
        await pilot.pause(0.1)
        for ch in "theme nord":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause(0.2)

        assert app.screen.theme.name == "Nord"
        assert app.screen.query_one("#top-bar", TopBar).theme.name == "Nord"
        assert app.settings.reader.theme == "nord"
    app.conn.close()

    # Reopening a fresh app in the same (isolated) home picks up the persisted theme.
    app2 = PinaxApp(initial_path=str(md_file))
    async with app2.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        assert app2.screen.theme.name == "Nord"
    app2.conn.close()


async def test_pdf_image_block_renders_as_image_widget(isolated_home, tmp_path):
    import pymupdf
    from PIL import Image as PILImage
    import io

    from pinax.ui.widgets.reader_view import _ImageBlockWidget

    img = PILImage.new("RGB", (200, 100), color=(255, 100, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Figure caption test", fontsize=14)
    page.insert_image(pymupdf.Rect(72, 100, 272, 200), stream=buf.getvalue())
    path = tmp_path / "with_image.pdf"
    pdf.save(path)

    app = PinaxApp(initial_path=str(path))
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.3)
        reader = app.screen.query_one("#reader-view", ReaderView)
        image_widgets = [c for c in reader.children if isinstance(c, _ImageBlockWidget)]
        assert len(image_widgets) == 1
    app.conn.close()


async def test_pdf_image_is_re_refreshed_after_mount(isolated_home, tmp_path):
    # Regression: textual-image's Kitty/Sixel widgets request `refresh(layout=True)` as
    # soon as image bytes are assigned in the constructor — before the widget is mounted.
    # A refresh requested pre-mount is lost, so without an explicit post-mount nudge, images
    # silently never actually paint until an unrelated later layout event (e.g. resizing a
    # panel) forces one. This confirms the nudge happens.
    import io

    import pymupdf
    from PIL import Image as PILImage

    from pinax.ui.widgets.reader_view import _ImageBlockWidget

    img = PILImage.new("RGB", (200, 100), color=(255, 100, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_image(pymupdf.Rect(72, 100, 272, 200), stream=buf.getvalue())
    path = tmp_path / "refresh_check.pdf"
    pdf.save(path)

    nudged: list[list] = []
    original_nudge = ReaderView._refresh_images

    def tracking_nudge(self, images):
        nudged.append(images)
        return original_nudge(self, images)

    ReaderView._refresh_images = tracking_nudge
    try:
        app = PinaxApp(initial_path=str(path))
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause(0.3)
            reader = app.screen.query_one("#reader-view", ReaderView)
            image_widgets = [c for c in reader.children if isinstance(c, _ImageBlockWidget)]
            assert len(image_widgets) == 1
            # The post-mount nudge (`_refresh_images`) must have run and included this widget.
            assert any(image_widgets[0] in batch for batch in nudged)
        app.conn.close()
    finally:
        ReaderView._refresh_images = original_nudge


async def test_pdf_page_thumbnails_render(isolated_home, pdf_with_duplicate_outline_pages):
    from pinax.ui.widgets.pages_panel import PagesPanel, _PageThumbnail

    app = PinaxApp(initial_path=str(pdf_with_duplicate_outline_pages))
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.5)
        panel = app.screen.query_one("#pages-panel", PagesPanel)
        thumbnails = [c for c in panel.children if isinstance(c, _PageThumbnail)]
        assert len(thumbnails) == 2
        assert [t.page_number for t in thumbnails] == [1, 2]
    app.conn.close()


async def test_library_shows_recently_opened_document(isolated_home, md_file):
    app = PinaxApp()
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        app.open_document_path(str(md_file))
        await pilot.pause(0.3)
        assert isinstance(app.screen, ReaderScreen)

        await pilot.press("escape")
        await pilot.pause(0.2)
        assert isinstance(app.screen, LibraryScreen)
        assert len(app.screen._records) == 1
        assert app.screen._records[0].path == str(md_file)
    app.conn.close()


async def test_library_lists_all_documents_with_sized_rows(isolated_home, tmp_path):
    # Regression: library rows had no explicit height, so the first entry expanded to
    # fill the whole screen and every document after it rendered entirely off-screen.
    from textual.widgets import ListView

    paths = []
    for i in range(3):
        path = tmp_path / f"doc{i}.md"
        path.write_text(f"# Document {i}\n\nSome content for document {i}.\n")
        paths.append(str(path))

    app = PinaxApp()
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.2)
        for path in paths:
            app.open_document_path(path)
            await pilot.pause(0.2)
            await pilot.press("escape")
            await pilot.pause(0.2)

        assert isinstance(app.screen, LibraryScreen)
        assert len(app.screen._records) == 3

        list_view = app.screen.query_one("#library-list", ListView)
        assert len(list_view.children) == 3
        regions = [c.region for c in list_view.children]
        # Every row must have a real, bounded height (not 0, not filling the screen) and
        # rows must not overlap — each one stacked below the previous.
        assert all(0 < r.height < 10 for r in regions)
        assert regions[1].y > regions[0].y
        assert regions[2].y > regions[1].y
    app.conn.close()
