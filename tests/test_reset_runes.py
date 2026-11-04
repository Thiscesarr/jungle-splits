import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sheet import norm, parse_sheet
from sources import parse_runes
from tracker import RUNNING, WAITING, RouteStats, RunClock, Tracker

ROOT = Path(__file__).resolve().parents[1]


class RunClockTest(unittest.TestCase):
    def test_level_drop_restarts_the_clock(self):
        clock = RunClock()
        self.assertEqual(clock.run_time(180.0, 300.0, level=4, items=2), 180.0)
        self.assertEqual(clock.run_time(180.1, 500.0, level=1, items=0), 0.0)
        self.assertAlmostEqual(clock.run_time(240.0, 500.0, level=1, items=1), 59.9)

    def test_reset_at_level_one_is_caught_by_inventory_and_gold(self):
        clock = RunClock()
        clock.run_time(70.0, 120.0, level=1, items=1)
        self.assertEqual(clock.run_time(70.1, 500.0, level=1, items=0), 0.0)
        clock = RunClock()
        clock.run_time(70.0, 120.0)
        self.assertEqual(clock.run_time(70.1, 500.0), 0.0)

    def test_practice_tool_gold_and_purchases_do_not_restart(self):
        clock = RunClock()
        clock.run_time(70.0, 120.0, level=2, items=1)
        self.assertAlmostEqual(clock.run_time(70.1, 1120.0, level=2, items=1), 70.1)  # +1000 gold button
        self.assertAlmostEqual(clock.run_time(70.2, 420.0, level=2, items=2), 70.2)  # bought an item

    def test_new_game_uses_the_real_clock_again(self):
        clock = RunClock()
        clock.run_time(180.0, 300.0, level=4, items=2)
        clock.run_time(180.1, 500.0, level=1, items=0)
        self.assertEqual(clock.run_time(5.0, 500.0, level=1, items=0), 5.0)

    def test_manual_restart(self):
        clock = RunClock()
        clock.run_time(200.0, 300.0)
        clock.restart()
        self.assertAlmostEqual(clock.run_time(200.1, 300.0), 0.1)

    def test_tracker_starts_a_new_run_after_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = Tracker(RouteStats(Path(tmp) / "r.json", ["Red", "Gromp"]), camp_spawn=55.0)
            clock = RunClock()
            for t, gold, level in [(50.0, 50, 1), (60.0, 60, 1), (150.0, 300, 3), (150.1, 500, 1), (206.0, 500, 1)]:
                tracker.feed(clock.run_time(t, gold, level), gold)
                if t == 150.1:
                    self.assertEqual(tracker.state, WAITING)
            self.assertEqual(tracker.state, RUNNING)
            self.assertEqual(tracker.stats.attempts, 2)


class SoundsTest(unittest.TestCase):
    def test_tones_are_written_as_wav(self):
        import wave
        from sound import SOUND_NAMES, THEMES, Sounds
        for theme in THEMES:
            self.assertEqual(set(THEMES[theme]), set(SOUND_NAMES))
        with tempfile.TemporaryDirectory() as tmp:
            sounds = Sounds(Path(tmp) / "gen", volume=0.3, enabled=False, custom_folder=Path(tmp) / "sons")
            sounds.play("pb")  # disabled: must not play
            for name in SOUND_NAMES:
                with wave.open(str(sounds.path(name))) as wav:
                    self.assertGreater(wav.getnframes(), 1000)
            (Path(tmp) / "sons").mkdir()
            (Path(tmp) / "sons" / "red.wav").write_bytes(b"")
            self.assertEqual(sounds.path("red"), Path(tmp) / "sons" / "red.wav")  # user's file wins


class HotkeyNamesTest(unittest.TestCase):
    def test_symbol_keys_by_position(self):
        from hotkeys import parse_combo, pretty_combo
        self.assertEqual(parse_combo("ctrl+shift+OEM1"), (0x6, 0xBA))
        self.assertEqual(parse_combo("ctrl+shift+PERIOD"), (0x6, 0xBE))
        self.assertTrue(pretty_combo("ctrl+shift+COMMA").startswith("Ctrl+Shift+"))
        self.assertEqual(pretty_combo(""), "")


class RunesTest(unittest.TestCase):
    def test_stat_shards(self):
        active = {
            "championStats": {"abilityPower": 0.0},
            "fullRunes": {
                "keystone": {"displayName": "Conqueror", "id": 8010},
                "statRunes": [{"id": 5005, "rawDescription": "perk_tooltip_StatModAttackSpeed"},
                              {"id": 5008, "rawDescription": "perk_tooltip_StatModAdaptive"},
                              {"id": 5001, "rawDescription": "perk_tooltip_StatModHealthScaling"}],
            },
        }
        runes = parse_runes(active)
        self.assertEqual(runes.shards, "AS/AD/HPS")
        self.assertEqual(runes.keystone, "Conqueror")
        active["championStats"]["abilityPower"] = 9.0
        self.assertEqual(parse_runes(active).shards, "AS/AP/HPS")

    def test_unknown_id_falls_back_to_description(self):
        active = {"fullRunes": {"statRunes": [{"id": 9999, "rawDescription": "perk_tooltip_StatModHealthFlat"}]}}
        self.assertEqual(parse_runes(active).shards, "HPF")

    def test_sheet_shards(self):
        routes = parse_sheet((ROOT / "clears_fallback.csv").read_text(encoding="utf-8"))
        lee = {r.path: r for r in routes[norm("Lee Sin")]}
        self.assertEqual(lee["Blue->Gromp->Wolves->Raptors->Krugs->Red"].shards, "AS/AD/HPS")


if __name__ == "__main__":
    unittest.main()
