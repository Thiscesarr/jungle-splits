"""Camps that pay their gold monster by monster, with pauses, must not close early (reddit bug report:
a Jax clear timed 11 s faster than the world record because every split shifted by one camp)."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detect import CampGold, StepDetector, best_route
from runlog import KEEP_FILES, RunLog
from sheet import norm, parse_sheet
from test_tracker import play
from tracker import CS_BROKEN, FINISHED, RouteStats, Tracker

ROOT = Path(__file__).resolve().parents[1]
JAX_ROUTE = ["Blue", "Gromp", "Wolves", "Raptors", "Red", "Krugs"]
# Small monsters first, the big one seconds later, as a Jax clears them.
JAX_KILLS = [(70.0, 90), (84.0, 80),
             (96.0, 15), (96.4, 15), (99.4, 55),
             (110.0, 8), (110.3, 8), (110.6, 8), (110.9, 8), (111.2, 8), (113.6, 35),
             (128.0, 90),
             (140.0, 10), (141.0, 15), (143.0, 14), (145.5, 28), (149.0, 42)]
CAMP_DEATHS = [70.0, 84.0, 99.4, 113.6, 128.0, 149.0]
# GitHub issue #1, a Master Yi clear of the same route: the wolves paid less than the usual 105 gold
# (lesser wolves paying 15, or one left behind to despawn once the big wolf died) and never closed.
YI_WOLVES = {"85 gold": [(95.0, 15), (95.1, 55), (95.9, 15)], "70 gold": [(95.0, 55), (95.9, 15)],
             "70 gold in one hit": [(95.9, 70)]}
YI_REST = [(70.0, 90), (84.0, 80),
           (104.0, 35), (104.1, 40), (110.0, 90), (122.0, 30), (122.5, 79)]
YI_DEATHS = [70.0, 84.0, 95.9, 104.1, 110.0, 122.5]


class SplitSafetyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "route.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_staggered_camps_close_on_their_last_monster(self):
        tracker = Tracker(RouteStats(self.path, JAX_ROUTE), camp_spawn=55.0, target=170.0)
        play(tracker, JAX_KILLS, start=50.0, end=155.0)
        self.assertEqual(tracker.state, FINISHED)
        self.assertEqual([round(s.time, 1) for s in tracker.splits], CAMP_DEATHS)

    def test_polluted_gold_samples_are_ignored(self):
        stats = RouteStats(self.path, JAX_ROUTE)
        stats.gold_samples[2] = [104.4, 105.4]  # wolves + the 20 gold bonus, learned by older versions
        self.assertIsNone(stats.expected_gold(2))
        self.assertEqual(stats.reference_gold(2), 85)
        stats.gold_samples[2] = [84.6, 104.4, 85.6]
        self.assertEqual(stats.expected_gold(2), 85.1)

    def test_split_run_does_not_teach_wrong_gold(self):
        tracker = Tracker(RouteStats(self.path, JAX_ROUTE), camp_spawn=55.0, target=170.0)
        play(tracker, JAX_KILLS, start=50.0, end=155.0)
        tracker.stats.gold_samples[2].append(50.0)
        self.assertAlmostEqual(tracker.stats.expected_gold(2), 85, delta=1)

    def test_shop_refunds_are_not_monster_gold(self):
        tracker = Tracker(RouteStats(self.path, ["Red", "Recall", "Gromp"]), camp_spawn=55.0)
        play(tracker, [(70.0, 90), (80.0, -350), (81.0, 350), (95.0, 80)], start=50.0, end=100.0)
        self.assertEqual([round(s.time, 1) for s in tracker.splits], [70.0, 80.0, 95.0])


    def test_wolves_paying_less_than_usual_still_close(self):
        for name, wolves in YI_WOLVES.items():
            with self.subTest(name):
                tracker = Tracker(RouteStats(Path(self.tmp.name) / f"{name}.json", JAX_ROUTE), camp_spawn=55.0)
                play(tracker, sorted(YI_REST + wolves), start=50.0, end=130.0)
                self.assertEqual(tracker.state, FINISHED)
                self.assertEqual([round(s.time, 1) for s in tracker.splits], YI_DEATHS)


    def test_real_master_yi_clear(self):
        """The debug log of a real clear for issue #1 (app 1.0.2): the two lesser wolves paid 15 each and
        died 5.5 s before the big one; the wolves (86.6 gold) never closed and swallowed the raptors."""
        rows = [r for r in csv.reader((ROOT / "tests" / "fixtures" / "master-yi-light-wolves.csv").open(encoding="utf-8"))
                if r and not r[0].startswith("#")][1:]
        tracker = Tracker(RouteStats(self.path, JAX_ROUTE), camp_spawn=55.0)
        for row in rows:
            tracker.feed(float(row[1]), float(row[2]), int(row[3]) if row[3] else None)
        self.assertEqual(tracker.state, FINISHED)
        # Each split within one sample of the camp's last kill in the log (Red pays 20 more gold 0.5 s later).
        for split, death in zip(tracker.splits, [73.30, 91.16, 115.44, 135.72, 162.02, 172.46]):
            self.assertAlmostEqual(split.time, death, delta=0.6)
        self.assertAlmostEqual(tracker.splits[2].gold, 86.6, delta=1)


class DetectorSafetyTest(unittest.TestCase):
    def test_detector_sees_six_whole_camps(self):
        detector = StepDetector(55.0, 2.0, 4)
        tracker = Tracker(RouteStats(Path(tempfile.mkdtemp()) / "r.json", JAX_ROUTE), camp_spawn=55.0)
        steps = []

        class Feed:
            def feed(self, t, gold, cs):
                tracker.feed(t, gold, cs)
                step = detector.feed(t, gold, cs, CS_BROKEN)
                if step:
                    steps.append(step)

        play(Feed(), JAX_KILLS, start=50.0, end=155.0)
        self.assertEqual([round(s.time, 1) for s in steps], CAMP_DEATHS)

    def test_jax_route_is_recognized(self):
        routes = parse_sheet((ROOT / "clears_fallback.csv").read_text(encoding="utf-8"))[norm("Jax")]
        other = next(r for r in routes if r.camps[0] == "Red")
        detector = StepDetector(55.0, 2.0, 4)
        current = other
        with tempfile.TemporaryDirectory() as tmp:
            camp_gold = CampGold(Path(tmp) / "camp_gold.json")

            class Feed:
                def feed(self, t, gold, cs):
                    nonlocal current
                    if detector.feed(t, gold, cs, CS_BROKEN):
                        current = best_route(detector.steps, routes, current, camp_gold) or current

            play(Feed(), JAX_KILLS, start=50.0, end=155.0)
        self.assertEqual(list(current.camps), JAX_ROUTE)

    def test_master_yi_route_is_recognized_with_light_wolves(self):
        routes = parse_sheet((ROOT / "clears_fallback.csv").read_text(encoding="utf-8"))[norm("Master Yi")]
        for name, wolves in YI_WOLVES.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                camp_gold = CampGold(Path(tmp) / "camp_gold.json")
                detector, current = StepDetector(55.0, 2.0, 4), routes[-1]

                class Feed:
                    def feed(self, t, gold, cs):
                        nonlocal current
                        if detector.feed(t, gold, cs, CS_BROKEN):
                            current = best_route(detector.steps, routes, current, camp_gold) or current

                play(Feed(), sorted(YI_REST + wolves), start=50.0, end=130.0)
                self.assertEqual([round(s.time, 1) for s in detector.steps], YI_DEATHS)
                self.assertEqual(current.path, "Blue->Gromp->Wolves->Raptors->Red->Krugs")


class RunLogTest(unittest.TestCase):
    def test_log_file_and_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for n in range(KEEP_FILES + 3):
                (folder / f"2026010{n:03d}-old.csv").write_text("x")
            log = RunLog(folder)
            log.add(60.0, 60.0, 520.5, 0, 1, 1)
            log.add(60.1, 60.1, 610.5, None, 1, 1)
            path = log.save({"champion": "Lee Sin", "route": "Red->Gromp"}, [("Red", 60.1, 90.0, False)])
            text = path.read_text(encoding="utf-8")
            self.assertIn("# route: Red->Gromp", text)
            self.assertIn("# split: Red at 60.10 with 90.0 gold", text)
            self.assertIn("60.10,60.10,610.50,,1,1", text)
            self.assertEqual(len(list(folder.glob("*.csv"))), KEEP_FILES)
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
