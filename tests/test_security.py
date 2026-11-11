"""Data from outside the app is never trusted: links from the community sheet and GitHub, release files,
what answers on the game's local port, and the saved settings file."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import links
import notices
import paths
import updater
from links import GITHUB_HOSTS, VIDEO_HOSTS, open_url, safe_url
from overlay import DEFAULT_CHAMPION, App
from sheet import parse_sheet
from sources import Sample, champion_name, read_game
from updater import Update, release_url

RELEASES = "https://github.com/Thiscesarr/jungle-splits/releases"
# What must never reach the browser (Windows would run or open it): from the security review.
NOT_LINKS = [
    "http\\..\\..\\..\\Windows\\System32\\calc.exe", "http\\..\\marker.cmd", "https\\..\\x.exe", "http:\\x.exe",
    "C:\\Windows\\System32\\calc.exe", "file:///C:/Windows/System32/calc.exe", "\\\\server\\share\\x.exe",
    "calc.exe", "javascript:alert(1)", "ms-settings:display", "shell:startup", "ftp://example.com/x",
    "http://www.youtube.com/watch?v=abc",  # plain http
    "https://", "https:///x", "https://localhost/x", "https://user:pass@www.youtube.com/x",
    "https://www.youtube.com:port/x", "https://www.youtube.com/a b", "https://www.youtube.com/\nx",
    "https://www.youtube.com/" + "a" * 600, "", "   ", None, 7, ["https://www.youtube.com/x"],
]


class LinksTest(unittest.TestCase):
    def test_only_plain_https_links(self):
        for bad in NOT_LINKS:
            self.assertEqual(safe_url(bad), "", repr(bad))
        for good in ("https://www.youtube.com/watch?v=abc&t=10s", "https://youtu.be/abc", " https://x.com/a/status/1 ",
                     "https://github.com/Thiscesarr/jungle-splits/releases/tag/v1.0.4"):
            self.assertEqual(safe_url(good), good.strip())

    def test_video_sites_only(self):
        for good in ("https://www.youtube.com/watch?v=abc", "https://youtu.be/abc", "https://m.youtube.com/x",
                     "https://www.bilibili.com/video/BV1", "https://x.com/a/status/1", "https://clips.twitch.tv/x"):
            self.assertEqual(safe_url(good, VIDEO_HOSTS), good)
        for bad in ("https://evil.example/watch?v=abc", "https://youtube.com.evil.example/x",
                    "https://notyoutube.com/x", "https://evil.example/?https://www.youtube.com/",
                    "https://www.youtube.com.evil.example/x", "https://github.com/x"):
            self.assertEqual(safe_url(bad, VIDEO_HOSTS), "", bad)

    def test_nothing_unsafe_is_opened(self):
        with mock.patch.object(links.webbrowser, "open") as browser:
            for bad in NOT_LINKS:
                self.assertFalse(open_url(bad))
            self.assertFalse(open_url("https://evil.example/x", VIDEO_HOSTS))
            browser.assert_not_called()
            self.assertTrue(open_url("https://youtu.be/abc", VIDEO_HOSTS))
            browser.assert_called_once_with("https://youtu.be/abc")


def sheet_row(video: str) -> str:
    import csv
    import io
    out = io.StringIO()
    csv.writer(out).writerow(["Lee Sin", "26.19", "", "1", "2:44", "Red->Krugs->Raptors", video, "Veno", "AS/AD/HPS"])
    return out.getvalue()


class SheetLinksTest(unittest.TestCase):
    def video(self, cell: str) -> str:
        return parse_sheet(sheet_row(cell))["leesin"][0].video

    def test_sheet_cells_that_are_not_video_links_are_dropped(self):
        for bad in [b for b in NOT_LINKS if isinstance(b, str)] + ["https://evil.example/watch?v=abc"]:
            self.assertEqual(self.video(bad), "", repr(bad))  # the route is kept, without a video

    def test_sheet_video_links_are_kept(self):
        self.assertEqual(self.video("https://www.youtube.com/watch?v=abc"), "https://www.youtube.com/watch?v=abc")
        self.assertEqual(self.video(" https://youtu.be/abc "), "https://youtu.be/abc")

    def test_the_bundled_sheet_keeps_its_videos(self):
        text = paths.FALLBACK_SHEET.read_text(encoding="utf-8")
        routes = [r for champion in parse_sheet(text).values() for r in champion]
        with_video = [r for r in routes if r.video]
        self.assertGreater(len(with_video), len(routes) * 0.9)
        self.assertTrue(all(safe_url(r.video, VIDEO_HOSTS) for r in with_video))

    def test_notice_links(self):
        def link(value):
            data = {"notices": [{"id": "n", "title": {"en": "T"}, "text": {"en": "x"}, "link": value}]}
            from datetime import date
            return notices.parse_notices(data, "1.0.0", "en", set(), date(2026, 1, 1))[0].link
        self.assertEqual(link("https://example.com/news"), "https://example.com/news")
        for bad in NOT_LINKS:
            self.assertEqual(link(bad), "", repr(bad))


class UpdaterLinksTest(unittest.TestCase):
    def release(self, setup, sums=f"{RELEASES}/download/v9.9.9/SHA256SUMS.txt", page=f"{RELEASES}/tag/v9.9.9"):
        return json.dumps({"tag_name": "v9.9.9", "html_url": page, "assets": [
            {"name": "JungleSplits-Setup.exe", "browser_download_url": setup},
            {"name": "SHA256SUMS.txt", "browser_download_url": sums}, "not an asset"]}).encode()

    def test_only_this_projects_release_links(self):
        self.assertEqual(release_url(f"{RELEASES}/download/v1/JungleSplits-Setup.exe"),
                         f"{RELEASES}/download/v1/JungleSplits-Setup.exe")
        for bad in NOT_LINKS + ["https://github.com/someone-else/jungle-splits/releases/download/v1/x.exe",
                                "https://evil.example/Thiscesarr/jungle-splits/releases/download/v1/x.exe",
                                "https://github.com.evil.example/Thiscesarr/jungle-splits/releases/x",
                                "https://github.com/Thiscesarr/jungle-splits-evil/releases/x"]:
            self.assertEqual(release_url(bad), "", repr(bad))

    def test_release_with_files_elsewhere_is_not_offered(self):
        good = f"{RELEASES}/download/v9.9.9/JungleSplits-Setup.exe"
        self.assertIsNotNone(updater.check_latest("1.0.0", fetch=lambda url: self.release(good)))
        for bad in ("https://evil.example/JungleSplits-Setup.exe", "file:///C:/Users/Public/setup.exe",
                    "http://github.com/Thiscesarr/jungle-splits/releases/download/v9.9.9/JungleSplits-Setup.exe", None):
            self.assertIsNone(updater.check_latest("1.0.0", fetch=lambda url, bad=bad: self.release(bad)), bad)
            self.assertIsNone(updater.check_latest("1.0.0", fetch=lambda url, bad=bad: self.release(good, sums=bad)))

    def test_release_page_falls_back_to_the_project(self):
        good = f"{RELEASES}/download/v9.9.9/JungleSplits-Setup.exe"
        update = updater.check_latest("1.0.0", fetch=lambda url: self.release(good, page="https://evil.example/x"))
        self.assertEqual(update.page_url, f"{RELEASES}/latest")

    def test_download_refuses_other_links(self):
        fetched = []
        with tempfile.TemporaryDirectory() as tmp:
            for update in (Update("9.9.9", "file:///C:/x.exe", f"{RELEASES}/download/v9.9.9/SHA256SUMS.txt", ""),
                           Update("9.9.9", f"{RELEASES}/download/v9.9.9/JungleSplits-Setup.exe",
                                  "https://evil.example/SHA256SUMS.txt", "")):
                with self.assertRaises(ValueError):
                    updater.download(update, Path(tmp), fetch=lambda url, timeout=0: fetched.append(url) or b"")
            self.assertEqual(fetched, [])  # nothing was even requested
            self.assertEqual(list(Path(tmp).iterdir()), [])


def game(**changes) -> dict:
    data = {"gameData": {"gameMode": "PRACTICETOOL", "gameTime": 61.5},
            "activePlayer": {"currentGold": 512.0, "level": 2, "riotId": "Me#BR1"},
            "allPlayers": [{"riotId": "Me#BR1", "championName": "Lee Sin", "scores": {"creepScore": 4}, "items": []}]}
    for path, value in changes.items():
        target = data
        *parents, last = path.split("__")
        for key in parents:
            target = target[int(key)] if isinstance(target, list) else target[key]
        target[last] = value
    return data


class GameDataTest(unittest.TestCase):
    def test_champion_names(self):
        for name in ("Lee Sin", "Cho'Gath", "Nunu & Willump", "Dr. Mundo", "Jarvan IV", "Kai'Sa", "Wukong", " Vi "):
            self.assertEqual(champion_name(name), name.strip())
        for bad in (["x"], {"a": 1}, None, 7, 1.5, True, "", "   ", "x" * 41, "..\\..\\evil", "a/b", "a\nb", "<b>",
                    "Lee\x00Sin", "{champion}"):
            self.assertIsNone(champion_name(bad), repr(bad))

    def test_odd_champion_is_dropped_not_fatal(self):
        """The reported crash: "championName": ["x"] killed the overlay's loop and was saved to disk."""
        for bad in (["x"], {"a": 1}, 7, "x" * 500, "..\\evil"):
            kind, sample = read_game(game(allPlayers__0__championName=bad), 0.0)
            self.assertEqual(kind, "sample")
            self.assertIsNone(sample.champion)

    def test_numbers_must_be_real_numbers(self):
        for path in ("gameData__gameTime", "activePlayer__currentGold"):
            for bad in ("12", None, [1], {"x": 1}, True, float("nan"), float("inf"), -1, 1e12):
                with self.assertRaises((ValueError, TypeError, KeyError), msg=(path, bad)):
                    read_game(game(**{path: bad}), 0.0)

    def test_optional_values_are_dropped_when_odd(self):
        for bad in ("9", [9], -1, 99999, 2.5, True, None):
            sample = read_game(game(allPlayers__0__scores={"creepScore": bad}, activePlayer__level=bad), 0.0)[1]
            self.assertIsNone(sample.cs, repr(bad))
            self.assertIsNone(sample.level, repr(bad))
        sample = read_game(game(allPlayers__0__items="knife"), 0.0)[1]
        self.assertIsNone(sample.items)

    def test_malformed_answers_never_escape_as_other_errors(self):
        """Whatever answers on the port, the feed only sees the errors it treats as "no game"."""
        handled = (OSError, ValueError, KeyError, TypeError, AttributeError)
        for data in ([], "text", 5, None, {"gameData": {"gameMode": "PRACTICETOOL"}},
                     game(activePlayer=[1, 2]), game(allPlayers="x"), game(allPlayers=[1, 2]),
                     game(allPlayers__0__scores=[1]), game(activePlayer__fullRunes=[1]),
                     game(activePlayer__fullRunes={"statRunes": [1, 2]}),
                     game(activePlayer__fullRunes={"statRunes": [{"id": 5008}], "keystone": "x"})):
            try:
                read_game(data, 0.0)
            except handled:
                pass

    def test_rune_names_stay_short(self):
        runes = {"statRunes": [{"id": 5005}, {"id": 5008}, {"id": 5001}], "keystone": {"displayName": "x" * 500}}
        sample = read_game(game(activePlayer__fullRunes=runes), 0.0)[1]
        self.assertEqual((sample.runes.shards, sample.runes.keystone), ("AS/AD/HPS", ""))
        runes["keystone"] = {"displayName": ["Conqueror"]}
        self.assertEqual(read_game(game(activePlayer__fullRunes=runes), 0.0)[1].runes.keystone, "")


class NoSource:
    def start_feeding(self, events):
        pass


class AppHardeningTest(unittest.TestCase):
    def make(self, ui_state) -> App:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = Path(tmp.name)
        (data / "ui_state.json").write_text(ui_state if isinstance(ui_state, str) else json.dumps(ui_state),
                                            encoding="utf-8")
        config = json.loads(paths.CONFIG.read_text(encoding="utf-8"))
        config["auto_update_sheet"] = False
        app = App(config, data, NoSource(), paths.FALLBACK_SHEET, data / "custom_sounds")
        self.addCleanup(app.quit)
        app.sounds.enabled = False
        app.hotkeys.stop()
        return app

    def test_app_opens_with_a_damaged_settings_file(self):
        """After the reported crash the app no longer opened until ui_state.json was deleted."""
        for state in ({"welcomed": True, "champion": ["x"]}, {"welcomed": True, "champion": 7},
                      {"welcomed": True, "champion": "..\\..\\evil"}, [1, 2, 3], "not json at all", "null"):
            app = self.make(state)
            self.assertEqual(app.champion, DEFAULT_CHAMPION, state)
            app._tick()
            self.assertIsNotNone(app.last_image)

    def test_odd_champion_from_the_game_is_ignored_and_never_saved(self):
        app = self.make({"welcomed": True, "language": "en", "champion": "Vi"})
        for bad in (["x"], {"a": 1}, 7, "x" * 500):
            app.events.put(("sample", Sample(10.0, 500.0, 0, 1, 0, bad, None, time.perf_counter())))
            app._tick()
            self.assertEqual(app.champion, "Vi")
            app._set_champion(bad)
            self.assertEqual(app.champion, "Vi")
        self.assertEqual(json.loads(app.ui_state_path.read_text(encoding="utf-8")).get("champion", "Vi"), "Vi")
        app.events.put(("sample", Sample(11.0, 500.0, 0, 1, 0, "Lee Sin", None, time.perf_counter())))
        app._tick()
        self.assertEqual(app.champion, "Lee Sin")  # a real name still switches

    def test_the_loop_survives_a_failing_turn(self):
        app = self.make({"welcomed": True})
        app._tick_id = None
        with mock.patch.object(app, "_step", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                app._tick()
        self.assertIsNotNone(app._tick_id)  # the next turn is booked all the same
        app._tick()

    def test_only_safe_links_are_opened_from_the_overlay(self):
        app = self.make({"welcomed": True})
        from dataclasses import replace
        with mock.patch.object(links.webbrowser, "open") as browser:
            for bad in ("http\\..\\..\\Windows\\System32\\calc.exe", "https://evil.example/x", "file:///C:/x.exe"):
                app.route = replace(app.route, video=bad)  # as if an old cached sheet still had it
                app._open_video()
            browser.assert_not_called()
            app.route = replace(app.route, video="https://youtu.be/abc")
            app._open_video()
            browser.assert_called_once_with("https://youtu.be/abc")
        self.assertEqual(GITHUB_HOSTS, ("github.com",))


if __name__ == "__main__":
    unittest.main()
