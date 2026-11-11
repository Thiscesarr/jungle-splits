"""The real overlay app (App), its window included: the layer the other tests don't reach. Samples go
through App._on_sample, the same path live game data takes (route detection, switching routes, replaying
the run), and the window's Windows flags are read back from the system."""
import ctypes
import json
import random
import sys
import time
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from types import SimpleNamespace

import display
import paths
from i18n import set_language
from overlay import NO_BOX, App
from popup import Popup
from welcome import WelcomeWindow
from updater import Update
from sheet import norm
from sim import samples, simulate_clear
from sources import Sample
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

    def test_unchanged_frame_is_not_drawn_again(self):
        """Waiting for a game nothing changes, and then the overlay must cost (almost) nothing."""
        app = self.app
        app._redraw()
        shown = app.last_image
        self.assertEqual(shown.size, (app.root.winfo_width(), app.root.winfo_height()))
        for _ in range(3):
            app._tick()
        self.assertIs(app.last_image, shown)
        app._command("mute")  # the footer changes: a new frame
        app._tick()
        self.assertIsNot(app.last_image, shown)
        app._command("mute")

    def test_minimized_overlay_draws_nothing(self):
        app = self.app
        app._set_minimized(True)
        shown = app.last_image
        app._command("mute")
        app._tick()
        self.assertIs(app.last_image, shown)
        app._command("mute")
        app._set_minimized(False)
        self.assertIsNot(app.last_image, shown)

    # --- only the Practice Tool ----------------------------------------------------------------

    def sample(self, game_time: float, gold: float) -> tuple:
        return "sample", Sample(game_time, gold, 0, 1, 1, "Lee Sin", None, time.perf_counter())

    def test_overlay_hides_in_a_game_that_is_not_the_practice_tool(self):
        app = self.app
        self.assertEqual(self.window(), (True, True))
        history = len(app.tracker.stats.history)
        attempts = app.tracker.stats.attempts
        app.events.put(("other_game", "CLASSIC"))  # a ranked game started
        app._tick()
        self.assertEqual(self.window()[0], False)
        self.assertFalse(app.connected)
        shown = app.last_image
        for _ in range(3):
            app._tick()
        self.assertIs(app.last_image, shown)  # nothing drawn while hidden
        app._command("move")  # the move hotkey doesn't bring it up over the game
        self.assertEqual(self.window()[0], False)
        self.assertFalse(app.move_mode)
        app.events.put(("offline",))  # the game ended
        app._tick()
        self.assertEqual(self.window(), (True, True))
        self.assertIsNone(app.other_game)
        self.assertEqual((len(app.tracker.stats.history), app.tracker.stats.attempts), (history, attempts))

    def test_practice_tool_right_after_another_game_shows_the_overlay(self):
        app = self.app
        app.events.put(("other_game", "ARAM"))
        app._tick()
        self.assertEqual(self.window()[0], False)
        app.events.put(self.sample(12.0, 500.0))
        app._tick()
        self.assertEqual(self.window(), (True, True))
        self.assertTrue(app.connected)
        app.events.put(("offline",))
        app._tick()

    def test_minimized_overlay_stays_minimized_after_another_game(self):
        app = self.app
        app._set_minimized(True)
        app.events.put(("other_game", "CLASSIC"))
        app._tick()
        app.events.put(("offline",))
        app._tick()
        self.assertEqual(self.window()[0], False)  # the player hid it: still hidden
        app._command("show")
        self.assertEqual(self.window(), (True, True))

    def test_move_mode_ends_when_another_game_starts(self):
        app = self.app
        app._set_move_mode(True)
        app.events.put(("other_game", "CLASSIC"))
        app._tick()
        self.assertFalse(app.move_mode)
        app.events.put(("offline",))
        app._tick()
        self.assertEqual(self.window(), (True, True))  # back, and clicks pass through again

    def test_no_popups_over_a_game_that_is_not_the_practice_tool(self):
        app = self.app
        app.events.put(("other_game", "CLASSIC"))
        app.events.put(("notices", {"notices": [{"id": "ranked-notice", "title": {"en": "Ranked"},
                                                 "text": {"en": "Not now"}}]}))
        app._tick()
        self.assertEqual(self.popups(), [])
        app.events.put(("offline",))
        app._tick()
        shown = self.popups()
        self.assertEqual([w.title() for w in shown], ["Ranked"])
        shown[0]._click(None)

    # --- what the overlay shows ----------------------------------------------------------------

    def press(self, box):
        """A click in the middle of a box of the overlay (panel coordinates), as Windows sends it."""
        app = self.app
        app._drag_moved = False
        x, y = (box[0] + box[2]) // 2 + app.margin, (box[1] + box[3]) // 2 + app.margin
        app._click_release(SimpleNamespace(x=x, y=y))

    def test_display_presets_change_only_the_drawing(self):
        """The same clear gives the same splits, PB and attempts whatever the overlay shows."""
        app = self.app
        route = "Raptors->Red->Krugs->Recall->Wolves->Gromp->Blue"
        results = []
        try:
            for name in display.PRESET_ORDER + ("custom",):
                app._show_parts(display.PRESETS.get(name, {**display.PRESETS["full"], "verdict": False}))
                self.play("Lee Sin", route, route.split("->"), seed=21)
                results.append(app.tracker.stats.history[-1]["splits"])
                self.assertIsNotNone(app.last_image)
        finally:
            app._show_parts(display.PRESETS["full"])
        self.assertTrue(all(r == results[0] for r in results), results)

    def test_clock_only_is_a_small_panel(self):
        app = self.app
        sizes = {}
        try:
            for name in display.PRESET_ORDER:
                app._show_parts(display.PRESETS[name])
                sizes[name] = app.last_image.size
                app.root.update()
                self.assertEqual(sizes[name], (app.root.winfo_width(), app.root.winfo_height()))  # window fits
        finally:
            app._show_parts(display.PRESETS["full"])
        self.assertLess(sizes["clock"][0], sizes["full"][0] * 0.7)
        self.assertLess(sizes["clock"][1], sizes["splits"][1])
        self.assertLess(sizes["splits"][1], sizes["full"][1])
        self.assertEqual(sizes["splits"][0], sizes["full"][0])

    def test_every_single_part_draws(self):
        app = self.app
        try:
            for part in display.PARTS:
                for move in (False, True):
                    app._set_move_mode(move)
                    app._show_parts({p: p == part for p in display.PARTS})
                    self.assertIsNotNone(app.last_image, part)
        finally:
            app._set_move_mode(False)
            app._show_parts(display.PRESETS["full"])

    def test_move_mode_buttons_work_on_the_small_panel(self):
        app = self.app
        try:
            app._show_parts(display.PRESETS["clock"])
            app._set_move_mode(True)
            width = app.last_image.width - 2 * app.margin
            for box in (app._close_box, app._minimize_box):
                self.assertTrue(0 <= box[0] < box[2] <= width, box)
            self.press(app._minimize_box)
            self.assertTrue(app.minimized)
            self.assertFalse(app.move_mode)
        finally:
            app._set_minimized(False)
            app._show_parts(display.PRESETS["full"])
        self.assertEqual(self.window(), (True, True))

    def test_hidden_video_link_cannot_be_clicked(self):
        app = self.app
        opened = []
        app._open_video = lambda: opened.append(1)
        try:
            app._set_champion("Lee Sin")
            app._select_route(next(r for r in app.champion_routes() if r.video))
            app._set_move_mode(True)
            self.assertNotEqual(app._video_box, NO_BOX)
            self.press(app._video_box)
            self.assertEqual(opened, [1])
            app._show_parts({**display.PRESETS["full"], "video": False})
            self.assertEqual(app._video_box, NO_BOX)
        finally:
            del app._open_video
            app._set_move_mode(False)
            app._show_parts(display.PRESETS["full"])

    def test_settings_save_and_cancel_the_overlay_parts(self):
        app = self.app
        app._open_settings()
        window = app.settings_window
        window._show_tab("overlay")
        window.preset.set("splits")
        window._apply_preset()
        self.assertEqual(app.show, display.PRESETS["splits"])  # live, before saving
        window._cancel()
        self.assertEqual(app.show, display.PRESETS["full"])
        self.assertIsNone(app.settings_window)

        app._open_settings()
        window = app.settings_window
        window.preset.set("clock")
        window._apply_preset()
        window._save()
        try:
            self.assertEqual(app.show, display.PRESETS["clock"])
            saved = json.loads(app.ui_state_path.read_text(encoding="utf-8"))
            self.assertEqual(display.normalize(saved["overlay_show"]), display.PRESETS["clock"])
            self.assertTrue(app.hotkeys is not None)  # the hotkeys came back after Settings closed
        finally:
            app.ui_state["overlay_show"] = display.PRESETS["full"]
            app._save_ui_state()
            app._show_parts(display.PRESETS["full"])
            app.hotkeys.stop()

    def test_settings_window_pages_through_the_app(self):
        app = self.app
        app._open_settings()
        window = app.settings_window
        try:
            for page in window.pages:
                window._show_tab(page)
                app.root.update()
            app._open_settings()  # a second open only brings it forward
            self.assertIs(app.settings_window, window)
        finally:
            window._cancel()
            app.hotkeys.stop()

    def test_popups_and_welcome_in_the_new_look(self):
        app = self.app
        chosen = []
        welcome = WelcomeWindow(app.root, app.icon_image, {"settings": "Ctrl+Shift+,", "move": "Ctrl+Shift+."},
                                chosen.append)
        app.root.update()
        welcome.language.set("pt")
        welcome._pick()
        self.assertEqual(welcome.title(), "Bem-vindo ao Jungle Splits")
        welcome._done()
        self.assertEqual(chosen, ["pt"])
        set_language("en")
        clicked = []
        popup = Popup(app.root, app.icon_image, "Title", "Text", [("OK", lambda: clicked.append("ok"), True),
                                                                 ("Delete", lambda: clicked.append("x"), "danger")],
                      lambda: clicked.append("closed"), note="note")
        self.assertEqual([b.kind for b in popup.buttons], ["primary", "danger"])
        popup.buttons[1].invoke()
        self.assertEqual(clicked, ["closed", "x"])
        self.assertFalse(popup.winfo_exists())

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

    # --- pop-ups -------------------------------------------------------------------------------

    def popups(self) -> list:
        return [w for w in self.app.root.winfo_children() if isinstance(w, Popup)]

    def test_update_and_notice_popups_wait_for_the_game_to_close(self):
        app = self.app
        app.connected = True  # a game is running
        app.events.put(("update_available", Update("9.9.9", "https://github.com/Thiscesarr/jungle-splits/releases/download/v9.9.9/JungleSplits-Setup.exe",
                                                   "https://github.com/Thiscesarr/jungle-splits/releases/download/v9.9.9/SHA256SUMS.txt", "https://github.com/Thiscesarr/jungle-splits/releases/tag/v9.9.9")))
        app.events.put(("notices", {"notices": [{"id": "test-notice", "title": {"en": "News"},
                                                 "text": {"en": "Something changed"}}]}))
        app._tick()
        self.assertEqual(self.popups(), [])  # never over a game
        self.assertTrue(app.update)  # the overlay line still offers it
        app.connected = False  # the game closed
        app._tick()
        shown = self.popups()
        self.assertEqual(len(shown), 1)  # one at a time, the update first
        self.assertIn("9.9.9", shown[0].title())
        shown[0]._click(None)  # "Later"
        app._tick()
        shown = self.popups()
        self.assertEqual([w.title() for w in shown], ["News"])
        shown[0]._click(None)
        self.assertIn("test-notice", app.ui_state["notices_seen"])
        app.events.put(("notices", {"notices": [{"id": "test-notice", "title": {"en": "News"},
                                                 "text": {"en": "Something changed"}}]}))
        app._tick()
        self.assertEqual(self.popups(), [])  # a notice is shown only once
        app.update = None

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
