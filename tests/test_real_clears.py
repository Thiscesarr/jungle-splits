"""Debug logs of real Practice Tool clears, replayed the way the overlay runs them (route detection
switching routes, the tracker replaying the run). Each camp must close on exactly its own gold, which
means every split landed on the camp's last kill: no camp swallowed part of another, nor the 20 gold
bonus that comes once per clear."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from detect import CampGold, StepDetector, best_route
from sheet import parse_sheet, routes_for_champion
from tracker import CS_UNKNOWN, DEFAULT_CAMP_GOLD, FINISHED, RouteStats, Tracker, camp_key

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
ROUTES = parse_sheet((ROOT / "src" / "clears_fallback.csv").read_text(encoding="utf-8"))
# log -> (champion, route selected when the clear started, route actually cleared)
CLEARS = {
    "master-yi-light-wolves.csv": ("Master Yi", "Blue->Gromp->Wolves->Raptors->Red->Krugs",
                                   "Blue->Gromp->Wolves->Raptors->Red->Krugs"),
    "lee-bonus-in-wolves.csv": ("Lee Sin", "Raptors->Red->Krugs->Recall->Wolves->Gromp->Blue",
                                "Raptors->Red->Krugs->Recall->Wolves->Gromp->Blue"),
    "lee-bonus-in-raptors.csv": ("Lee Sin", "Blue->Gromp->Wolves->Raptors->Red->Krugs",
                                 "Blue->Gromp->Wolves->Raptors->Red->Krugs"),
    "lee-bonus-mid-krugs.csv": ("Lee Sin", "Blue->Gromp->Wolves->Raptors->Krugs->Red",
                                "Blue->Gromp->Wolves->Raptors->Krugs->Red"),
    # Started at level 4 with the Krugs-first route selected, cleared Red first.
    "lee-level4-red-before-krugs.csv": ("Lee Sin", "Blue->Gromp->Wolves->Raptors->Krugs->Red",
                                        "Blue->Gromp->Wolves->Raptors->Red->Krugs"),
}


def replay(path: Path, champion: str, start_route: str, tmp: Path):
    rows = [r for r in csv.reader(path.open(encoding="utf-8")) if r and not r[0].startswith("#")][1:]
    routes = routes_for_champion(ROUTES, champion, 1)
    route = next(r for r in routes if r.path == start_route)
    camp_gold, run, detector = CampGold(tmp / "camp_gold.json"), [], StepDetector(55.0, 2.0, 4)

    def tracker_for(route, cs_state):
        tracker = Tracker(RouteStats(tmp / f"{len(route.path)}-{hash(route.path)}.json", list(route.camps)),
                          55.0, 170.0, 2.0, 4, cs_state)
        for sample in run:
            tracker.feed(*sample)
        return tracker

    tracker = tracker_for(route, CS_UNKNOWN)
    for row in rows:
        sample = (float(row[1]), float(row[2]), int(row[3]) if row[3] else None)
        run.append(sample)
        if detector.feed(*sample, tracker.cs_state) and tracker.state in ("running", "finished"):
            new = best_route(detector.steps, routes, route, camp_gold)
            if new is not None:
                tracker.discard_run()
                route, tracker = new, tracker_for(new, tracker.cs_state)
                continue
        tracker.feed(*sample)
    return route, tracker


class RealClearsTest(unittest.TestCase):
    def test_every_camp_closes_on_its_own_gold(self):
        for name, (champion, start, cleared) in CLEARS.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                route, tracker = replay(FIXTURES / name, champion, start, Path(tmp))
                self.assertEqual(route.path, cleared)
                self.assertEqual(tracker.state, FINISHED)
                for camp, split in zip(route.camps, tracker.splits):
                    if camp_key(camp) != "recall":
                        self.assertAlmostEqual(split.gold, DEFAULT_CAMP_GOLD[camp_key(camp)], delta=3,
                                               msg=f"{camp} closed at {split.time}")


if __name__ == "__main__":
    unittest.main()
