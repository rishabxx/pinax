"""Regenerates the README screenshots from the synthetic demo documents in this directory.

All demo content is original text written for this repo — not excerpted from any real
book — specifically so these screenshots carry no copyright question. Run from the repo
root with a throwaway HOME so it doesn't touch your real reading history:

    HOME=$(mktemp -d) uv run python docs/screenshots/generate.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pinax.app.app import PinaxApp
from pinax.ui.widgets.reader_view import ReaderView

DEMO_DIR = Path(__file__).parent / "demo-content"
OUT_DIR = Path(__file__).parent


async def _read_partway(path: Path, presses: int) -> None:
    app = PinaxApp(initial_path=str(path))
    async with app.run_test(size=(150, 42)) as pilot:
        await pilot.pause(0.3)
        for _ in range(presses):
            await pilot.press("space")
        await pilot.pause(0.3)
        app.screen._save_progress()
    app.conn.close()


async def main() -> None:
    # A code block + a table are the two most distinctive rendering features to show off.
    app = PinaxApp(initial_path=str(DEMO_DIR / "architecture-spec.md"))
    async with app.run_test(size=(150, 42)) as pilot:
        await pilot.pause(0.3)
        reader = app.screen.query_one("#reader-view", ReaderView)
        for _ in range(2):
            await pilot.press("space")
        await pilot.pause(0.3)
        app.save_screenshot(str(OUT_DIR / "reader.svg"))

        reader.scroll_to(y=18, animate=False, immediate=True)
        await pilot.pause(0.3)
        app.save_screenshot(str(OUT_DIR / "reader-table.svg"))
    app.conn.close()

    # A populated library needs a few documents with real reading progress.
    await _read_partway(DEMO_DIR / "architecture-spec.md", 3)
    await _read_partway(DEMO_DIR / "distributed-systems-notes.md", 8)
    await _read_partway(DEMO_DIR / "api-design-guide.md", 25)

    app = PinaxApp()
    async with app.run_test(size=(150, 42)) as pilot:
        await pilot.pause(0.3)
        app.save_screenshot(str(OUT_DIR / "library.svg"))
    app.conn.close()

    print(f"Wrote screenshots to {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
