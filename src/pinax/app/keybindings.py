"""Default keymap (brief §13). `gg` is a two-key chord handled separately in
`ReaderScreen.on_key` since Textual's `Binding` model doesn't express multi-key chords.
"""

from __future__ import annotations

from textual.binding import Binding

READER_BINDINGS: list[Binding] = [
    Binding("j,down", "scroll_down_line", "Scroll down", show=False),
    Binding("k,up", "scroll_up_line", "Scroll up", show=False),
    Binding("ctrl+d", "half_page_down", "½ page ↓", show=False),
    Binding("ctrl+u", "half_page_up", "½ page ↑", show=False),
    Binding("space,pagedown", "page_down", "Page ↓", show=False),
    Binding("shift+space,pageup", "page_up", "Page ↑", show=False),
    Binding("h", "prev_source_page", "Prev page"),
    Binding("l", "next_source_page", "Next page"),
    Binding("right_square_bracket", "next_section", "Next §", key_display="]"),
    Binding("left_square_bracket", "prev_section", "Prev §", key_display="["),
    Binding("G", "goto_end", "Bottom", show=False),
    Binding("slash", "open_search", "Search", key_display="/"),
    Binding("n", "search_next", "Next match", show=False),
    Binding("N", "search_prev", "Prev match", show=False),
    Binding("t", "toggle_toc", "TOC"),
    Binding("z,ctrl+z", "toggle_focus_mode", "Focus"),
    Binding("p", "toggle_page_mode", "Page mode", show=False),
    Binding("colon", "open_command_palette", "Commands", key_display=":"),
    Binding("ctrl+p", "open_command_palette", "Commands", show=False),
    Binding("ctrl+o", "open_file_picker", "Open file", show=False),
    Binding("question_mark", "open_help", "Help", key_display="?"),
    Binding("a", "reserved_ai", "Ask AI"),
    Binding("ctrl+i", "toggle_ai_panel", "AI panel", show=False),
    Binding("b", "reserved_bookmark", "Bookmark (Phase 4)", show=False),
    Binding("m", "reserved_notes", "Notes (Phase 4)", show=False),
    Binding("escape,q", "close_overlay", "Close"),
]

RESERVED_HINTS = {
    "reserved_ai": "AI assistant arrives in Phase 2 — the reader itself is fully usable without it.",
    "reserved_bookmark": "Bookmarks arrive in Phase 4.",
    "reserved_notes": "Notes/annotations arrive in Phase 4.",
}

__all__ = ["READER_BINDINGS", "RESERVED_HINTS"]
