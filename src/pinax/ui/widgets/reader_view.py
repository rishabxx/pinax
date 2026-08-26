"""The core reading surface.

Virtualized on purpose (brief §62: "never render the entire document into one giant
widget"): only a window of blocks around the current scroll position is ever mounted. The
window grows as the reader approaches its edges and is trimmed from the trailing edge once
it exceeds MAX_MOUNTED, so a 2,000-page document costs roughly the same to render as a
20-page one.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from rich.text import Text
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widgets import Static
from textual_image.renderable import Image as _AutoImageRenderable
from textual_image.widget import Image as AutoImage

from ...app.events import LocationChanged, SectionChanged
from ...app.logging_setup import get_logger
from ...app.state import ReaderViewMode
from ...documents.models import BlockType, Document, DocumentBlock
from ..images import extract_block_image
from ..rendering import css_class_for, render_block
from ..themes import Theme

BLOCK_MARGIN = 1  # kept in sync with _BlockWidget.DEFAULT_CSS margin-bottom
INITIAL_WINDOW = 220
WINDOW_CHUNK = 120
MAX_MOUNTED = 520
EXTEND_MARGIN = 150  # cells of remaining virtual scroll before we grow the window


class _BlockWidget(Static):
    DEFAULT_CSS = """
    _BlockWidget { margin: 0 0 1 0; }
    _BlockWidget.block-heading-1 { margin: 2 0 1 0; }
    _BlockWidget.block-heading-2 { margin: 2 0 1 0; }
    _BlockWidget.block-heading-3 { margin: 1 0 1 0; }
    _BlockWidget.block-heading-4, _BlockWidget.block-heading-5, _BlockWidget.block-heading-6 { margin: 1 0 1 0; }
    _BlockWidget.block-list_item { margin: 0 0 0 0; }
    _BlockWidget.block-code, _BlockWidget.block-table, _BlockWidget.block-quote { margin: 1 0 1 0; }
    """

    def __init__(self, block: DocumentBlock, renderable, width: int | str):
        super().__init__(renderable, id=block.id, classes=css_class_for(block))
        self.block_id = block.id
        self.source_page = block.source_page
        self.section_id = block.section_id
        self.order = block.order
        if isinstance(width, int):
            self.styles.width = width
            self.styles.max_width = "100%"
        else:
            self.styles.width = "100%"


class _ImageBlockWidget(AutoImage, Renderable=_AutoImageRenderable):
    """A rendered embedded image (Kitty/iTerm2/Sixel/half-cell, whichever the terminal
    supports — `AutoImage` picks automatically). Carries the same `block_id`/`source_page`/
    `section_id` bookkeeping as `_BlockWidget` so the windowing and location-tracking code
    can treat both interchangeably via duck typing (`hasattr(widget, "block_id")`)."""

    DEFAULT_CSS = """
    _ImageBlockWidget { margin: 0 0 1 0; height: auto; }
    """

    def __init__(self, block: DocumentBlock, image_bytes: bytes, width: int | str):
        super().__init__(io.BytesIO(image_bytes), id=block.id)
        self.block_id = block.id
        self.source_page = block.source_page
        self.section_id = block.section_id
        self.order = block.order
        if isinstance(width, int):
            self.styles.width = width
            self.styles.max_width = "100%"
        else:
            self.styles.width = "100%"


class _PageDivider(Static):
    DEFAULT_CSS = """
    _PageDivider { margin: 1 0; color: $text-muted; }
    """

    def __init__(self, page: int, theme: Theme, width: int | str):
        label = f" PAGE {page} "
        rule_len = 24
        text = Text(f"{'─' * rule_len}{label}{'─' * rule_len}", style=theme.muted, justify="center")
        super().__init__(text)
        if isinstance(width, int):
            self.styles.width = width
        else:
            self.styles.width = "100%"


@dataclass
class VisibleState:
    cursor_block_id: str | None = None
    current_page: int | None = None
    current_section_id: str | None = None
    visible_block_ids: list[str] | None = None
    previous_block_ids: list[str] | None = None
    next_block_ids: list[str] | None = None


class ReaderView(VerticalScroll, can_focus=True):
    DEFAULT_CSS = """
    ReaderView {
        align-horizontal: left;
        scrollbar-gutter: stable;
        padding: 1 3;
    }
    """

    reading_width: reactive[int | str] = reactive(86)

    def __init__(self, theme: Theme, reading_width: int | str = 86, **kwargs) -> None:
        super().__init__(**kwargs)
        self.theme = theme
        self.reading_width = reading_width
        self.view_mode: ReaderViewMode = ReaderViewMode.REFLOW
        self.document: Document | None = None
        self._flat_blocks: list[DocumentBlock] = []
        self._window_start = 0
        self._window_end = 0
        self._last_extend_direction = "down"
        self._location_timer = None
        self.last_state = VisibleState()
        self._settling = False
        self._image_issue_count = 0

    def set_centered(self, centered: bool) -> None:
        """Focus mode (brief §9/§12) centers the reading column now that the default
        layout left-aligns it to keep the AI panel from fighting the text for space."""
        self.styles.align_horizontal = "center" if centered else "left"

    def _warn_image_issue(self, detail: str) -> None:
        get_logger().warning("image render issue: %s", detail)
        self._image_issue_count += 1
        if self._image_issue_count == 1:
            self.notify(
                f"Some images couldn't be displayed ({detail}). See the log for details.",
                title="Image rendering",
                severity="warning",
                timeout=6,
            )

    @property
    def block_count(self) -> int:
        return len(self._flat_blocks)

    async def load_document(self, document: Document, *, initial_block_id: str | None = None) -> None:
        self.document = document
        self._flat_blocks = sorted(document.blocks, key=lambda b: b.order)
        await self.remove_children()
        self._window_start = 0
        self._window_end = 0
        self._settling = True

        start_index = 0
        if initial_block_id:
            for i, b in enumerate(self._flat_blocks):
                if b.id == initial_block_id:
                    start_index = max(0, i - 10)
                    break

        self._window_start = start_index
        self._window_end = start_index
        await self._extend_bottom(INITIAL_WINDOW)
        # Settling ends when the deliberate scroll actually lands (watch_scroll_y), with a
        # short grace-period timer — started only once the scroll has actually been
        # requested, not from here — as a backstop for the "already at the target" case
        # where scroll_y never changes and watch_scroll_y never fires. A *fixed* timer
        # started here would race the `_scroll_to_block` retry chain (which waits for
        # layout on every retry, and can legitimately take longer than any fixed delay on
        # a wide/complex layout), firing before the real scroll lands and letting a
        # near-top extend corrupt the window underneath it.
        if initial_block_id:
            self.call_after_refresh(self._scroll_to_block, initial_block_id, False)
        else:
            self.scroll_home(animate=False)
            self.set_timer(0.15, self._end_settling)
            self.call_after_refresh(self._update_location)

    def _end_settling(self) -> None:
        if self._settling:
            self._settling = False
            self._schedule_location_update()

    def set_view_mode(self, mode: ReaderViewMode) -> None:
        if mode == self.view_mode:
            return
        self.view_mode = mode
        self.call_after_refresh(self._rebuild_window)

    def watch_reading_width(self) -> None:
        self.call_after_refresh(self._rebuild_window)

    async def _rebuild_window(self) -> None:
        if self.document is None:
            return
        start, end = self._window_start, self._window_end
        current = self.last_state.cursor_block_id
        await self.remove_children()
        self._window_start = start
        self._window_end = start
        await self._extend_bottom(end - start)
        if current:
            self._scroll_to_block(current, animate=False)

    def _build_widget(self, block: DocumentBlock, last_page: int | None) -> list[Static]:
        widgets: list[Static] = []
        if self.view_mode == ReaderViewMode.SOURCE_PAGE and block.source_page is not None and block.source_page != last_page:
            widgets.append(_PageDivider(block.source_page, self.theme, self.reading_width))

        if block.type == BlockType.IMAGE and self.document is not None:
            image_bytes = extract_block_image(self.document.path, self.document.metadata.format, block.metadata)
            if image_bytes is None:
                self._warn_image_issue(f"page {block.source_page}: image bytes could not be extracted/decoded")
            else:
                try:
                    widgets.append(_ImageBlockWidget(block, image_bytes, self.reading_width))
                    return widgets
                except Exception as exc:
                    # Fall through to the placeholder panel — a decodable-but-unusable
                    # image (zero dimensions, a codec quirk the terminal can't display)
                    # must never take the whole extend batch down with it.
                    self._warn_image_issue(f"page {block.source_page}: image widget failed to render ({exc})")

        renderable = render_block(block, self.theme, self._effective_width())
        if renderable is not None:
            widgets.append(_BlockWidget(block, renderable, self.reading_width))
        return widgets

    def _effective_width(self) -> int:
        if isinstance(self.reading_width, int):
            return self.reading_width
        return max(20, self.size.width - 4)

    def _build_widget_safe(self, block: DocumentBlock, last_page: int | None) -> list[Static]:
        try:
            return self._build_widget(block, last_page)
        except Exception:
            # One malformed block must never take down the whole extend batch (and with
            # it, the reader's ability to scroll any further) — brief §63.
            fallback = _BlockWidget(
                block,
                Text(f"[Could not display this block — page {block.source_page or '?'}]", style=self.theme.muted),
                self.reading_width,
            )
            return [fallback]

    def _nudge_new_images(self, widgets: list[Static]) -> None:
        """Kitty/Sixel image widgets set their own `refresh(layout=True)` flag as soon as
        image bytes are assigned — which happens in the constructor, *before* the widget is
        mounted. A refresh requested before a widget is attached to the compositor is lost,
        so without this, freshly-mounted images silently fail to actually paint until some
        unrelated later layout event (e.g. resizing a panel) forces a fresh one. Re-request
        the refresh now that the widget is actually attached and has a real region.
        """
        images = [w for w in widgets if isinstance(w, _ImageBlockWidget)]
        if images:
            self.call_after_refresh(self._refresh_images, images)

    def _refresh_images(self, images: list[Static]) -> None:
        for image in images:
            image.refresh(layout=True)

    async def _extend_bottom(self, count: int) -> None:
        if self.document is None:
            return
        end = min(self._window_end + count, len(self._flat_blocks))
        last_page = self._flat_blocks[self._window_end - 1].source_page if self._window_end > 0 else None
        new_widgets: list[Static] = []
        for block in self._flat_blocks[self._window_end : end]:
            new_widgets.extend(self._build_widget_safe(block, last_page))
            last_page = block.source_page if block.source_page is not None else last_page
        if new_widgets:
            await self.mount_all(new_widgets)
            self._nudge_new_images(new_widgets)
        self._window_end = end
        self._last_extend_direction = "down"
        await self._trim_if_needed()

    async def _extend_top(self, count: int) -> None:
        if self.document is None or self._window_start == 0:
            return
        new_start = max(0, self._window_start - count)
        added_blocks = self._flat_blocks[new_start : self._window_start]

        # Anchor to the current cursor block's on-screen offset (not a manual sum of
        # widget heights — that drifted by a few blocks' worth of pixels under real
        # content, since it has to assume nothing about already-mounted widgets changes
        # between the "before" and "after" measurement). Widget regions are exact and
        # post-layout, so re-deriving the scroll target from the anchor's own region after
        # prepending is precise regardless of how tall the new content turns out to be.
        anchor_id = self.last_state.cursor_block_id
        anchor_offset = None
        if anchor_id:
            try:
                anchor_widget = self.query_one(f"#{anchor_id}")
                anchor_offset = self.scroll_y - anchor_widget.virtual_region.y
            except Exception:
                anchor_offset = None

        last_page = self._flat_blocks[new_start - 1].source_page if new_start > 0 else None
        new_widgets: list[Static] = []
        for block in added_blocks:
            new_widgets.extend(self._build_widget_safe(block, last_page))
            last_page = block.source_page if block.source_page is not None else last_page

        if new_widgets:
            await self.mount_all(new_widgets, before=0)
            self._nudge_new_images(new_widgets)
            if anchor_id and anchor_offset is not None:
                self.call_after_refresh(self._restore_scroll_anchor, anchor_id, anchor_offset)
        self._window_start = new_start
        self._last_extend_direction = "up"
        await self._trim_if_needed()

    def _restore_scroll_anchor(self, anchor_id: str, anchor_offset: float) -> None:
        try:
            widget = self.query_one(f"#{anchor_id}")
        except Exception:
            return
        target_y = max(0.0, widget.virtual_region.y + anchor_offset)
        self.scroll_to(y=target_y, animate=False, immediate=True)

    async def _trim_if_needed(self) -> None:
        mounted = list(self.children)
        if len(mounted) <= MAX_MOUNTED:
            return

        excess = len(mounted) - MAX_MOUNTED
        if self._last_extend_direction == "down":
            to_remove = mounted[:excess]
            removed_height = sum(w.size.height + BLOCK_MARGIN for w in to_remove)
            for w in to_remove:
                await w.remove()
            self.scroll_to(y=max(0.0, self.scroll_y - removed_height), animate=False, immediate=True)
            block_widgets_left = [w for w in mounted[excess:] if hasattr(w, "block_id")]
            if block_widgets_left:
                self._window_start = self._flat_blocks_index(block_widgets_left[0].block_id)
        else:
            to_remove = mounted[-excess:]
            for w in to_remove:
                await w.remove()
            block_widgets_left = [w for w in mounted[:-excess] if hasattr(w, "block_id")]
            if block_widgets_left:
                self._window_end = self._flat_blocks_index(block_widgets_left[-1].block_id) + 1

    def _flat_blocks_index(self, block_id: str) -> int:
        for i, b in enumerate(self._flat_blocks):
            if b.id == block_id:
                return i
        return 0

    def watch_scroll_y(self, old: float, new: float) -> None:
        self._settling = False
        self._schedule_location_update()

    def _schedule_location_update(self) -> None:
        if self._location_timer is not None:
            self._location_timer.stop()
        self._location_timer = self.set_timer(0.08, self._update_location)

    def _update_location(self) -> None:
        block_widgets = [c for c in self.children if hasattr(c, "block_id")]
        if not block_widgets:
            return

        viewport_top = self.scroll_y
        viewport_bottom = self.scroll_y + self.size.height

        visible_ids: list[str] = [
            widget.block_id
            for widget in block_widgets
            if widget.virtual_region.y + widget.virtual_region.height > viewport_top
            and widget.virtual_region.y < viewport_bottom
        ]

        cursor_id = visible_ids[0] if visible_ids else block_widgets[0].block_id
        cursor_block = self.document.block_by_id(cursor_id) if self.document else None
        section_id = cursor_block.section_id if cursor_block else None
        page = cursor_block.source_page if cursor_block else None

        idx = self._flat_blocks_index(cursor_id)
        prev_ids = [b.id for b in self._flat_blocks[max(0, idx - 5) : idx]]
        next_ids = [b.id for b in self._flat_blocks[idx + 1 : idx + 6]]

        section_changed = section_id != self.last_state.current_section_id
        self.last_state = VisibleState(
            cursor_block_id=cursor_id,
            current_page=page,
            current_section_id=section_id,
            visible_block_ids=visible_ids,
            previous_block_ids=prev_ids,
            next_block_ids=next_ids,
        )
        self.post_message(LocationChanged(cursor_id, page, section_id))
        if section_changed:
            self.post_message(SectionChanged(section_id))

        self._maybe_extend()

    def _maybe_extend(self) -> None:
        if self.document is None or self._settling:
            return
        near_bottom = (self.max_scroll_y - self.scroll_y) < EXTEND_MARGIN
        near_top = self.scroll_y < EXTEND_MARGIN
        if near_bottom and self._window_end < len(self._flat_blocks):
            self.run_worker(self._extend_bottom(WINDOW_CHUNK), exclusive=False)
        elif near_top and self._window_start > 0:
            self.run_worker(self._extend_top(WINDOW_CHUNK), exclusive=False)

    def _scroll_to_block(self, block_id: str, animate: bool = True, retries: int = 4) -> None:
        try:
            widget = self.query_one(f"#{block_id}")
        except Exception:
            self._end_settling()
            return
        if widget.virtual_region.height == 0 and retries > 0:
            # Freshly mounted widgets aren't laid out yet on the same refresh they were
            # mounted on — wait another cycle rather than compute a scroll target from a
            # zero-size region.
            self.call_after_refresh(self._scroll_to_block, block_id, animate, retries - 1)
            return
        scrolled = self.scroll_to_widget(widget, animate=animate, top=True, immediate=True)
        if not scrolled:
            # Already at the target position — no scroll_y change will fire to end settling.
            self._end_settling()
        else:
            # `immediate=True` still doesn't guarantee the scroll_y change lands
            # synchronously — give it one short grace period, started only now (not from
            # when loading began), then end settling regardless. watch_scroll_y ends it
            # sooner if the change lands before this fires.
            self.set_timer(0.15, self._end_settling)

    async def jump_to_block(self, block_id: str) -> None:
        if self.document is None:
            return
        idx = self._flat_blocks_index(block_id)
        if not (self._window_start <= idx < self._window_end):
            await self.load_document(self.document, initial_block_id=block_id)
            return
        self._scroll_to_block(block_id)

    async def jump_to_section(self, section_id: str) -> None:
        if self.document is None:
            return
        section = self.document.section_by_id(section_id)
        if section and section.block_ids:
            await self.jump_to_block(section.block_ids[0])

    def action_scroll_down_line(self) -> None:
        self.scroll_relative(y=2)

    def action_scroll_up_line(self) -> None:
        self.scroll_relative(y=-2)

    def action_half_page_down(self) -> None:
        self.scroll_relative(y=max(1, self.size.height // 2))

    def action_half_page_up(self) -> None:
        self.scroll_relative(y=-max(1, self.size.height // 2))

    def action_page_down(self) -> None:
        self.scroll_page_down()

    def action_page_up(self) -> None:
        self.scroll_page_up()

    def action_goto_start(self) -> None:
        if self._window_start > 0 and self.document is not None:
            self.run_worker(self.load_document(self.document, initial_block_id=self._flat_blocks[0].id))
        else:
            self.scroll_home()

    def action_goto_end(self) -> None:
        if self.document is None:
            return
        if self._window_end < len(self._flat_blocks):
            self.run_worker(self.load_document(self.document, initial_block_id=self._flat_blocks[-1].id))
        else:
            self.scroll_end()
