"""Draws the app icon (assets/icon.ico, icon.png) and the README banner (docs/banner.png).

The mark is a stopwatch whose ring is split into the three F1 sector colors.
Run from the repo root: python tools/make_assets.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
PURPLE, GREEN, RED = (166, 61, 255), (31, 200, 95), (232, 51, 58)
INK, PAPER = (14, 16, 20), (238, 240, 243)
FONTS = Path("C:/Windows/Fonts")


def stopwatch(size: int, background: bool = True) -> Image.Image:
    """The mark, drawn 4x larger and scaled down for smooth edges."""
    big = size * 4
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = big / 1024
    if background:
        d.rounded_rectangle((0, 0, big - 1, big - 1), radius=230 * u, fill=(17, 20, 26))
        d.rounded_rectangle((10 * u, 10 * u, big - 10 * u, big - 10 * u), radius=220 * u,
                            outline=(38, 43, 54), width=round(8 * u))
    cx, cy, r, ring = 512 * u, 566 * u, 318 * u, 78 * u
    # Crown and side button.
    d.rounded_rectangle((452 * u, 150 * u, 572 * u, 214 * u), radius=18 * u, fill=PAPER)
    d.rectangle((492 * u, 205 * u, 532 * u, 262 * u), fill=PAPER)
    d.line((cx + 236 * u, cy - 300 * u, cx + 276 * u, cy - 260 * u), fill=PAPER, width=round(44 * u))
    # Ring in three sectors with small gaps.
    box = (cx - r, cy - r, cx + r, cy + r)
    for start, end, color in ((213, 327, PURPLE), (333, 87, GREEN), (93, 207, RED)):
        d.arc(box, start, end, fill=color, width=round(ring))
    # Hand and hub.
    d.line((cx, cy, cx + 150 * u, cy - 170 * u), fill=PAPER, width=round(46 * u))
    d.ellipse((cx - 50 * u, cy - 50 * u, cx + 50 * u, cy + 50 * u), fill=PAPER)
    d.ellipse((cx - 20 * u, cy - 20 * u, cx + 20 * u, cy + 20 * u), fill=INK)
    return img.resize((size, size), Image.LANCZOS)


def banner(path: Path) -> None:
    width, height = 1280, 400
    img = Image.new("RGB", (width, height), INK)
    glow = Image.new("RGB", (width, height), INK)
    g = ImageDraw.Draw(glow)
    for (x, y, color) in ((180, 120, PURPLE), (1100, 330, GREEN), (760, -40, RED)):
        g.ellipse((x - 260, y - 260, x + 260, y + 260), fill=tuple(c // 3 for c in color))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(120)), 0.9)
    img.paste(stopwatch(260), (110, 70), stopwatch(260))
    d = ImageDraw.Draw(img)
    title = ImageFont.truetype(str(FONTS / "segoeuib.ttf"), 96)
    tagline = ImageFont.truetype(str(FONTS / "segoeui.ttf"), 30)
    d.text((420, 105), "Jungle Splits", font=title, fill=PAPER)
    d.text((424, 225), "F1-style split timer for your League of Legends jungle clear", font=tagline,
           fill=(170, 178, 192))
    for i, color in enumerate((PURPLE, GREEN, RED)):
        d.rounded_rectangle((424 + i * 92, 295, 504 + i * 92, 307), radius=6, fill=color)
    img.save(path)


def main() -> None:
    assets, docs = ROOT / "assets", ROOT / "docs"
    assets.mkdir(exist_ok=True)
    docs.mkdir(exist_ok=True)
    icon = stopwatch(512)
    icon.save(assets / "icon.png")
    icon.save(assets / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    banner(docs / "banner.png")
    print("assets written")


if __name__ == "__main__":
    main()
