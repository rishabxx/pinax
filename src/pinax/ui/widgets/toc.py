"""Table of contents tree (brief §16), backed by Textual's Tree widget.

Sizing/border/title chrome live on the containing `Sidebar` — this widget is just the tree,
so it can sit inside a `TabPane` without doubling up on borders or padding.
"""

from __future__ import annotations

from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from ...documents.models import Document
from ..themes import Theme


class TOCTree(Tree):
    DEFAULT_CSS = """
    TOCTree { background: transparent; }
    """

    def __init__(self, theme: Theme, **kwargs) -> None:
        super().__init__("Document", **kwargs)
        self.theme = theme
        self._section_nodes: dict[str, TreeNode] = {}
        self._highlighted: str | None = None

    def on_mount(self) -> None:
        self.show_root = False
        self.guide_depth = 2

    def load_document(self, document: Document) -> None:
        self.clear()
        self._section_nodes.clear()

        node_by_id: dict[str, TreeNode] = {}
        for section in sorted(document.sections, key=lambda s: s.order):
            title = section.title.strip() or "(untitled)"
            parent_node = node_by_id.get(section.parent_id) if section.parent_id else None
            target = parent_node if parent_node is not None else self.root
            node = target.add(title, data=section.id)
            node_by_id[section.id] = node
            self._section_nodes[section.id] = node

        self.root.expand_all()

    def highlight_section(self, section_id: str | None) -> None:
        if section_id is None or section_id == self._highlighted:
            return
        self._highlighted = section_id
        node = self._section_nodes.get(section_id)
        if node is not None:
            self.select_node(node)
            self.scroll_to_node(node, animate=False)
