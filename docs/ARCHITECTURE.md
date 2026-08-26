# Pinax — Architecture

Terminal-native intelligent document reader. This document is the reference architecture
requested before implementation began. Phase 1 (excellent reader, no AI) is now implemented
against this design; later phases extend it without altering these boundaries.

## 1. Layered architecture

```
Source Document
      ↓
Document Parser        (documents/*)          — format → normalized AST, never touches UI/AI
      ↓
Normalized Document     (documents/models.py)  — Document / Section / DocumentBlock
      ↓
Reader Engine            (app/*, ui/*)          — Textual app, virtualized rendering, navigation
      ↓
Reading Context           (app/state.py)         — what block/page/section is on screen right now
      ↓
Retrieval                (search/*, intelligence/retrieval.py — Phase 3)
      ↓
Context Builder           (intelligence/context_builder.py — Phase 2)
      ↓
AI Provider               (intelligence/providers/* — Phase 2)
```

Hard boundaries (enforced by import direction, not just convention):

- `documents/` never imports `ui/` or `intelligence/`. It knows nothing about Textual or LLMs.
- `ui/` never imports a concrete parser or a concrete provider — it depends only on
  `documents.models` and on `intelligence` through a narrow interface (Phase 2+).
- `intelligence/` never imports `textual`. It receives plain data (`ReadingContext`, strings)
  and returns plain data (strings, citations). The provider adapters know nothing about
  documents or the UI — only `list[Message] -> AsyncIterator[str]`.
- `persistence/` is accessed through repositories, not raw SQL scattered through the app.

## 2. Component diagram

```
                      ┌───────────────────────────────────────────┐
                      │                 cli.py                    │
                      │   tr / pinax   [file] [--page][--ask]  │
                      └───────────────────┬─────────────────────-─┘
                                           │ launches
                      ┌────────────────────▼────────────────────┐
                      │              app/app.py (PinaxApp)     │
                      │   screens: Library, Reader, Settings, Help│
                      └───┬───────────────┬────────────────┬─────┘
                          │               │                │
                ┌─────────▼───┐   ┌───────▼──────┐   ┌─────▼──────┐
                │ ui/widgets   │   │ app/state.py │   │ app/events │
                │ reader_view  │   │ ReaderState  │   │ semantic   │
                │ toc, status  │   │ AppMode      │   │ messages   │
                │ search_bar   │   │ ReadingCtx   │   │            │
                │ cmd_palette  │   └───────┬──────┘   └────────────┘
                └──────┬───────┘           │
                       │                   │ read by (Phase 2)
                       │           ┌───────▼────────┐
                       │           │ intelligence/*  │  (not built in Phase 1)
                       │           └────────────────┘
                       │
             ┌─────────▼──────────┐        ┌────────────────────┐
             │ documents/parser.py │───────▶│ documents/models.py │
             │ dispatch by suffix  │        │ Document/Section/   │
             │ pdf/docx/epub/md/txt│        │ Block/BlockType     │
             └─────────┬──────────┘        └──────────┬──────────┘
                       │                               │
             ┌─────────▼──────────┐        ┌───────────▼─────────┐
             │ persistence/database│        │ search/lexical.py   │
             │ + repositories       │◀──────│ SQLite FTS5 index    │
             │ (documents, progress,│        └──────────────────────┘
             │  bookmarks, ...)      │
             └───────────────────────┘
```

## 3. Event / data flow

Two independent loops, matching §73 of the brief ("don't call the LLM because the user
scrolled"):

**Local loop (every keystroke / scroll, cheap, synchronous):**

```
key/mouse event
   → ReaderScreen updates scroll offset / cursor block
   → ReaderView posts LocationChanged / ViewportChanged / SectionChanged
   → app/state.ReadingContext is mutated in place
   → status bar re-renders from ReadingContext
   → reading_progress repository writes debounced (≤ 1/sec) position update
```

No network/DB-heavy/LLM work happens here. This is why `ReadingContext` is a plain mutable
object owned by the app, not something rebuilt from a query each frame.

**Deliberate-action loop (search, AI ask, navigation jump — Phase 2 shows AI wiring):**

```
AIQuestionSubmitted(text)
   → ContextBuilder reads current ReadingContext (snapshot)
   → Retrieval hits FTS5 (+ semantic in Phase 3) for extra chunks
   → ContextBudget assembles prompt within token budget
   → Provider.chat() streams tokens
   → AIResponseStarted / AIResponseCompleted events update the AI panel incrementally
   → citations in the response are parsed into navigable spans
```

Semantic events (superset relevant to Phase 1) are defined in `app/events.py`:
`DocumentOpened`, `DocumentParsed`, `LocationChanged`, `ViewportChanged`, `SectionChanged`,
`SelectionChanged` (Phase 4), `BookmarkCreated`, `SearchExecuted`. AI-related events
(`AIQuestionSubmitted`, `AIResponseStarted/Completed`, `CitationActivated`) are declared now
as a `Protocol`/enum surface so Phase 2 doesn't need to touch `app/state.py` again.

## 4. Normalized document model

`documents/models.py` (Pydantic). This is the single representation every parser produces and
every UI widget consumes — no widget ever sees a `fitz.Page` or a `docx.Document`.

```python
class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    LIST_ITEM = "list_item"
    CODE = "code"
    QUOTE = "quote"
    TABLE = "table"
    IMAGE = "image"
    CAPTION = "caption"
    FOOTNOTE = "footnote"
    EQUATION = "equation"
    PAGE_BREAK = "page_break"

class BoundingBox(BaseModel):
    x0: float; y0: float; x1: float; y1: float

class DocumentBlock(BaseModel):
    id: str
    type: BlockType
    text: str
    source_page: int | None = None
    section_id: str | None = None
    order: int
    level: int | None = None          # heading level / list depth
    bbox: BoundingBox | None = None
    metadata: dict[str, Any] = {}      # e.g. {"language": "python"} for CODE, table rows, etc.

class Section(BaseModel):
    id: str
    title: str
    level: int
    order: int
    parent_id: str | None = None
    block_ids: list[str] = []
    source_page_start: int | None = None
    source_page_end: int | None = None

class DocumentMetadata(BaseModel):
    author: str | None = None
    format: str
    language: str | None = None
    file_hash: str
    file_size: int
    created_at: datetime | None = None

class Document(BaseModel):
    id: str
    path: str
    title: str
    metadata: DocumentMetadata
    sections: list[Section]
    blocks: list[DocumentBlock]
    page_count: int | None
```

Reasoning: PDFs have real pages, DOCX/MD/EPUB usually do not — so `source_page` is optional
everywhere and the reader always reasons in terms of `Section → Block`, using `source_page`
opportunistically for the status bar and Source Page Mode (§10 of brief).

## 5. Database schema

SQLite at `~/.local/share/pinax/pinax.db` (via `platformdirs`), accessed only through
`persistence/repositories/*`. Migrations are plain, numbered SQL files applied by
`persistence/database.py` (`PRAGMA user_version` tracks applied migration).

```sql
-- 0001_initial.sql
CREATE TABLE documents (
    id              TEXT PRIMARY KEY,
    path            TEXT NOT NULL UNIQUE,
    file_hash       TEXT NOT NULL,
    title           TEXT NOT NULL,
    author          TEXT,
    format          TEXT NOT NULL,
    page_count      INTEGER,
    created_at      TEXT NOT NULL,
    last_opened_at  TEXT
);

CREATE TABLE reading_progress (
    document_id     TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    block_id        TEXT,
    page            INTEGER,
    section_id      TEXT,
    scroll_offset   REAL NOT NULL DEFAULT 0,
    progress        REAL NOT NULL DEFAULT 0,   -- 0..1
    reading_time_s  INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT NOT NULL
);

CREATE TABLE bookmarks (
    id              TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    block_id        TEXT,
    page            INTEGER,
    section_id      TEXT,
    preview         TEXT,
    label           TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE annotations (
    id                TEXT PRIMARY KEY,
    document_id       TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    block_id          TEXT,
    selection_start   INTEGER,
    selection_end     INTEGER,
    selected_text     TEXT,
    note              TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

-- Phase 1 also needs a document cache: parsed AST is expensive to rebuild.
CREATE TABLE document_cache (
    document_id     TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    file_hash       TEXT NOT NULL,
    parser_version  TEXT NOT NULL,
    blob_path       TEXT NOT NULL,   -- path under ~/.cache/pinax/ast/<id>.json
    created_at      TEXT NOT NULL
);

CREATE VIRTUAL TABLE blocks_fts USING fts5(
    document_id UNINDEXED,
    block_id UNINDEXED,
    section_title,
    text,
    page UNINDEXED
);
```

Phase 2+ adds `conversations`, `messages`, `document_summaries`, `document_chunks`,
`embedding_records`, `application_settings` — deferred until the AI layer actually needs them,
per §92 ("no half-finished implementations").

## 6. Reader state model

```python
class AppMode(str, Enum):
    READING = "reading"
    SEARCH = "search"
    AI = "ai"                 # Phase 2
    COMMAND_PALETTE = "command_palette"
    TOC = "toc"
    SELECTION = "selection"   # Phase 4
    ANNOTATION = "annotation" # Phase 4
    HELP = "help"
    LIBRARY = "library"

class ReadingContext:
    document_id: str
    current_page: int | None
    current_section_id: str | None
    visible_block_ids: list[str]
    cursor_block_id: str | None
    selected_block_ids: list[str]
    scroll_position: float
    previous_block_ids: list[str]
    next_block_ids: list[str]
```

`AppMode` drives keybinding dispatch (one handler per mode, not a giant conditional — §71/§72
of the brief). `ReadingContext` is owned by `ReaderScreen`, updated on every viewport change,
and is the only thing Phase 2's `ContextBuilder` will read.

## 7. AI context construction algorithm (Phase 2 target, documented now)

```
build_context(question, reading_context, budget) -> PromptContext:
    1. selected_text          (if any)                — highest priority, verbatim
    2. visible_blocks         (reading_context.visible_block_ids, resolved to text)
    3. current_source_page    (label only, "p.41 / 112")
    4. nearby_blocks          (reading_context.previous/next_block_ids, small window)
    5. current_section_summary (Phase 3, cached)
    6. retrieved_chunks       (search/lexical.py now, +semantic in Phase 3)
    7. document_summary       (Phase 3, cached)
    8. conversation_history   (summarized beyond N turns)

    Each tier is added in this order until ContextBudget.remaining() would be exceeded;
    lower-priority tiers are trimmed/dropped first, never selected_text or visible_blocks.
```

`ContextBudget` (dataclass) holds per-tier token caps that scale with the configured model's
context window; `:context` (Phase 2/4) renders exactly which tiers were included and their
sizes, per §42.

## 8. Retrieval architecture

Phase 1 ships lexical only:

```
search/lexical.py
    index_document(document)      -> populate blocks_fts from Document.blocks
    search(document_id, query)    -> ranked (block_id, snippet, page, section) via FTS5 bm25()
```

Phase 3 adds `search/semantic.py` (local embeddings, no mandatory vector DB — brief §36) and
`intelligence/retrieval.py` computes:

```
score = lexical_weight * bm25_norm + semantic_weight * cosine_sim
```

Both are optional and the reader works fully with lexical-only search, which is why it is
built first.

## 9. TUI wireframes

Wide (≥ 120 cols): `TOC | READER | AI`. Medium (80–119): `READER | AI`, TOC becomes an overlay
screen. Narrow (< 80): `READER` only, TOC/AI become full-screen overlays. Focus mode collapses
to a centered single column with no chrome except a page indicator. See §8/§9/§89 of the brief
for the reference layouts — Phase 1 implements Wide/Medium/Narrow reader+TOC (no AI panel yet;
its column is reserved but not rendered until Phase 2).

## 10. Keybinding map (Phase 1 subset; full map in `app/keybindings.py`)

```
j/k Ctrl+d/u Space/Shift+Space   scroll
h/l                              prev/next source page (Source Page Mode)
[ / ]                            prev/next section
gg / G                           top / bottom
/  n  N                          search, next/prev match
t                                toggle TOC
z                                focus mode
b                                bookmark
:                                command palette
?                                help
q / Esc                          close overlay / back
Ctrl+o                           file picker
a  m                             reserved for Phase 2 (AI) / Phase 4 (notes) — bound, no-op with a hint
```

## 11. Directory structure (implemented, Phase 1)

```
src/pinax/
├── cli.py                     entry point: tr/pinax [path] [--page] [--search] [--ask*]
├── __main__.py
├── app/
│   ├── app.py                 PinaxApp, screen stack, global key dispatch by AppMode
│   ├── state.py                AppMode, ReadingContext, AppState
│   ├── keybindings.py           Keymap dataclass, default bindings
│   └── events.py                 semantic Textual messages
├── ui/
│   ├── screens/{reader,library,help}.py
│   ├── widgets/{reader_view,toc,status_bar,search_bar,command_palette,progress_bar}.py
│   └── themes/themes.py          Theme dataclass + Midnight/Nord/Paper/Dracula/Catppuccin/Mono/TermGreen
├── documents/
│   ├── models.py, parser.py, normalization.py, chunking.py
│   └── pdf.py, docx.py, markdown.py, text.py, epub.py
├── persistence/
│   ├── database.py, repositories/{documents,reading_progress,bookmarks}.py
├── search/lexical.py
└── config/{models.py, settings.py}
```

`intelligence/`, `search/semantic.py`, and the `agent_panel`/`notes_panel` widgets are
intentionally not created yet — they are Phase 2/3/4 and would otherwise be empty scaffolding.

## 12. Dependency choices

| Concern            | Choice                     | Why |
|---------------------|----------------------------|-----|
| TUI                 | Textual                    | async-native, CSS-like styling, virtualization primitives (works well with large documents) |
| Rendering primitives| Rich                       | ships with Textual, used for markup/tables/syntax highlighting |
| PDF                 | PyMuPDF (fitz)              | fast, block/layout-aware extraction, page images for OCR heuristic |
| DOCX                | python-docx                 | reads heading styles directly → trivial TOC |
| EPUB                | ebooklib + BeautifulSoup    | spine/TOC access + HTML→block conversion |
| Markdown            | markdown-it-py              | CommonMark token stream maps cleanly to BlockType |
| Validation          | Pydantic v2                 | the normalized document model, config schema |
| DB                  | stdlib `sqlite3` + FTS5     | zero extra infra, ships with Python on all target platforms |
| Config paths        | `platformdirs`              | correct XDG/macOS/Windows paths without hand-rolling |
| CLI                 | `click`                     | subcommands (`config`, `doctor`, `cache`) + good `--help` |

No SQLAlchemy in Phase 1 — a lightweight repository layer over stdlib `sqlite3` is simpler and
sufficient for a single-user local app (brief explicitly allows "SQLAlchemy or lightweight
repository layer").

## 13. Implementation milestones

- **Phase 1 (this delivery):** CLI, Textual shell, PDF/DOCX/MD/TXT/EPUB parsing, normalized
  model, reader view (reflow + source-page mode), TOC, vim scrolling, FTS5 search, SQLite
  progress persistence + library screen, 7 themes, width management, focus mode.
- **Phase 2:** AI panel, provider abstraction (OpenAI/Anthropic/Ollama/compatible), streaming,
  `ReadingContext`→`ContextBuilder` wiring, citations, chat persistence.
- **Phase 3:** hierarchical summaries, embeddings/hybrid retrieval, whole-document Q&A,
  `:context` debug view.
- **Phase 4:** bookmarks/notes UI, selection mode, reading history (back/forward), AI-navigate,
  Socratic mode, quiz/flashcards.
- **Phase 5:** HTML/PPTX, equations, terminal images, OCR pipeline, complex multi-column PDFs.

## 14. Testing strategy

- **Unit:** `documents/models.py` invariants, each parser against small in-memory fixtures
  (PDF/DOCX generated on the fly with PyMuPDF/python-docx in test setup, no binary fixtures
  committed), heading-inference heuristics, chunk boundary rules, FTS5 query ranking.
- **Repository/integration:** `persistence/*` against a temp SQLite file — migration
  idempotency, progress upsert, bookmark CRUD, cascade deletes.
- **TUI:** Textual's `App.run_test()` pilot for keybinding dispatch, TOC navigation, search
  overlay open/select/jump, theme switching, responsive layout breakpoints.
- **No AI tests in Phase 1** — provider adapters and context-builder tests land with Phase 2.

## 15. Post-Phase-1 visual pass

Pulled forward from later phases after seeing the reader on a real terminal (kitty) and
comparing against a target visual reference:

- **Chrome redesign** (`ui/widgets/top_bar.py`, `bottom_bar.py`, `sidebar.py`, `ai_panel.py`):
  the plain `StatusBar`/`Footer`/bare-tree `TOCPanel` were replaced with a colored-badge top
  bar (page/progress/width/mode chips), a colored-badge bottom key-hint bar, and a `Sidebar`
  that wraps the outline tree and a new `PagesPanel` in Textual's `TabbedContent`, plus a
  document-info footer (file/format/pages/author/producer/size/modified).
- **Image rendering** (`ui/images.py`, `_ImageBlockWidget` in `reader_view.py`): moved up
  from Phase 5. IMAGE blocks with a resolvable source render via `textual-image`'s
  `AutoImage`, which auto-negotiates Kitty graphics protocol → Sixel → half-cell unicode
  depending on what the terminal supports — no per-terminal branching needed in pinax
  itself. Extraction is lazy and `lru_cache`d per `(path, xref)`, not done at parse time, so
  `documents/pdf.py` stays free of cache-directory side effects. Currently PDF-only (embedded
  image xrefs); DOCX/EPUB inline images still fall back to the placeholder panel.
- **PAGES tab** (`ui/widgets/pages_panel.py`): PDF-only page thumbnails, rasterized via
  PyMuPDF (`page.get_pixmap`) at low resolution, generated off the event loop
  (`asyncio.to_thread` per page) and capped at `MAX_THUMBNAILS` so a 600-page book doesn't
  block startup or rasterize pages nobody will look at.
- **In-app theme switching**: `ReaderScreen.action_set_theme()`, reachable from the command
  palette (`Theme: <name>` per theme), swaps `self.theme`, persists it to `config.toml`, and
  re-renders the currently-mounted window (`ReaderView._rebuild_window()`) plus every themed
  chrome widget — no full remount, so scroll position survives a theme switch.
- **`reader.show_agent` now defaults to `true`** — the AI panel exists as an honest "not
  configured" placeholder rather than fabricated content, so there's no reason to hide it by
  default the way there was before it existed.

None of this changes the layer boundaries in §1 — it is entirely inside `ui/`.
