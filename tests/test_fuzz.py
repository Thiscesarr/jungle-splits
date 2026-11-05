"""Stress tests: hundreds of random clears over every route in the sheet. Each split must land on the
moment the camp's last monster died, whatever order the monsters died in and however long the pauses
inside a camp were, and route detection must end on the route that was actually cleared."""
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from detect import CampGold, StepDetector, best_route
from sheet import parse_sheet
from sim import samples, simulate_clear
from tracker import CS_BROKEN, CS_UNKNOWN, FINISHED, MULTI_MONSTER_CAMPS, RouteStats, RunClock, Tracker, camp_key

ROOT = Path(__file__).resolve().parents[1]
ROUTES = parse_sheet((ROOT / "src" / "clears_fallback.csv").read_text(encoding="utf-8"))
ALL_PATHS = sorted({r.camps for champion in ROUTES.values() for r in champion})
SAMPLE_PERIOD = 0.13  # a split is seen on the first sample after the kill


def signature(camps) -> list[tuple]:
    """What route detection can see of a route: Red and Blue look the same (one monster, 90 gold)."""
    from tracker import DEFAULT_CAMP_GOLD
    return [("recall",) if camp_key(c) == "recall" else (camp_key(c) in MULTI_MONSTER_CAMPS,
                                                          DEFAULT_CAMP_GOLD[camp_key(c)]) for c in camps]


class TrackerFuzzTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, seed: int, max_gap: float, cs_mode: str, runs: int = 1, walk=(5.0, 10.0)) -> None:
        rng = random.Random(seed)
        camps = list(rng.choice(ALL_PATHS))
        tracker = Tracker(RouteStats(Path(self.tmp.name) / f"{seed}.json", camps), camp_spawn=55.0,
                          cs_state=CS_UNKNOWN)
        for run in range(runs):  # later runs use the camp gold learned from earlier ones
            clear = simulate_clear(camps, rng, max_gap=max_gap, walk=walk)
            bonuses = sum(1 for _, g in clear.events if g == 20)
            self.two_bonus_clears = getattr(self, "two_bonus_clears", 0) + (bonuses >= 2)
            for t, gold, cs in samples(clear, rng, cs_mode=cs_mode, start=45.0 if run == 0 else 0.5):
                tracker.feed(t, gold, cs)
            context = f"seed {seed} run {run} {camps} deaths {clear.deaths}"
            self.assertEqual(tracker.state, FINISHED, context)
            for camp, split, death in zip(camps, tracker.splits, clear.deaths):
                self.assertGreaterEqual(split.time, death - 1e-6, f"{camp} closed early: {context}")
                self.assertLess(split.time - death, SAMPLE_PERIOD, f"{camp} closed late: {context}")

    def test_random_clears_with_realistic_pauses(self):
        for seed in range(300):
            self.check(seed, max_gap=2.5, cs_mode="batched")

    def test_long_pauses_inside_camps(self):
        # Pauses longer than the quiet window used to close camps early (the reddit Jax bug).
        for seed in range(300, 450):
            self.check(seed, max_gap=4.8, cs_mode="none")

    def test_slow_clears_get_a_pet_bonus_every_minute(self):
        """Clears slower than about 3:31 get a second pet bonus treat."""
        for seed in range(500, 560):
            self.check(seed, max_gap=3.0, cs_mode="batched", walk=(20.0, 30.0))
        self.assertGreater(self.two_bonus_clears, 20)  # the case is really covered

    def test_repeated_runs_learn_camp_gold_safely(self):
        for seed in range(450, 490):
            self.check(seed, max_gap=3.0, cs_mode="batched", runs=4)


class DetectionFuzzTest(unittest.TestCase):
    def test_every_sheet_route_is_recognized(self):
        """Starting from another route of the same champion, detection must end on a route that
        looks the same as the one cleared (Red and Blue swapped are indistinguishable by design)."""
        rng = random.Random(7)
        with tempfile.TemporaryDirectory() as tmp:
            camp_gold = CampGold(Path(tmp) / "camp_gold.json")
            for champion, routes in sorted(ROUTES.items()):
                for truth in routes:
                    start = rng.choice(routes)
                    clear = simulate_clear(list(truth.camps), rng, max_gap=2.5)
                    detector, current = StepDetector(55.0, 2.0, 4), start
                    for t, gold, cs in samples(clear, rng, cs_mode="batched"):
                        if detector.feed(t, gold, cs, CS_BROKEN):
                            current = best_route(detector.steps, routes, current, camp_gold) or current
                    self.assertEqual(len(detector.steps), len(truth.camps), f"{champion} {truth.path}")
                    # A short clear (3 camps) is the start of some full clears: while the run goes on,
                    # nothing tells them apart, so detection may stay on the longer route.
                    detected = signature(current.camps)[: len(truth.camps)]
                    self.assertEqual(detected, signature(truth.camps),
                                     f"{champion}: cleared {truth.path}, detected {current.path}")


class ResetFuzzTest(unittest.TestCase):
    def test_practice_tool_resets_start_fresh_attempts(self):
        """Random Reset Games (clock keeps running) between and in the middle of clears."""
        rng = random.Random(3)
        with tempfile.TemporaryDirectory() as tmp:
            for trial in range(40):
                camps = list(rng.choice(ALL_PATHS))
                tracker = Tracker(RouteStats(Path(tmp) / f"{trial}.json", camps), camp_spawn=55.0)
                clock, game_time, started = RunClock(), 0.0, 0
                for attempt in range(rng.randint(2, 5)):
                    clear = simulate_clear(camps, rng)
                    feed = samples(clear, rng, start=1.0)
                    abort = attempt % 2 == 1 and rng.random() < 0.6
                    if abort:  # reset somewhere mid-clear
                        feed = feed[: rng.randint(len(feed) // 3, len(feed) - 20)]
                    for t, gold, cs in feed:
                        level = 1 + sum(1 for d in clear.deaths if d <= t) // 2
                        tracker.feed(clock.run_time(game_time + t, gold, level, 1), gold, cs)
                    started += any(t >= 55.0 for t, _, _ in feed)
                    game_time += feed[-1][0] + 0.1
                    tracker.feed(clock.run_time(game_time, 500.0, 1, 0), 500.0, 0)  # Reset Game
                    game_time += 0.1
                    if not abort:
                        self.assertEqual(len(tracker.splits), 0)  # the reset cleared the finished run
                self.assertEqual(tracker.stats.attempts, started, f"trial {trial}")
                self.assertGreaterEqual(tracker.stats.completed, 1)


if __name__ == "__main__":
    unittest.main()
