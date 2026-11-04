import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tracker import (ABANDONED, FINISHED, GREEN, PURPLE, RED, RUNNING, WAITING, RouteStats, Tracker,
                     fmt_clock, fmt_delta, parse_clock)

CAMPS = ["Red", "Krugs", "Raptors"]


def play(tracker, kills, start=85.0, end=None, gold=50.0):
    """Feeds 10 Hz samples with passive income; kills are (game time, gold) pairs."""
    kills = sorted(kills)
    end = end if end is not None else kills[-1][0] + 3.0
    t = start
    while t <= end + 1e-9:
        gold += 2.04 * 0.1
        while kills and kills[0][0] <= t + 1e-9:
            gold += kills.pop(0)[1]
        tracker.feed(round(t, 2), gold)
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

    def tracker(self):
        return Tracker(RouteStats(self.path, CAMPS), camp_spawn=90.0, target=130.0, quiet_window=2.0)

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

    def test_verdict(self):
        tr = self.tracker()
        play(tr, clear())  # PB 128 = sum of best, target 130
        tr = self.tracker()
        play(tr, clear(red=104.0), end=104.5)
        verdict, pace, best = tr.verdict(104.5)
        self.assertEqual(verdict, "reset")  # 104 + 15 + 13 = 132 > 130
        tr = self.tracker()
        play(tr, clear(red=100.5), end=101.0)
        self.assertEqual(tr.verdict(101.0)[0], "on_pace")

    def test_formatting(self):
        self.assertEqual(parse_clock("2:50.0"), 170.0)
        self.assertEqual(fmt_clock(169.84), "2:49.8")
        self.assertEqual(fmt_clock(59.96), "1:00.0")
        self.assertEqual(fmt_delta(-1.23), "-1.2")
        self.assertEqual(fmt_delta(0.3), "+0.3")


if __name__ == "__main__":
    unittest.main()
