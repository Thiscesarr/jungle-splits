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


# Every size Windows asks for at 100% to 300% display scaling: a missing one is made by stretching another.
ICON_SIZES = (16, 20, 24, 32, 40, 48, 60, 64, 72, 96, 128, 256)


def stopwatch(size: int, background: bool = True) -> Image.Image:
    """The mark at this size, drawn 8x larger and scaled down for smooth edges. Small sizes aren't the
    big drawing shrunk (its thin strokes turn to a blur): the watch fills more of the tile and its ring
    and hand get thicker, and details too small to read are left out."""
    k = 8 if size < 128 else 4
    big = size * k
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = big / 1024
    small, tiny = size < 96, size <= 24
    if background:
        d.rounded_rectangle((0, 0, big - 1, big - 1), radius=230 * u, fill=(17, 20, 26))
        if not small:
            d.rounded_rectangle((10 * u, 10 * u, big - 10 * u, big - 10 * u), radius=220 * u,
                                outline=(38, 43, 54), width=round(8 * u))
    if tiny:
        cx, cy, r, ring, hand, hub = 512 * u, 560 * u, 390 * u, 150 * u, 96 * u, 86 * u
    elif small:
        cx, cy, r, ring, hand, hub = 512 * u, 572 * u, 356 * u, 112 * u, 66 * u, 64 * u
    else:
        cx, cy, r, ring, hand, hub = 512 * u, 566 * u, 318 * u, 78 * u, 46 * u, 50 * u
    # Crown and side button.
    top = cy - r
    if tiny:
        d.rounded_rectangle((432 * u, top - 96 * u, 592 * u, top + 10 * u), radius=20 * u, fill=PAPER)
    else:
        crown = 70 * u if small else 60 * u
        d.rounded_rectangle((cx - crown, top - 98 * u, cx + crown, top - 34 * u), radius=18 * u, fill=PAPER)
        d.rectangle((cx - 20 * u - (6 * u if small else 0), top - 43 * u, cx + 20 * u + (6 * u if small else 0),
                     top + 14 * u), fill=PAPER)
        if not small:
            d.line((cx + 236 * u, cy - 300 * u, cx + 276 * u, cy - 260 * u), fill=PAPER, width=round(44 * u))
    # Ring in three sectors with small gaps.
    box = (cx - r, cy - r, cx + r, cy + r)
    gap = 5 if tiny else 3
    for start, end, color in ((210 + gap, 330 - gap, PURPLE), (330 + gap, 90 - gap, GREEN), (90 + gap, 210 - gap, RED)):
        d.arc(box, start, end, fill=color, width=round(ring))
    # Hand and hub.
    reach = (r - ring) * 0.86
    tip = (cx + reach * 0.66, cy - reach * 0.75) if small else (cx + 150 * u, cy - 170 * u)
    d.line((cx, cy, *tip), fill=PAPER, width=round(hand))
    d.ellipse((cx - hub, cy - hub, cx + hub, cy + hub), fill=PAPER)
    if not tiny:
        dot = hub * 0.4
        d.ellipse((cx - dot, cy - dot, cx + dot, cy + dot), fill=INK)
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


def flag(country: str, path: Path) -> None:
    """Small flags for the README: Windows doesn't draw flag emoji, so the bilingual links use images."""
    w, h = 240, 160
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    if country == "br":
        d.rectangle((0, 0, w, h), fill=(0, 156, 59))
        d.polygon([(w * 0.085, h / 2), (w / 2, h * 0.115), (w * 0.915, h / 2), (w / 2, h * 0.885)], fill=(255, 223, 0))
        r = h * 0.26
        d.ellipse((w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r), fill=(0, 39, 118))
        d.arc((w / 2 - r * 1.6, h / 2 - r * 0.55, w / 2 + r * 1.6, h / 2 + r * 2.4), 236, 304, fill="white", width=7)
    else:
        stripe = h / 13
        for i in range(0, 13, 2):
            d.rectangle((0, i * stripe, w, (i + 1) * stripe), fill=(178, 34, 52))
        d.rectangle((0, 0, w * 0.4, stripe * 7), fill=(60, 59, 110))
        for row in range(5):
            for col in range(6):
                x, y = w * 0.4 * (col + 0.5) / 6, stripe * 7 * (row + 0.5) / 5
                d.ellipse((x - 4, y - 4, x + 4, y + 4), fill="white")
    img.resize((48, 32), Image.LANCZOS).save(path)


def main() -> None:
    assets, docs = ROOT / "src" / "assets", ROOT / "docs"
    assets.mkdir(exist_ok=True)
    docs.mkdir(exist_ok=True)
    icon = stopwatch(512)
    icon.save(assets / "icon.png")
    # Each size of the .ico is its own drawing (see stopwatch), not the big one scaled down.
    frames = [stopwatch(n) for n in ICON_SIZES]
    frames[-1].save(assets / "icon.ico", sizes=[(n, n) for n in ICON_SIZES], append_images=frames[:-1])
    banner(docs / "banner.png")
    (docs / "flags").mkdir(exist_ok=True)
    flag("us", docs / "flags" / "us.png")
    flag("br", docs / "flags" / "br.png")
    print("assets written")


if __name__ == "__main__":
    main()
