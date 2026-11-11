"""The overlay's drawing (render.py): per-pixel alpha, fonts, and the caches that keep it cheap."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from render import Frame, Renderer, rgba

MARGIN = 6


def frame(*ops) -> Frame:
    fr = Frame(200)
    fr.height = 60
    for op in ops:
        op(fr)
    return fr


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.r = Renderer()
        self.panel = self.r.panel(200, 60, 0.5, 10, MARGIN, "#0e1014", ("#a63dff", "#1fc85f", "#e8333a"), 3)

    def alpha(self, image, x, y) -> int:
        return image.getpixel((x + MARGIN, y + MARGIN))[3]

    def test_glass_is_translucent_but_text_is_opaque(self):
        image = self.r.render(frame(lambda f: f.text(10, 30, "8888", "#ffffff", ("num_bold", 30), "w")),
                              self.panel, MARGIN)
        self.assertEqual(image.size, (200 + 2 * MARGIN, 60 + 2 * MARGIN))
        self.assertAlmostEqual(self.alpha(image, 150, 40), 128, delta=12)  # glass at opacity 0.5
        self.assertEqual(self.alpha(image, 100, 1), 255)  # the brand stripe
        text = image.crop((MARGIN + 10, MARGIN + 15, MARGIN + 80, MARGIN + 45)).getchannel("A")
        self.assertEqual(text.getextrema()[1], 255)  # glyphs fully opaque on the glass

    def test_rounded_corners_and_shadow_are_see_through(self):
        image = self.r.render(frame(), self.panel, MARGIN)
        self.assertLess(self.alpha(image, 0, 0), 128)  # corner cut by the radius
        self.assertEqual(image.getpixel((0, 0))[3], 0)  # outside the shadow
        self.assertGreater(image.getpixel((MARGIN + 100, MARGIN + 60 + 2))[3], 0)  # shadow under the panel

    def test_clock_digits_take_the_same_width(self):
        """A running clock must not jitter as its digits change."""
        widths = {self.r.measure(text, "num_bold", 30) for text in ("1:11.1", "8:88.8", "0:00.0", "2:47.3")}
        self.assertEqual(len(widths), 1)

    def test_symbols_missing_from_segoe_ui_still_draw(self):
        """▶ and ✕ aren't in Segoe UI; Tk got them from Windows' font fallback, the renderer does it itself."""
        for symbol in "▶✕":
            image = self.r.render(frame(lambda f: f.text(100, 30, symbol, "#ffffff", ("ui", 20))), self.panel,
                                  MARGIN)
            ink = image.crop((MARGIN + 85, MARGIN + 15, MARGIN + 115, MARGIN + 45)).convert("L")
            self.assertGreater(ink.getextrema()[1], 200, symbol)

    def test_frames_compare_by_content(self):
        a = frame(lambda f: f.rect(0, 0, 10, 10, "#ffffff", 3), lambda f: f.text(1, 1, "x", (1, 2, 3), ("ui", 9)))
        b = frame(lambda f: f.rect(0, 0, 10, 10, "#ffffff", 3), lambda f: f.text(1, 1, "x", (1, 2, 3), ("ui", 9)))
        self.assertEqual(a.key(), b.key())
        b.text(1, 1, "y", "#000000", ("ui", 9))
        self.assertNotEqual(a.key(), b.key())

    def test_text_partly_outside_is_clipped_not_an_error(self):
        image = self.r.render(frame(lambda f: f.text(-40, -10, "Krugs Raptors", "#ffffff", ("ui", 30), "nw"),
                                    lambda f: f.text(190, 55, "Krugs Raptors", "#ffffff", ("ui", 30), "nw")),
                              self.panel, MARGIN)
        self.assertEqual(image.size, (200 + 2 * MARGIN, 60 + 2 * MARGIN))

    def test_rgba(self):
        self.assertEqual(rgba("#a63dff"), (0xa6, 0x3d, 0xff, 255))
        self.assertEqual(rgba("#a63dff", 30), (0xa6, 0x3d, 0xff, 30))
        self.assertEqual(rgba((1, 2, 3, 4)), (1, 2, 3, 4))


if __name__ == "__main__":
    unittest.main()
