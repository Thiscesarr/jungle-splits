"""Listing and deleting saved records from the Settings window."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import records
from tracker import RouteStats, slug


class RecordsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        for champion, camps, name, pb in (("Vi", ["Red", "Krugs"], "Red->Krugs", 168.1),
                                          ("Vi", ["Blue", "Gromp"], "Blue->Gromp-2smite", None),
                                          ("Lee Sin", ["Raptors", "Red"], "Raptors->Red", 175.0)):
            stats = RouteStats(self.data / slug(champion) / f"{slug(name)}.json", camps)
            stats.attempts = 3
            stats.pb = [pb - 10, pb] if pb else None
            stats.save()
        (self.data / "logs").mkdir()
        (self.data / "logs" / "run.csv").write_text("x")
        (self.data / "camp_gold.json").write_text("{}")
        (self.data / "vi" / "old.corrupt.json").write_text("{")
        RouteStats(self.data / "vi" / "never-run.json", ["Red"]).save()  # selected once, never attempted
        self.names = records.champion_names(["Lee Sin", "Vi"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_lists_every_route_with_its_pb(self):
        listed = records.list_records(self.data, self.names)
        self.assertEqual([(r.champion, r.camps, r.smites, r.pb, r.attempts) for r in listed], [
            ("Lee Sin", ("Raptors", "Red"), 1, 175.0, 3),
            ("Vi", ("Blue", "Gromp"), 2, None, 3),
            ("Vi", ("Red", "Krugs"), 1, 168.1, 3),
        ])

    def test_deletes_only_the_chosen_routes(self):
        vi = [r for r in records.list_records(self.data, self.names) if r.champion == "Vi"]
        self.assertEqual(records.delete_records([vi[1].path]), 1)
        left = records.list_records(self.data, self.names)
        self.assertEqual([(r.champion, r.camps) for r in left], [("Lee Sin", ("Raptors", "Red")), ("Vi", ("Blue", "Gromp"))])
        self.assertTrue((self.data / "camp_gold.json").exists() and (self.data / "logs" / "run.csv").exists())

    def test_deleting_twice_is_harmless(self):
        lee = records.list_records(self.data, self.names)[0]
        self.assertEqual(records.delete_records([lee.path, lee.path]), 1)
        self.assertFalse((self.data / "lee-sin").exists())  # an empty champion folder goes too

    def test_unknown_folder_gets_a_readable_name(self):
        self.assertEqual(records.list_records(self.data, {})[0].champion, "Lee Sin")


if __name__ == "__main__":
    unittest.main()
