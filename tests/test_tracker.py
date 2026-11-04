import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hotkeys import combo_from_vk, parse_combo
from sheet import norm, parse_sheet
from tracker import (ABANDONED, CS_BROKEN, CS_OK, FINISHED, GREEN, PURPLE, RED, RUNNING, WAITING, RouteStats,
                     Tracker, fmt_clock, fmt_delta, parse_clock)

ROOT = Path(__file__).resolve().parents[1]

CAMPS = ["Red", "Krugs", "Raptors"]


def play(tracker, kills, start=85.0, end=None, gold=50.0, cs=None):
    """Feeds 10 Hz samples with passive income; kills are (game time, gold[, cs]) tuples.
    cs=None leaves CS out of the samples, like a source without scoreboard data."""
    kills = sorted(kills)
    end = end if end is not None else kills[-1][0] + 3.0
    t = start
    while t <= end + 1e-9:
        gold += 2.04 * 0.1
        while kills and kills[0][0] <= t + 1e-9:
            kill = kills.pop(0)
            gold += kill[1]
            if cs is not None and len(kill) > 2:
                cs += kill[2]
        tracker.feed(round(t, 2), gold, cs)
        t += 0.1
    return gold


def clear(red=100.0, krugs=115.0, raptors=128.0):
    return [(red, 90), (krugs - 1.0, 60), (krugs - 0.5, 25), (krugs, 15), (raptors - 0.3, 50), (raptors, 35)]


class TrackerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "route.json"

    def tearDown(self):
        self.tmp.cleanup()

    def tracker(self, camps=CAMPS):
        return Tracker(RouteStats(self.path, camps), camp_spawn=90.0, target=130.0, quiet_window=2.0)

    def test_first_run_splits_on_last_kill_of_each_camp(self):
        tr = self.tracker()
        play(tr, clear())
        self.assertEqual(tr.state, FINISHED)
        self.assertEqual([round(s.time, 1) for s in tr.splits], [100.0, 115.0, 128.0])
        self.assertTrue(all(s.color == PURPLE for s in tr.splits))
        self.assertTrue(tr.new_pb)
        self.assertEqual(tr.stats.attempts, 1)
        self.assertEqual(tr.stats.completed, 1)

    def test_second_run_colors_and_learned_gold(self):
        tr = self.tracker()
        play(tr, clear())
        tr = self.tracker()  # reload from disk
        self.assertAlmostEqual(tr.stats.expected_gold(1), 100, delta=1)
        play(tr, clear(red=99.0, krugs=115.5, raptors=127.5))
        colors = [s.color for s in tr.splits]
        # Red: faster (purple). Krugs segment 16.5 vs 15 (red). Raptors 12.0 vs 13.0 (purple).
        self.assertEqual(colors, [PURPLE, RED, PURPLE])
        self.assertAlmostEqual(tr.splits[0].total_delta, -1.0, places=1)
        self.assertAlmostEqual(tr.splits[1].segment_delta, 1.5, places=1)
        self.assertTrue(tr.new_pb)

    def test_green_when_beating_pb_but_not_best_segment(self):
        tr = self.tracker()
        play(tr, clear(red=100.0, krugs=115.0, raptors=128.0))
        tr = self.tracker()
        play(tr, clear(red=101.0, krugs=114.0, raptors=130.0))  # krugs segment 13 -> new best, no PB
        tr = self.tracker()
        play(tr, clear(red=102.0, krugs=116.5, raptors=130.0))  # krugs 14.5: PB seg 15, best 13
        self.assertEqual(tr.splits[1].color, GREEN)

    def test_learned_gold_splits_immediately(self):
        tr = self.tracker()
        play(tr, clear())
        tr = self.tracker()
        play(tr, clear(), end=115.05)
        self.assertEqual(len(tr.splits), 2)
        self.assertAlmostEqual(tr.splits[1].time, 115.0, places=1)

    def test_pause_inside_camp_before_half_gold_does_not_split(self):
        tr = self.tracker()
        play(tr, [(105.0, 20), (108.0, 70)], end=112.0)
        self.assertEqual(len(tr.splits), 1)
        self.assertAlmostEqual(tr.splits[0].time, 108.0, places=1)

    def test_practice_tool_gold_and_purchases_are_ignored(self):
        tr = self.tracker()
        play(tr, [(95.0, 1000), (97.0, -300)], end=104.0)
        self.assertEqual(tr.splits, [])
        self.assertEqual(tr.state, RUNNING)

    def test_clock_going_back_starts_new_run(self):
        tr = self.tracker()
        play(tr, clear()[:1], end=104.0)
        self.assertEqual(len(tr.splits), 1)
        tr.feed(20.0, 500.0)
        self.assertEqual(tr.state, WAITING)
        self.assertEqual(tr.splits, [])

    def test_joining_after_spawn_waits_for_reset(self):
        tr = self.tracker()
        tr.feed(120.0, 300.0)
        self.assertEqual(tr.state, ABANDONED)

    def test_undo_restores_best_segment_and_gold(self):
        tr = self.tracker()
        play(tr, [(100.0, 90)], end=103.0)
        tr.undo()
        self.assertEqual(tr.splits, [])
        self.assertIsNone(tr.stats.best_segments[0])
        self.assertAlmostEqual(tr.seg_gold, 90, delta=0.5)

    def test_verdict_compares_with_pb_not_target(self):
        tr = self.tracker()
        play(tr, clear(), start=85.0)  # PB 128 = sum of best
        tr = self.tracker()
        tr.target = 120.0  # out of reach: must not say reset by itself
        play(tr, clear(), end=95.0)
        self.assertEqual(tr.verdict(95.0)[0], "ahead")
        tr = self.tracker()
        tr.target = 120.0
        play(tr, clear(red=101.5), end=102.0)
        self.assertEqual(tr.verdict(102.0)[0], "behind")  # +1.5, within the 2 s margin
        tr = self.tracker()
        play(tr, clear(red=104.0), end=104.5)
        verdict, pace, best = tr.verdict(104.5)
        self.assertEqual(verdict, "reset")  # 104 + 15 + 13 = 132 > 128 + 2
        tr = self.tracker()
        tr.target = 131.0
        play(tr, clear(red=100.5), end=101.0)
        self.assertEqual(tr.verdict(101.0)[0], "on_target")

    def test_current_delta(self):
        tr = self.tracker()
        play(tr, clear())
        tr = self.tracker()
        play(tr, clear(red=99.0, krugs=117.0), end=110.0)
        self.assertAlmostEqual(tr.current_delta(110.0), -1.0, places=1)  # ahead after Red
        self.assertAlmostEqual(tr.current_delta(116.0), 1.0, places=1)  # Krugs PB split was 115.0

    def test_cs_closes_camp_on_fourth_cs_despite_long_pause(self):
        tr = self.tracker()
        play(tr, [(100.0, 90, 4), (105.0, 40, 2), (109.0, 30, 1), (110.0, 30, 1)], end=112.0, cs=0)
        self.assertEqual(tr.cs_state, CS_OK)
        self.assertEqual([round(s.time, 1) for s in tr.splits], [100.0, 110.0])

    def test_cs_reported_in_batches_falls_back_to_gold(self):
        tr = self.tracker()
        play(tr, [(100.0, 90, 0), (115.0, 100, 10)], end=118.0, cs=0)
        self.assertEqual(tr.cs_state, CS_BROKEN)
        self.assertEqual([round(s.time, 1) for s in tr.splits], [100.0, 115.0])

    def test_recall_closes_on_purchase(self):
        tr = self.tracker(["Red", "Recall", "Gromp"])
        play(tr, [(100.0, 90, 4), (110.0, -300, 0), (124.0, 80, 4)], cs=0)
        self.assertEqual(tr.state, FINISHED)
        self.assertEqual([round(s.time, 1) for s in tr.splits], [100.0, 110.0, 124.0])

    def test_recall_without_purchase_is_closed_by_next_camp(self):
        tr = self.tracker(["Red", "Recall", "Gromp"])
        play(tr, [(100.0, 90, 4), (124.0, 80, 4)], cs=0)
        self.assertEqual(tr.state, FINISHED)
        self.assertEqual([round(s.time, 1) for s in tr.splits], [100.0, 124.0, 124.0])

    def test_sheet_routes(self):
        routes = parse_sheet((ROOT / "clears_fallback.csv").read_text(encoding="utf-8"))
        lee = {r.path: r for r in routes[norm("Lee Sin")]}
        recall = lee["Raptors->Red->Krugs->Recall->Wolves->Gromp->Blue"]
        self.assertEqual(recall.record, 164.0)
        self.assertEqual(recall.player, "Veno")
        self.assertIn(norm("Nunu & Willump"), routes)

    def test_hotkey_parsing(self):
        self.assertEqual(parse_combo("ctrl+shift+S"), (0x6, ord("S")))
        self.assertEqual(parse_combo("VK226"), (0, 226))
        # Symbol keys round-trip through the active keyboard layout (US, ABNT2, ...).
        for symbol in ";-.,":
            vk = parse_combo(symbol)[1]
            self.assertEqual(parse_combo(combo_from_vk(vk)), (0, vk))

    def test_formatting(self):
        self.assertEqual(parse_clock("2:50.0"), 170.0)
        self.assertEqual(fmt_clock(169.84), "2:49.8")
        self.assertEqual(fmt_clock(59.96), "1:00.0")
        self.assertEqual(fmt_delta(-1.23), "-1.2")
        self.assertEqual(fmt_delta(0.3), "+0.3")


if __name__ == "__main__":
    unittest.main()
