"""What the overlay shows (display.py): presets, and saved choices read back safely."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import display
from display import CUSTOM, PARTS, PRESET_ORDER, PRESETS, clock_only, normalize, preset_of


class DisplayTest(unittest.TestCase):
    def test_nothing_saved_shows_everything_as_before(self):
        """Players updating from a version without this setting keep the overlay they had."""
        for saved in (None, {}, [], "full", 3):
            self.assertEqual(normalize(saved), PRESETS["full"], saved)

    def test_saved_choices_are_cleaned(self):
        saved = {"camps": False, "verdict": 0, "footer": "yes", "unknown_part": False}
        shown = normalize(saved)
        self.assertEqual(set(shown), set(PARTS))
        self.assertIs(shown["camps"], False)
        self.assertIs(shown["verdict"], False)
        self.assertIs(shown["footer"], True)
        self.assertIs(shown["header"], True)  # missing: shown

    def test_presets_are_recognized(self):
        for name in PRESET_ORDER:
            self.assertEqual(preset_of(PRESETS[name]), name)
            self.assertEqual(set(PRESETS[name]), set(PARTS))

    def test_any_other_choice_is_custom(self):
        for name in PRESET_ORDER:
            for part in PARTS:
                changed = dict(PRESETS[name], **{part: not PRESETS[name][part]})
                self.assertNotIn(preset_of(changed), (name,), (name, part))
        self.assertEqual(preset_of({**PRESETS["full"], "runes": False}), CUSTOM)

    def test_presets_match_their_names(self):
        self.assertFalse(any(PRESETS["clock"].values()))  # only the clock, always drawn
        self.assertEqual({p for p, on in PRESETS["splits"].items() if on}, {"delta", "camps"})
        self.assertTrue(all(PRESETS["full"].values()))

    def test_clock_only(self):
        self.assertTrue(clock_only(PRESETS["clock"]))
        self.assertTrue(clock_only({**PRESETS["clock"], "delta": True}))  # the delta fits under the clock
        for part in PARTS:
            if part != "delta":
                self.assertFalse(clock_only({**PRESETS["clock"], part: True}), part)
        self.assertFalse(clock_only(PRESETS["splits"]))
        self.assertFalse(clock_only(None))

    def test_parts_are_in_overlay_order(self):
        self.assertEqual(PARTS[0], "header")
        self.assertEqual(PARTS[-1], "footer")
        self.assertEqual(len(set(PARTS)), len(PARTS))
        self.assertEqual(display.PRESET_ORDER, tuple(PRESETS))


if __name__ == "__main__":
    unittest.main()
