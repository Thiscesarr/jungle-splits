import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from i18n import LANGUAGES, STRINGS, set_language, t
from settings_window import parse_target
from sheet import norm, parse_sheet, routes_for_champion

ROOT = Path(__file__).resolve().parents[1]
RECALL_ROUTE = "Raptors->Red->Krugs->Recall->Wolves->Gromp->Blue"


class SmitesTest(unittest.TestCase):
    def setUp(self):
        self.routes = parse_sheet((ROOT / "clears_fallback.csv").read_text(encoding="utf-8"))

    def test_routes_follow_the_chosen_smite_count(self):
        one = routes_for_champion(self.routes, "Lee Sin", 1)
        two = routes_for_champion(self.routes, "Lee Sin", 2)
        self.assertEqual(one[0].smites, 1)
        self.assertEqual(two[0].record, 153.0)  # the 2-smite 2:33 comes first in 2-smite mode
        self.assertTrue(all(r.smites == 2 for r in two))
        # Every path stays available in both modes, without a record when not clocked that way.
        self.assertEqual({r.path for r in one}, {r.path for r in two})
        recall_two = next(r for r in two if r.path == RECALL_ROUTE)
        self.assertIsNone(recall_two.record)

    def test_pb_files_are_separate_per_smite_count(self):
        one = next(r for r in routes_for_champion(self.routes, "Lee Sin", 1) if r.path == RECALL_ROUTE)
        two = next(r for r in routes_for_champion(self.routes, "Lee Sin", 2) if r.path == RECALL_ROUTE)
        self.assertEqual(one.stats_name, RECALL_ROUTE)  # keeps existing 1-smite PB files
        self.assertNotEqual(one.stats_name, two.stats_name)

    def test_video_links(self):
        recall = next(r for r in self.routes[norm("Lee Sin")] if r.path == RECALL_ROUTE)
        self.assertTrue(recall.video.startswith("https://www.youtube.com/"))

    def test_unknown_champion_uses_fallback_routes(self):
        routes = routes_for_champion(self.routes, "Nobody", 2, fallback=["Red->Krugs"])
        self.assertEqual([r.path for r in routes], ["Red->Krugs"])
        self.assertEqual(routes[0].smites, 2)


class TranslationTest(unittest.TestCase):
    def test_every_string_has_every_language(self):
        for key, texts in STRINGS.items():
            self.assertEqual(set(texts), set(LANGUAGES), key)

    def test_switching_language(self):
        set_language("pt")
        self.assertEqual(t("col_camp"), "CAMPO")
        set_language("en")
        self.assertEqual(t("col_camp"), "CAMP")
        self.assertIn("2:50", t("target_hit", time="2:50.0"))

    def test_target_parsing(self):
        self.assertEqual(parse_target("2:50"), 170.0)
        self.assertEqual(parse_target("2:44.5"), 164.5)
        self.assertIsNone(parse_target(""))
        for bad in ("170", "abc", "0:10", "99:00"):
            with self.assertRaises(ValueError):
                parse_target(bad)


if __name__ == "__main__":
    unittest.main()
