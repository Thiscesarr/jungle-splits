"""Draws the overlay as an image with Pillow, for a window with per-pixel transparency (layered.py).

The panel is translucent "glass" while text and sector colors stay fully opaque and crisp, with rounded
corners and a soft shadow, which a Tk canvas (one alpha for the whole window) cannot do.

Drawing is split in two so the game loses as little as possible to the overlay:
- the overlay records what it would draw into a Frame (plain tuples, cheap to build and compare), and a
  frame equal to the last one is not drawn at all: waiting for a game, the overlay draws nothing;
- the Renderer turns a Frame into an image from caches: the panel (shadow, glass, brand stripe), every
  shape and every piece of text are rasterized once and then only composited.
"""
from __future__ import annotations

import math
from collections import OrderedDict

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# Shapes are drawn this many times larger and scaled down: Pillow doesn't anti-alias rounded corners.
SUPERSAMPLE = 4

# Font faces: candidate files (Windows fonts folder), variable-font style, and whether digits are drawn
# in fixed-width cells (Bahnschrift's digits are proportional, which would make a running clock jitter).
FACES: dict[str, tuple[tuple[str, ...], bytes | None, bool]] = {
    "ui": (("segoeui.ttf", "arial.ttf"), None, False),
    "ui_semibold": (("seguisb.ttf", "segoeui.ttf", "arial.ttf"), None, False),
    "ui_bold": (("segoeuib.ttf", "arialbd.ttf"), None, False),
    "num": (("bahnschrift.ttf", "consola.ttf"), b"SemiBold", True),
    "num_bold": (("bahnschrift.ttf", "consolab.ttf"), b"Bold", True),
    "symbol": (("seguisym.ttf", "segoeui.ttf", "arial.ttf"), None, False),
}
DIGITS = "0123456789"


def rgba(color, alpha: int = 255) -> tuple[int, int, int, int]:
    """'#rrggbb' or an (r, g, b[, a]) tuple as RGBA."""
    if isinstance(color, str):
        value = color.lstrip("#")
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha
    return tuple(color) if len(color) == 4 else (*color, alpha)


class Frame:
    """What one overlay frame shows, in panel coordinates (0, 0 is the panel's top-left corner)."""

    def __init__(self, width: int):
        self.width = width
        self.height = 0
        self.ops: list[tuple] = []

    def rect(self, x0: int, y0: int, x1: int, y1: int, fill, radius: int = 0) -> None:
        self.ops.append(("rect", round(x0), round(y0), round(x1), round(y1), rgba(fill), round(radius)))

    def outline(self, x0: int, y0: int, x1: int, y1: int, color, width: int, radius: int = 0) -> None:
        self.ops.append(("outline", round(x0), round(y0), round(x1), round(y1), rgba(color), round(width),
                         round(radius)))

    def text(self, x: int, y: int, text: str, color, font: tuple[str, int], anchor: str = "center") -> None:
        """anchor like Tk's: n/nw/ne put y on the top of the line, center/w/e on its middle."""
        self.ops.append(("text", round(x), round(y), text, rgba(color), font, anchor))

    def key(self) -> tuple:
        return self.width, self.height, tuple(self.ops)


class LRU(OrderedDict):
    def __init__(self, size: int):
        super().__init__()
        self.size = size

    def get_or(self, key, make):
        if key in self:
            self.move_to_end(key)
            return self[key]
        value = self[key] = make()
        if len(self) > self.size:
            self.popitem(last=False)
        return value


class Renderer:
    def __init__(self):
        self._fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
        self._glyphs: dict[tuple[str, str], bool] = {}
        self._notdefs: dict[str, bytes] = {}
        self._layouts = LRU(4096)
        self._texts = LRU(512)
        self._shapes = LRU(256)
        self._panels = LRU(8)

    # --- fonts -------------------------------------------------------------------------------------

    def font(self, face: str, size: int) -> ImageFont.FreeTypeFont:
        key = (face, size)
        if key not in self._fonts:
            files, variation, _ = FACES[face]
            font = None
            for file in files:
                try:
                    font = ImageFont.truetype(file, size)
                except OSError:
                    continue
                if variation:
                    try:
                        font.set_variation_by_name(variation)
                    except (OSError, ValueError):
                        pass  # not a variable font (the fallback): its own weight is fine
                break
            self._fonts[key] = font or ImageFont.load_default(size)
        return self._fonts[key]

    def _has_glyph(self, face: str, ch: str) -> bool:
        key = (face, ch)
        if key not in self._glyphs:
            font = self.font(face, 20)
            self._glyphs[key] = ch.isspace() or bytes(font.getmask(ch)) != self._notdef(face)
        return self._glyphs[key]

    def _notdef(self, face: str) -> bytes:
        if face not in self._notdefs:
            self._notdefs[face] = bytes(self.font(face, 20).getmask("￿"))
        return self._notdefs[face]

    def _layout(self, text: str, face: str, size: int) -> tuple[list[tuple[float, str, ImageFont.FreeTypeFont]], float]:
        """([(x, run, font)], width): runs of text in one font, symbols the face lacks (▶ ✕) in the
        symbol font, as Windows' font fallback did for Tk; digits of number faces in equal cells."""
        def make():
            primary = self.font(face, size)
            tabular = FACES[face][2]
            digit = max(primary.getlength(d) for d in DIGITS) if tabular else 0.0
            runs: list[tuple[float, str, ImageFont.FreeTypeFont]] = []
            x, start, run, run_font = 0.0, 0.0, "", None
            for ch in text:
                font = primary if self._has_glyph(face, ch) else self.font("symbol", size)
                if tabular and ch in DIGITS:
                    if run:
                        runs.append((start, run, run_font))
                        x, run = start + run_font.getlength(run), ""
                    runs.append((x + (digit - font.getlength(ch)) / 2, ch, font))
                    x += digit
                    continue
                if font is not run_font and run:
                    runs.append((start, run, run_font))
                    x, run = start + run_font.getlength(run), ""
                if not run:
                    start, run_font = x, font
                run += ch
            if run:
                runs.append((start, run, run_font))
                x = start + run_font.getlength(run)
            return runs, x
        return self._layouts.get_or((text, face, size), make)

    def measure(self, text: str, face: str, size: int) -> float:
        """Width of text in pixels, as drawn."""
        return self._layout(text, face, size)[1]

    def line_height(self, face: str, size: int) -> int:
        ascent, descent = self.font(face, size).getmetrics()
        return ascent + descent

    # --- sprites -----------------------------------------------------------------------------------

    def _text_sprite(self, text: str, face: str, size: int, color: tuple) -> tuple[Image.Image, int]:
        """(sprite, left padding): the text in color on a transparent background, its top on the line's top."""
        def make():
            runs, length = self._layout(text, face, size)
            pad = max(2, size // 6)  # room for glyphs that overhang their advance (italics, "j", "f")
            width = math.ceil(length) + 2 * pad
            ascent = self.font(face, size).getmetrics()[0]
            mask = Image.new("L", (max(1, width), max(1, self.line_height(face, size))), 0)
            draw = ImageDraw.Draw(mask)
            for x, run, font in runs:
                # Every run on the face's baseline, whatever font it comes from.
                draw.text((pad + x, ascent), run, font=font, fill=255, anchor="ls")
            sprite = Image.new("RGBA", mask.size, color[:3] + (0,))
            sprite.putalpha(mask if color[3] == 255 else mask.point(lambda v: v * color[3] // 255))
            return sprite, pad
        return self._texts.get_or((text, face, size, color), make)

    def _shape(self, width: int, height: int, fill: tuple | None, outline: tuple | None, line: int,
               radius: int) -> Image.Image:
        def make():
            k = SUPERSAMPLE
            big = Image.new("RGBA", (width * k, height * k), (0, 0, 0, 0))
            draw = ImageDraw.Draw(big)
            box = (0, 0, width * k - 1, height * k - 1)
            r = min(radius, width // 2, height // 2) * k
            if fill:
                draw.rounded_rectangle(box, r, fill=fill)
            if outline:
                draw.rounded_rectangle(box, r, outline=outline, width=line * k)
            return big.resize((width, height), Image.Resampling.BOX)
        return self._shapes.get_or((width, height, fill, outline, line, radius), make)

    def panel(self, width: int, height: int, opacity: float, radius: int, margin: int, background,
              stripe: tuple, stripe_height: int) -> Image.Image:
        """Shadow, translucent glass, a faint top sheen, the hairline edge and the brand stripe."""
        def make():
            k = SUPERSAMPLE
            full = (width + 2 * margin, height + 2 * margin)
            image = Image.new("RGBA", full, (0, 0, 0, 0))
            # The panel's shape, drawn large and scaled down for smooth corners.
            mask = Image.new("L", (width * k, height * k), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, width * k - 1, height * k - 1), radius * k, fill=255)
            mask = mask.resize((width, height), Image.Resampling.BOX)
            if margin:
                shadow = Image.new("L", full, 0)
                ImageDraw.Draw(shadow).rounded_rectangle(
                    (margin, margin + margin // 4, margin + width - 1, margin + height - 1 + margin // 4),
                    radius, fill=round(120 * opacity))
                shadow = shadow.filter(ImageFilter.GaussianBlur(margin / 2.5))
                # Only outside the panel: under the glass it would make the panel darker than its opacity.
                outside = Image.new("L", full, 255)
                outside.paste(ImageChops.invert(mask), (margin, margin))
                image.putalpha(ImageChops.multiply(shadow, outside))
            glass = Image.new("RGBA", (width, height), rgba(background, round(255 * opacity)))
            sheen = Image.linear_gradient("L").resize((width, height)).point(lambda v: max(0, 14 - v * 14 // 120))
            glass.alpha_composite(Image.merge("RGBA", (*Image.new("RGB", (width, height), (255, 255, 255)).split(),
                                                       sheen)))
            stripe_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(stripe_layer)
            for i, color in enumerate(stripe):
                draw.rectangle((i * width // len(stripe), 0, (i + 1) * width // len(stripe), stripe_height - 1),
                               fill=rgba(color))
            glass.alpha_composite(stripe_layer)
            glass.putalpha(Image.composite(glass.getchannel("A"), Image.new("L", (width, height), 0), mask))
            edge = self._shape(width, height, None, (255, 255, 255, 26), 1, radius)
            glass.alpha_composite(edge)
            image.alpha_composite(glass, (margin, margin))
            return image
        return self._panels.get_or((width, height, round(opacity, 3), radius, margin, background, stripe,
                                    stripe_height), make)

    # --- frames ------------------------------------------------------------------------------------

    def render(self, frame: Frame, panel: Image.Image, margin: int) -> Image.Image:
        image = panel.copy()
        for op in frame.ops:
            kind = op[0]
            if kind == "rect":
                _, x0, y0, x1, y1, fill, radius = op
                if x1 > x0 and y1 > y0:
                    image.alpha_composite(self._shape(x1 - x0, y1 - y0, fill, None, 0, radius),
                                          (x0 + margin, y0 + margin))
            elif kind == "outline":
                _, x0, y0, x1, y1, color, line, radius = op
                if x1 > x0 and y1 > y0:
                    image.alpha_composite(self._shape(x1 - x0, y1 - y0, None, color, line, radius),
                                          (x0 + margin, y0 + margin))
            elif kind == "text":
                _, x, y, text, color, (face, size), anchor = op
                if not text:
                    continue
                sprite, pad = self._text_sprite(text, face, size, color)
                width = sprite.width - 2 * pad
                if anchor in ("w", "nw"):
                    left = x
                elif anchor in ("e", "ne"):
                    left = x - width
                else:
                    left = x - width // 2
                top = y if anchor in ("n", "nw", "ne") else y - sprite.height // 2
                left, top = left - pad + margin, top + margin
                # alpha_composite needs the sprite inside the image: clip what falls outside.
                cx, cy = max(0, -left), max(0, -top)
                cw = min(sprite.width, image.width - left) - cx
                ch = min(sprite.height, image.height - top) - cy
                if cw > 0 and ch > 0:
                    image.alpha_composite(sprite, (left + cx, top + cy), (cx, cy, cx + cw, cy + ch))
        return image
