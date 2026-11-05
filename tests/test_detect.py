import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from detect import CampGold, Step, StepDetector, best_route
from sheet import Route, norm, parse_path, parse_sheet
from sources import DemoSource
from tracker import CS_BROKEN, CS_OK, PASSIVE_GOLD_PER_SEC, RouteStats, Tracker

ROOT = Path(__file__).resolve().parents[1]
SPAWN = 55.0
PREFERRED = "Raptors->Red->Krugs->Recall->Wolves->Gromp->Blue"


def samples_for(camps, seed):
    """10 Hz (time, gold, cs) samples of a simulated clear of the given camps."""
    demo = DemoSource(None, "Lee Sin", SPAWN, seed=seed)
    events = demo.plan(list(camps))
    end = events[-1][0] + 3.0
    t, gold, cs, out = SPAWN - 5.0, 500.0, 0, []
    while t <= end:
        gold += PASSIVE_GOLD_PER_SEC * 0.1
        while events and events[0][0] <= t:
            _, gold_gain, cs_gain = events.pop(0)
            gold += gold_gain
            cs += cs_gain
        out.append((round(t, 2), gold, cs))
        t += 0.1
    return out


class DetectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.camp_gold = CampGold(Path(self.tmp.name) / "camp_gold.json")
        routes = parse_sheet((ROOT / "src" / "clears_fallback.csv").read_text(encoding="utf-8"))
        self.lee = routes[norm("Lee Sin")]

    def tearDown(self):
        self.tmp.cleanup()

    def detect(self, samples, cs_state):
        """Mimics the overlay: starts on the preferred route and follows the detector's switches.
        Returns the final route and the step count at which it was last switched."""
        current = next(r for r in self.lee if r.path == PREFERRED)
        detector = StepDetector(SPAWN, 2.0, 4)
        switched_at = 0
        for t, gold, cs in samples:
            if detector.feed(t, gold, cs if cs_state != CS_BROKEN else None, cs_state):
                route = best_route(detector.steps, self.lee, current, self.camp_gold)
                if route is not None:
                    current, switched_at = route, len(detector.steps)
        return current, switched_at

    def test_every_lee_route_is_recognized(self):
        for cs_state in (CS_OK, CS_BROKEN):
            for route in self.lee:
                for seed in range(3):
                    with self.subTest(route=route.path, cs=cs_state, seed=seed):
                        found, switched_at = self.detect(samples_for(route.camps, seed), cs_state)
                        self.assertEqual(found.path, route.path)

    def test_blue_and_red_start_split_by_second_camp(self):
        routes = [Route("X", parse_path("Red->Krugs->Raptors->Wolves->Gromp->Blue")),
                  Route("X", parse_path("Blue->Gromp->Wolves->Raptors->Red->Krugs")),
                  Route("X", parse_path("Raptors->Red->Krugs->Wolves->Gromp->Blue"))]
        red, blue, raptors = routes
        single, multi = Step("camp", 70, 90, 1), Step("camp", 85, 100, 3)
        # Raptor start chosen, but the first camp died in one hit: move to a single-monster start.
        self.assertIn(best_route([single], routes, raptors, self.camp_gold), (red, blue))
        # Second camp settles it.
        self.assertEqual(best_route([single, Step("camp", 85, 80, 1)], routes, red, self.camp_gold), blue)
        self.assertEqual(best_route([single, multi], routes, blue, self.camp_gold), red)

    def test_purchase_becomes_recall_step(self):
        detector = StepDetector(SPAWN, 2.0, 4)
        steps = []
        for t, gold, cs in [(54.0, 500, 0), (60.0, 500, 0), (60.1, 590, 4), (70.0, 590, 4), (70.1, 240, 4)]:
            step = detector.feed(t, gold, cs, CS_OK)
            if step:
                steps.append(step.kind)
        self.assertEqual(steps, ["camp", "recall"])

    def test_learned_camp_gold(self):
        self.camp_gold.learn(["Red", "Recall", "Gromp"], [95.0, 0.0, 72.0])
        reloaded = CampGold(self.camp_gold.path)
        self.assertEqual(reloaded.expected("Gromp"), (72.0, True))
        self.assertEqual(reloaded.expected("Blue")[1], False)


class DiscardRunTest(unittest.TestCase):
    def test_discard_restores_stats_from_before_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "route.json"
            camps = ["Red", "Gromp"]
            tracker = Tracker(RouteStats(path, camps), camp_spawn=SPAWN)
            for t, gold, cs in samples_for(camps, seed=1):
                tracker.feed(t, gold, cs)
            self.assertIsNotNone(tracker.stats.pb)
            tracker.discard_run()
            reloaded = RouteStats(path, camps)
            self.assertIsNone(reloaded.pb)
            self.assertEqual(reloaded.attempts, 0)
            self.assertEqual(reloaded.best_segments, [None, None])


if __name__ == "__main__":
    unittest.main()
