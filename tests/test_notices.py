"""Notices published in docs/notices.json: who sees which, and that a broken file never gets in the way."""
import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import notices

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 5)


def notice(**fields):
    return {"id": "n1", "title": {"pt": "Título", "en": "Title"}, "text": {"pt": "Texto", "en": "Text"}, **fields}


def parse(items, version="1.0.4", language="pt", seen=()):
    return notices.parse_notices({"notices": items}, version, language, set(seen), TODAY)


class NoticesTest(unittest.TestCase):
    def test_shown_in_the_players_language(self):
        self.assertEqual([(n.title, n.text) for n in parse([notice()])], [("Título", "Texto")])
        self.assertEqual(parse([notice()], language="en")[0].title, "Title")
        only_en = notice(title={"en": "Title"}, text={"en": "Text"})
        self.assertEqual(parse([only_en])[0].title, "Title")  # missing translation: English

    def test_shown_once(self):
        self.assertEqual(parse([notice()], seen={"n1"}), [])

    def test_version_range_and_end_date(self):
        self.assertEqual(len(parse([notice(min_version="1.0.4", max_version="1.0.9")])), 1)
        self.assertEqual(parse([notice(min_version="1.0.5")]), [])
        self.assertEqual(parse([notice(max_version="1.0.3")]), [])
        self.assertEqual(len(parse([notice(until="2026-11-05")])), 1)  # the last day still counts
        self.assertEqual(parse([notice(until="2026-11-04")]), [])

    def test_link_must_be_https(self):
        self.assertEqual(parse([notice(link="https://example.com")])[0].link, "https://example.com")
        self.assertEqual(parse([notice(link="file:///C:/x.exe")])[0].link, "")

    def test_broken_entries_are_skipped(self):
        items = [None, "x", {"id": "", "title": "a", "text": "b"}, notice(id="no-text", text={}),
                 notice(id="bad-date", until="soon"), notice(id="ok")]
        self.assertEqual([n.id for n in parse(items)], ["ok"])
        for data in (None, [], {"notices": "x"}, {}):
            self.assertEqual(notices.parse_notices(data, "1.0.4", "pt", set(), TODAY), [])

    def test_unreachable_file_is_ignored(self):
        def offline(url):
            raise OSError("no internet")
        self.assertIsNone(notices.fetch_notices(offline))
        self.assertIsNone(notices.fetch_notices(lambda url: b"<html>404</html>"))

    def test_published_file_is_valid(self):
        """docs/notices.json is what every installed app reads: it must stay valid JSON in this format."""
        data = json.loads((ROOT / "docs" / "notices.json").read_text(encoding="utf-8"))
        self.assertIsInstance(data["notices"], list)
        for item in data["notices"]:
            self.assertTrue(item["id"] and item["title"]["pt"] and item["title"]["en"], item)
            self.assertTrue(item["text"]["pt"] and item["text"]["en"], item)
        ids = [item["id"] for item in data["notices"]]
        self.assertEqual(len(ids), len(set(ids)), "two notices share an id")


if __name__ == "__main__":
    unittest.main()
