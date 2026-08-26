"""Regenerates the README screenshots from synthetic demo content — nothing here is
excerpted from a real book, specifically so these screenshots carry no copyright question.

The Markdown demo docs live in `demo-content/`. The PDF demo (with an embedded chart, to
show off image rendering) is generated on the fly by this script rather than checked in as
a binary, the same way the test suite generates its PDF fixtures.

Run from the repo root with a throwaway HOME so it doesn't touch your real reading history:

    HOME=$(mktemp -d) uv run python docs/screenshots/generate.py

Note: headless captures (this script) can't exercise a real terminal's Kitty/Sixel graphics
protocol — that only works talking to an actual terminal emulator. For a screenshot that
shows the embedded chart actually rendered, run the generated PDF
(`docs/screenshots/demo-content/embedding-notes.pdf`) in a real terminal and capture it
yourself: `uv run pinax docs/screenshots/demo-content/embedding-notes.pdf`.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

from pinax.app.app import PinaxApp
from pinax.ui.widgets.reader_view import ReaderView

DEMO_DIR = Path(__file__).parent / "demo-content"
OUT_DIR = Path(__file__).parent
THEME = "jet-black"


def _build_chart(path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    random.seed(7)
    width, height = 1400, 900
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    clusters = {
        "alpha": ((300, 250), (255, 99, 71)),
        "beta": ((1000, 220), (30, 144, 255)),
        "gamma": ((250, 650), (60, 179, 113)),
        "delta": ((1050, 680), (238, 130, 238)),
        "epsilon": ((680, 450), (255, 165, 0)),
    }
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    except Exception:
        font = ImageFont.load_default()

    for name, (center, color) in clusters.items():
        cx, cy = center
        for _ in range(220):
            x = cx + random.gauss(0, 90)
            y = cy + random.gauss(0, 90)
            r = random.randint(4, 8)
            draw.ellipse([x - r, y - r, x + r, y + r], outline=color, width=2)
        draw.text((cx - 40, cy - 130), name, fill=color, font=font)

    draw.text((40, 30), "Figure 3.2 - Embedding clusters by category", fill=(20, 20, 20), font=font)
    img.save(path)


def _build_demo_pdf(out_path: Path, chart_path: Path) -> None:
    import pymupdf

    pdf = pymupdf.open()

    page = pdf.new_page(width=612, height=792)
    page.insert_textbox(pymupdf.Rect(72, 72, 540, 140), "Embedding Space Notes", fontsize=24, fontname="helv", color=(0.1, 0.1, 0.1))
    page.insert_textbox(
        pymupdf.Rect(72, 150, 540, 200), "3  Visualizing Learned Representations", fontsize=16, fontname="helv", color=(0.15, 0.15, 0.4)
    )
    intro = (
        "One way to sanity-check a learned embedding space is to project it down to two "
        "dimensions and look at whether semantically related items end up near each other. "
        "The figure on the next page shows five synthetic categories projected this way - "
        "points from the same category cluster together even though the projection never "
        "saw the category labels during training."
    )
    page.insert_textbox(pymupdf.Rect(72, 210, 540, 340), intro, fontsize=11, fontname="helv", color=(0.1, 0.1, 0.1))

    code = (
        "def project(embeddings, n_components=2):\n"
        "    reducer = UMAP(n_components=n_components)\n"
        "    return reducer.fit_transform(embeddings)\n"
        "\n"
        "coords = project(model.encode(items))\n"
        "plot_clusters(coords, labels=categories)"
    )
    y = 360
    for line in code.split("\n"):
        page.insert_text((80, y), line, fontsize=10, fontname="Courier")
        y += 16

    page2 = pdf.new_page(width=612, height=792)
    page2.insert_textbox(pymupdf.Rect(72, 40, 540, 70), "3.2  Cluster Projection", fontsize=14, fontname="helv", color=(0.15, 0.15, 0.4))
    page2.insert_image(pymupdf.Rect(72, 80, 540, 400), filename=str(chart_path))
    page2.insert_textbox(
        pymupdf.Rect(72, 405, 540, 430), "Figure 3.2 - Embedding clusters by category", fontsize=10, fontname="helv", color=(0.35, 0.35, 0.35)
    )
    discussion = (
        "Each marker is one item; color and label mark which synthetic category it belongs "
        "to. The projection groups items from the same category into visually distinct "
        "regions, with looser boundaries where categories are conceptually closer to one "
        "another - a useful diagnostic before trusting an embedding for downstream retrieval."
    )
    page2.insert_textbox(pymupdf.Rect(72, 440, 540, 560), discussion, fontsize=11, fontname="helv", color=(0.1, 0.1, 0.1))

    pdf.save(out_path)


async def _set_theme(app: PinaxApp) -> None:
    app.screen.action_set_theme(THEME)


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
    chart_path = DEMO_DIR / "clusters.png"
    pdf_path = DEMO_DIR / "embedding-notes.pdf"
    _build_chart(chart_path)
    _build_demo_pdf(pdf_path, chart_path)

    # A code block + a table are the two most distinctive rendering features to show off.
    app = PinaxApp(initial_path=str(DEMO_DIR / "architecture-spec.md"))
    async with app.run_test(size=(150, 42)) as pilot:
        await pilot.pause(0.3)
        await _set_theme(app)
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
    print(f"PDF demo (open this yourself in a real terminal for an image-rendering screenshot): {pdf_path}")


if __name__ == "__main__":
    asyncio.run(main())
