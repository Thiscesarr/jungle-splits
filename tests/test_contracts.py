"""Contracts the app relies on: the sheet's format, the default config, the translations, and surviving
damaged files. These catch breakage that unit tests of the logic can't (a restructured sheet, a missing
translation, a corrupted save)."""
import csv
import io
import json
import os
import re
import string
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sheet
from detect import CampGold
from hotkeys import parse_combo
from i18n import LANGUAGES, STRINGS
from settings_window import ACTIONS
from sound import THEMES
from tracker import DEFAULT_CAMP_GOLD, RECALL, RouteStats, camp_key, parse_clock

ROOT = Path(__file__).resolve().parents[1]
HEADER = ["Champion", "Patch", "Camps", "Smite(s)", "Time", "Path", "Link", "Player"]


def check_sheet(test: unittest.TestCase, text: str, where: str) -> None:
    rows = list(csv.reader(io.StringIO(text)))
    header = next((r for r in rows if r and r[0].strip() == "Champion"), None)
    test.assertIsNotNone(header, f"{where}: header row missing")
    test.assertEqual([c.strip() for c in header[:8]], HEADER, f"{where}: columns moved")
    routes = sheet.parse_sheet(text)
    test.assertGreater(sum(len(r) for r in routes.values()), 100, f"{where}: too few clears parsed")
    for champion, champion_routes in routes.items():
        for route in champion_routes:
            context = f"{where}: {route.champion} {route.path}"
            for camp in route.camps:
                test.assertTrue(camp_key(camp) in DEFAULT_CAMP_GOLD or camp_key(camp) == RECALL,
                                f"{context}: unknown camp {camp!r}")
            test.assertTrue(90 <= route.record <= 300, f"{context}: odd time {route.record}")
            test.assertIn(route.smites, (1, 2), context)
            test.assertTrue(not route.video or route.video.startswith("https://"), context)
            test.assertRegex(route.patch, r"^\d+\.\d+", context)


class SheetContractTest(unittest.TestCase):
    def test_bundled_sheet(self):
        check_sheet(self, (ROOT / "clears_fallback.csv").read_text(encoding="utf-8"), "bundled copy")

    @unittest.skipUnless(os.environ.get("JS_ONLINE_TESTS"), "set JS_ONLINE_TESTS=1 to check the live sheet")
    def test_live_sheet(self):
        """Early warning that the online sheet changed format (runs in CI)."""
        with urllib.request.urlopen(sheet.SHEET_URL, timeout=30) as response:
            check_sheet(self, response.read().decode("utf-8"), "live sheet")

    def test_garbage_cache_falls_back_to_bundled_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / sheet.CACHE_NAME).write_bytes(b"\x00\xff<html>Sign in</html>")
            routes = sheet.load_routes(Path(tmp), ROOT / "clears_fallback.csv")
            self.assertIn(sheet.norm("Lee Sin"), routes)

    def test_rows_with_missing_or_odd_cells_are_skipped(self):
        text = ("Champion,Patch,Camps,Smite(s),Time,Path,Link,Player\n"
                "Lee Sin,26.01,6,1,02:45,Red->Krugs->Raptors->Wolves->Gromp->Blue,https://x,P,AD/AD\n"
                "Meta Junglers:,,,,,,,,\n"
                "Broken,26.01,6,one,2:45,Red->Krugs\n"
                "Short row\n"
                "Ivern,26.01,6,1,not a time,Red->Krugs,,\n")
        routes = sheet.parse_sheet(text)
        self.assertEqual(sorted(routes), ["broken", "leesin"])
        self.assertEqual(routes["broken"][0].smites, 1)


class ConfigContractTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

    def test_every_action_has_a_valid_default_hotkey(self):
        hotkeys = self.config["hotkeys"]
        self.assertEqual(set(hotkeys), set(ACTIONS))
        combos = [c for c in hotkeys.values() if c]
        for combo in combos:
            parse_combo(combo)
        self.assertEqual(len(combos), len({c.lower() for c in combos}), "two actions share a hotkey")

    def test_values(self):
        self.assertEqual(parse_clock(self.config["camp_spawn"]), 55.0)
        self.assertIn(self.config["sounds"]["theme"], THEMES)
        self.assertTrue(0 < self.config["overlay"]["opacity"] <= 1)
        for path in self.config["fallback_routes"]:
            self.assertTrue(all(camp_key(c) in DEFAULT_CAMP_GOLD for c in sheet.parse_path(path)))


class TranslationContractTest(unittest.TestCase):
    def test_same_placeholders_in_every_language(self):
        for key, texts in STRINGS.items():
            self.assertEqual(set(texts), set(LANGUAGES), key)
            fields = {lang: {f for _, f, _, _ in string.Formatter().parse(text) if f} for lang, text in texts.items()}
            self.assertEqual(fields["pt"], fields["en"], f"{key}: {fields}")

    def test_every_key_used_in_the_code_exists(self):
        used = set()
        for source in ROOT.glob("*.py"):
            used |= set(re.findall(r"""\bt\(\s*["']([a-z0-9_]+)["']""", source.read_text(encoding="utf-8")))
        # Keys built at runtime.
        used |= {f"act_{a}" for a in ACTIONS} | {f"theme_{k}" for k in THEMES}
        used |= {f"tab_{k}" for k in ("general", "hotkeys", "sounds", "records", "about")}
        missing = sorted(k for k in used if k not in STRINGS)
        self.assertEqual(missing, [])


class DamagedFilesTest(unittest.TestCase):
    def test_corrupt_route_stats_start_fresh_and_keep_a_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "route.json"
            path.write_text('{"camps": ["Red", "Gro', encoding="utf-8")  # cut off mid-write
            stats = RouteStats(path, ["Red", "Gromp"])
            self.assertIsNone(stats.pb)
            stats.save()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["camps"], ["Red", "Gromp"])
            self.assertTrue(list(Path(tmp).glob("route.*.corrupt.json")))

    def test_corrupt_camp_gold_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "camp_gold.json").write_text("not json", encoding="utf-8")
            self.assertEqual(CampGold(Path(tmp) / "camp_gold.json").expected("Red"), (90, False))


if __name__ == "__main__":
    unittest.main()
