"""Theme palettes (brief §47).

Colors are applied programmatically (widget.styles.*, Rich Style objects) rather than via
per-theme CSS blocks — content styling (headings, code, quotes) is generated dynamically
from parsed documents, so Python-side theming is the simpler and more testable path than
duplicating CSS per theme. Structural layout (padding, borders, panel sizing) lives in
static Textual CSS that doesn't hardcode color.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Theme:
    name: str
    background: str
    surface: str  # panel/sidebar background, one step off the page background
    foreground: str
    muted: str  # dim text: hints, page numbers, secondary status
    accent: str  # current selection, active TOC entry, search highlight
    border: str
    heading_colors: tuple[str, str, str, str, str, str] = field(
        default=("", "", "", "", "", "")
    )
    code_theme: str = "monokai"
    quote_color: str = ""
    link_color: str = ""

    def heading_color(self, level: int) -> str:
        idx = max(0, min(level - 1, len(self.heading_colors) - 1))
        return self.heading_colors[idx] or self.foreground


MIDNIGHT = Theme(
    name="Midnight",
    background="#0d1117",
    surface="#131a24",
    foreground="#d6deeb",
    muted="#5b6b83",
    accent="#7aa2f7",
    border="#1f2733",
    heading_colors=("#e0af68", "#7aa2f7", "#9ece6a", "#bb9af7", "#e0af68", "#7aa2f7"),
    code_theme="one-dark",
    quote_color="#7dcfff",
    link_color="#7aa2f7",
)

NORD = Theme(
    name="Nord",
    background="#2e3440",
    surface="#3b4252",
    foreground="#e5e9f0",
    muted="#6b7689",
    accent="#88c0d0",
    border="#434c5e",
    heading_colors=("#88c0d0", "#81a1c1", "#a3be8c", "#b48ead", "#88c0d0", "#81a1c1"),
    code_theme="nord",
    quote_color="#8fbcbb",
    link_color="#88c0d0",
)

CATPPUCCIN = Theme(
    name="Catppuccin",
    background="#1e1e2e",
    surface="#292c3c",
    foreground="#cdd6f4",
    muted="#6c7086",
    accent="#f5c2e7",
    border="#313244",
    heading_colors=("#f5c2e7", "#89b4fa", "#a6e3a1", "#fab387", "#f5c2e7", "#89b4fa"),
    code_theme="monokai",
    quote_color="#94e2d5",
    link_color="#89b4fa",
)

DRACULA = Theme(
    name="Dracula",
    background="#282a36",
    surface="#343746",
    foreground="#f8f8f2",
    muted="#6272a4",
    accent="#ff79c6",
    border="#44475a",
    heading_colors=("#ff79c6", "#bd93f9", "#50fa7b", "#ffb86c", "#ff79c6", "#bd93f9"),
    code_theme="dracula",
    quote_color="#8be9fd",
    link_color="#8be9fd",
)

PAPER = Theme(
    name="Paper",
    background="#faf6ef",
    surface="#f1ebe0",
    foreground="#2b2620",
    muted="#8a8073",
    accent="#a1673a",
    border="#ddd3c2",
    heading_colors=("#8a4a2b", "#a1673a", "#5c6b3f", "#7a5a8a", "#8a4a2b", "#a1673a"),
    code_theme="friendly",
    quote_color="#5c6b3f",
    link_color="#a1673a",
)

MONOCHROME = Theme(
    name="Monochrome",
    background="#101010",
    surface="#1a1a1a",
    foreground="#e6e6e6",
    muted="#6e6e6e",
    accent="#ffffff",
    border="#2c2c2c",
    heading_colors=("#ffffff", "#e6e6e6", "#cccccc", "#b3b3b3", "#ffffff", "#e6e6e6"),
    code_theme="bw",
    quote_color="#b3b3b3",
    link_color="#ffffff",
)

JET_BLACK = Theme(
    name="Jet Black",
    background="#000000",
    surface="#0a0a0a",
    foreground="#e6e6e6",
    muted="#5f5f5f",
    accent="#00e5ff",
    border="#1a1a1a",
    heading_colors=("#00e5ff", "#33ff99", "#ffd166", "#c792ea", "#00e5ff", "#33ff99"),
    code_theme="monokai",
    quote_color="#00e5ff",
    link_color="#00e5ff",
)

TERMINAL_GREEN = Theme(
    name="Terminal Green",
    background="#001100",
    surface="#001a00",
    foreground="#33ff33",
    muted="#0f8a0f",
    accent="#88ff88",
    border="#0f4d0f",
    heading_colors=("#88ff88", "#66ee66", "#55dd55", "#44cc44", "#88ff88", "#66ee66"),
    code_theme="vim",
    quote_color="#55dd55",
    link_color="#88ff88",
)

THEMES: dict[str, Theme] = {
    t.name.lower().replace(" ", "-"): t
    for t in (MIDNIGHT, NORD, CATPPUCCIN, DRACULA, PAPER, MONOCHROME, JET_BLACK, TERMINAL_GREEN)
}
# Accept the config-file keys used in brief §66/§47 examples too.
THEMES["midnight"] = MIDNIGHT
THEMES["nord"] = NORD
THEMES["catppuccin"] = CATPPUCCIN
THEMES["dracula"] = DRACULA
THEMES["paper"] = PAPER
THEMES["monochrome"] = MONOCHROME
THEMES["jet-black"] = JET_BLACK
THEMES["terminal-green"] = TERMINAL_GREEN

DEFAULT_THEME_NAME = "midnight"


def get_theme(name: str) -> Theme:
    return THEMES.get(name.lower(), MIDNIGHT)


THEME_NAMES = list(dict.fromkeys(t.name for t in THEMES.values()))

__all__ = ["Theme", "THEMES", "THEME_NAMES", "DEFAULT_THEME_NAME", "get_theme"]
