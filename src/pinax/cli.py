"""CLI entry point (brief §58): `tr` / `pinax`.

`tr file.pdf` is sugar for `tr open file.pdf` — `PinaxGroup.resolve_command` falls back
to the `open` subcommand whenever the first argument isn't a recognized subcommand name, so
a bare path works without every subcommand fighting over positional-argument parsing.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import click


class PinaxGroup(click.Group):
    def resolve_command(self, ctx, args):
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            return super().resolve_command(ctx, ["open", *args])


@click.group(cls=PinaxGroup, invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Pinax — a terminal-native intelligent document reader."""
    if ctx.invoked_subcommand is None:
        _run_app(None, None, None)


@main.command()
@click.argument("path", required=False, type=click.Path(exists=True, dir_okay=False))
@click.option("--page", type=int, default=None, help="Open at a specific source page.")
@click.option("--search", "search_query", type=str, default=None, help="Open and immediately run a search.")
def open(path: str | None, page: int | None, search_query: str | None) -> None:
    """Open a document, or the library if PATH is omitted."""
    _run_app(path, page, search_query)


def _run_app(path: str | None, page: int | None, search_query: str | None) -> None:
    from .app.logging_setup import configure_logging, get_logger

    log_path = configure_logging()
    logger = get_logger()

    # textual-image detects Kitty/Sixel graphics-protocol support by writing an escape
    # sequence and reading the terminal's reply. That round-trip only works while stdin is
    # still plain blocking I/O — once Textual's `App.run()` starts, it owns stdin on a
    # background thread and grabs the terminal's reply before textual-image ever sees it,
    # so detection always fails and silently degrades to low-fidelity half-cell rendering.
    # Importing it here — before `app.run()` — forces that detection to happen while it can
    # still succeed.
    import textual_image.widget  # noqa: F401
    from textual_image.renderable import Image as _SelectedImageRenderable

    protocol = _SelectedImageRenderable.__module__.rsplit(".", 1)[-1]
    logger.info("pinax starting: path=%s image_protocol=%s log=%s", path, protocol, log_path)

    from .app.app import PinaxApp

    app = PinaxApp(initial_path=path, initial_page=page, initial_search=search_query)
    try:
        app.run()
    except Exception:
        logger.exception("pinax crashed")
        raise


@main.command()
def config() -> None:
    """Show (and optionally edit) the configuration file."""
    from .config.settings import config_path, load_settings

    load_settings()  # ensures config.toml exists on a fresh install
    path = config_path()
    click.echo(f"Config file: {path}\n")
    click.echo(path.read_text())

    editor = os.environ.get("EDITOR")
    if editor and sys.stdout.isatty():
        if click.confirm(f"Open in {editor}?", default=False):
            subprocess.call([editor, str(path)])


@main.command()
def doctor() -> None:
    """Report environment/dependency health."""
    import textual

    from . import __version__
    from .config.settings import cache_dir, config_path, data_dir, database_path

    click.echo(f"pinax {__version__}")
    click.echo(f"Python        {sys.version.split()[0]}")
    click.echo(f"Textual       {textual.__version__}")
    click.echo()

    for name, importer in [
        ("PyMuPDF (pdf)", lambda: __import__("pymupdf")),
        ("python-docx (docx)", lambda: __import__("docx")),
        ("ebooklib (epub)", lambda: __import__("ebooklib")),
        ("markdown-it-py (md)", lambda: __import__("markdown_it")),
        ("textual-image (embedded images)", lambda: __import__("textual_image")),
    ]:
        try:
            importer()
            click.echo(f"  [ok]   {name}")
        except ImportError as exc:
            click.echo(f"  [FAIL] {name}: {exc}")

    click.echo()
    try:
        import textual_image.widget  # noqa: F401 -- triggers detection, same as the real app does
        from textual_image.renderable import Image as _SelectedImageRenderable

        protocol = _SelectedImageRenderable.__module__.rsplit(".", 1)[-1]
        quality = {"tgp": "best", "sixel": "best", "halfcell": "low-fidelity", "unicode": "no terminal detected"}
        click.echo(f"  [ok]   Image protocol: {protocol} ({quality.get(protocol, 'unknown')})")
        if protocol == "halfcell":
            click.echo("         Falling back to half-cell rendering means Kitty/Sixel weren't detected.")
            click.echo("         This is expected outside a real interactive terminal (e.g. piped output).")
    except Exception as exc:
        click.echo(f"  [--]   Could not detect terminal graphics support: {exc}")
        click.echo("         Images fall back to colored half-cell rendering, which works everywhere.")

    click.echo()
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        click.echo("  [ok]   SQLite FTS5 support")
    except sqlite3.OperationalError as exc:
        click.echo(f"  [FAIL] SQLite FTS5 support: {exc}")

    click.echo()
    click.echo(f"  Config    {config_path()} ({'exists' if config_path().exists() else 'will be created on first run'})")
    click.echo(f"  Database  {database_path()}")
    click.echo(f"  Cache     {cache_dir()}")
    click.echo(f"  Data dir  {data_dir()}")

    click.echo()
    click.echo("  AI provider: not configured (AI assistant ships in Phase 2)")

    click.echo()
    term = os.environ.get("TERM", "unknown")
    colorterm = os.environ.get("COLORTERM", "")
    click.echo(f"  TERM={term}  COLORTERM={colorterm or '(unset)'}")


@main.group()
def cache() -> None:
    """Inspect or clear the on-disk document cache."""


@cache.command("status")
def cache_status() -> None:
    from .config.settings import cache_dir

    root = cache_dir()
    if not root.exists():
        click.echo(f"{root} does not exist yet.")
        return

    total_bytes = 0
    file_count = 0
    for p in root.rglob("*"):
        if p.is_file():
            total_bytes += p.stat().st_size
            file_count += 1

    click.echo(f"Cache directory: {root}")
    click.echo(f"Files:           {file_count}")
    click.echo(f"Size:            {total_bytes / (1 << 20):.2f} MiB")


@cache.command("clear")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
def cache_clear(yes: bool) -> None:
    from .config.settings import cache_dir

    root = cache_dir()
    if not root.exists():
        click.echo("Nothing to clear.")
        return
    if not yes and not click.confirm(f"Delete everything under {root}?", default=False):
        click.echo("Cancelled.")
        return
    shutil.rmtree(root)
    click.echo("Cache cleared.")


if __name__ == "__main__":
    main()
