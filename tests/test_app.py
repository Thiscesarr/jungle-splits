"""The real overlay app (App), its window included: the layer the other tests don't reach. Samples go
through App._on_sample, the same path live game data takes (route detection, switching routes, replaying
the run), and the window's Windows flags are read back from the system."""
import ctypes
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths
from overlay import App
from sheet import norm
from sim import samples, simulate_clear
from tracker import DEFAULT_CAMP_GOLD, FINISHED, MULTI_MONSTER_CAMPS, RouteStats, camp_key, slug

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PERIOD = 0.13
GWL_EXSTYLE, WS_EX_TRANSPARENT, WS_EX_LAYERED = -20, 0x20, 0x80000
user32 = ctypes.windll.user32
user32.GetWindowLongW.restype = ctypes.c_long


class NoSource:
    """The tests feed samples themselves."""

    def start_feeding(self, events):
        pass


def signature(camps) -> list[tuple]:
    """What gold can tell of a route: Red and Blue pay the same."""
    return [("recall",) if camp_key(c) == "recall" else (camp_key(c) in MULTI_MONSTER_CAMPS,
                                                          DEFAULT_CAMP_GOLD[camp_key(c)]) for c in camps]


class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.tmp.name)
        (cls.data / "ui_state.json").write_text(json.dumps({"welcomed": True, "language": "en"}), encoding="utf-8")
        config = json.loads(paths.CONFIG.read_text(encoding="utf-8"))
        config["auto_update_sheet"] = False
        cls.app = App(config, cls.data, NoSource(), paths.FALLBACK_SHEET, cls.data / "custom_sounds")
        cls.app.sounds.enabled = False
        cls.app.hotkeys.stop()  # keys pressed while the tests run must not reach the app

    @classmethod
    def tearDownClass(cls):
        cls.app.quit()
        cls.tmp.cleanup()

    def window(self) -> tuple[bool, bool]:
        """(visible, clicks pass through) as Windows sees the overlay."""
        self.app.root.update()
        style = user32.GetWindowLongW(self.app.hwnd, GWL_EXSTYLE)
        return (bool(user32.IsWindowVisible(self.app.hwnd)),
                bool(style & WS_EX_TRANSPARENT) and bool(style & WS_EX_LAYERED))

    def play(self, champion: str, start_route: str, camps: list[str], seed: int):
        """Plays a simulated clear into the app after a Practice Tool reset; returns the clear."""
        app = self.app
        if app.champion != champion:
            app._set_champion(champion)
        app._select_route(next(r for r in app.champion_routes() if r.path == start_route))
        rng = random.Random(seed)
        clear = simulate_clear(camps, rng)
        for t, gold, cs in samples(clear, rng, start=1.0):
            app._on_sample(t, gold, cs)
        app._on_sample(0.5, 500.0, 0)  # the next reset: the clock goes back
        return clear

    # --- window --------------------------------------------------------------------------------

    def test_clicks_pass_through_the_overlay(self):
        """The opacity setting used to drop the click-through flag (Tk rewrites the window style)."""
        app = self.app
        self.assertEqual(self.window(), (True, True))
        app._show_opacity(0.5)
        self.assertEqual(self.window(), (True, True))
        app._show_opacity(app.opacity)
        app._set_move_mode(True)
        self.assertEqual(self.window(), (True, False))  # move mode: the overlay takes clicks
        app._set_move_mode(False)
        self.assertEqual(self.window(), (True, True))

    def test_minimize_and_bring_back(self):
        app = self.app
        app._set_move_mode(True)
        app._set_minimized(True)
        self.assertEqual(self.window(), (False, True))
        self.assertFalse(app.move_mode)
        app._command("move")  # the move hotkey brings it back, not straight into move mode
        self.assertEqual(self.window(), (True, True))
        self.assertFalse(app.move_mode)
        app._set_minimized(True)
        app._command("show")  # the tray item
        self.assertEqual(self.window(), (True, True))

    # --- timing through the app ----------------------------------------------------------------

    def check_clear(self, champion, start_route, truth, seed):
        clear = self.play(champion, start_route, list(truth), seed)
        context = f"{champion}: cleared {'->'.join(truth)} from {start_route}, seed {seed}"
        self.assertEqual(signature(self.app.route.camps)[:len(truth)], signature(truth), context)
        # The finished run was saved: read the splits back from the route's history.
        history = self.app.tracker.stats.history
        self.assertTrue(history, context)
        for camp, split, death in zip(truth, history[-1]["splits"], clear.deaths):
            self.assertGreaterEqual(split, round(death, 2) - 0.01, f"{camp} closed early: {context}")
            self.assertLess(split - death, SAMPLE_PERIOD, f"{camp} closed late: {context}")

    def test_every_route_of_some_champions(self):
        """Each route of these champions, starting on another route: detection must switch to it and
        every split must land on its camp's last kill."""
        rng = random.Random(5)
        for champion in ("Lee Sin", "Cho'Gath", "Master Yi", "Vi"):
            self.app._set_champion(champion)
            routes = self.app.champion_routes()
            for seed, truth in enumerate(routes):
                start = rng.choice([r for r in routes if r.path != truth.path] or routes)
                self.check_clear(champion, start.path, truth.camps, seed)

    def test_issue_1_chogath_krugs(self):
        """GitHub issue #1: on 1.0.2 a Cho'Gath clear's Krugs only registered after killing another camp,
        because the wolves (85 gold, expected 105) never closed and every split shifted by one camp."""
        route = "Blue->Gromp->Wolves->Raptors->Red->Krugs"
        for seed in range(5):
            clear = self.play("Cho'Gath", route, route.split("->") + ["Krugs"], seed)  # then the other Krugs
            splits = self.app.tracker.stats.history[-1]["splits"]
            self.assertEqual(len(splits), 6)
            self.assertLess(abs(splits[5] - clear.deaths[5]), SAMPLE_PERIOD)  # the first Krugs, on time

    # --- records -------------------------------------------------------------------------------

    def test_deleting_the_route_in_use_forgets_it(self):
        app = self.app
        route = "Raptors->Red->Krugs->Recall->Wolves->Gromp->Blue"
        self.play("Lee Sin", route, route.split("->"), seed=1)
        listed = [r for r in app._records() if r.champion == "Lee Sin" and "->".join(r.camps) == route]
        self.assertEqual(len(listed), 1)
        self.assertIsNotNone(listed[0].pb)
        self.assertEqual(app._delete_records([listed[0].path]), 1)
        self.assertIsNone(app.tracker.stats.pb)  # not kept in memory to be written back
        self.assertEqual(app.tracker.stats.attempts, 0)
        self.assertFalse(listed[0].path.exists())


if __name__ == "__main__":
    unittest.main()
