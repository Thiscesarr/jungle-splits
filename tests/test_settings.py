"""The settings window, driven like a player would: pages, every control, Save and Cancel, hotkey
capture, records deletion. Its callbacks are recorded instead of reaching the app."""
import sys
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import display
from i18n import language, set_language, t
from popup import Popup
from settings_window import ACTIONS, PAGES, SettingsWindow
from ui import Button, Segmented, Slider, Switch

VK_A, VK_F5, VK_ESCAPE = 0x41, 0x74, 0x1B
DEFAULT_BINDS = {"split": "ctrl+shift+oem_1", "undo": "ctrl+shift+oem_2", "reset": "ctrl+shift+oem_6",
                 "next_route": "ctrl+shift+oem_5", "smites": "ctrl+shift+oem_plus", "move": "ctrl+shift+oem_period",
                 "settings": "ctrl+shift+oem_comma", "mute": "ctrl+shift+oem_minus", "quit": ""}
VALUES = {"language": "en", "champion": "Lee Sin", "target": 170.0, "smites": 1, "scale": 0.8, "opacity": 0.85,
          "show": display.PRESETS["full"], "update_version": "", "binds": dict(DEFAULT_BINDS),
          "default_binds": dict(DEFAULT_BINDS), "sound_theme": "suave", "sound_volume": 0.35}


def control(root, variable):
    """The Segmented or Slider that sets this variable."""
    return next(w for w in widgets(root, (Segmented, Slider)) if w.variable is variable)


def widgets(root, kind):
    found, todo = [], [root]
    while todo:
        widget = todo.pop()
        if isinstance(widget, kind):
            found.append(widget)
        todo.extend(widget.winfo_children())
    return found


class SettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        set_language("en")
        self.calls: dict[str, list] = {name: [] for name in ("save", "close", "preview", "sounds", "opacity", "logs", "scale",
                                                            "update", "delete", "show")}
        self.records = [SimpleNamespace(champion="Lee Sin", camps=["Red", "Krugs"], smites=1, pb=171.2, attempts=4,
                                        path=Path(f"r{i}.json")) for i in range(3)]

    def open(self, on_screen: bool = False, **values) -> SettingsWindow:
        c = self.calls

        def delete(paths):
            c["delete"].append(paths)
            self.records = [r for r in self.records if r.path not in paths]
            return len(paths)

        window = SettingsWindow(self.root, VALUES | values, c["save"].append, lambda: c["close"].append(1),
                                lambda *a: c["preview"].append(a), lambda: c["sounds"].append(1), c["opacity"].append,
                                lambda: c["logs"].append(1), lambda: c["update"].append(1), lambda: self.records,
                                delete, c["show"].append, None, c["scale"].append)
        if not on_screen:
            window.geometry("+-3000+0")
        self.root.update()
        self.addCleanup(lambda: window.winfo_exists() and window.destroy())
        return window

    def page(self, window, name):
        window._show_tab(name)
        self.root.update()
        return window.pages[name]

    # --- pages -----------------------------------------------------------------------------------

    def test_every_page_opens_and_the_window_keeps_its_size(self):
        window = self.open()
        size = None
        for name in PAGES:
            page = self.page(window, name)
            self.assertTrue(window.nav[name].selected)
            self.assertEqual(sum(item.selected for item in window.nav.values()), 1)
            now = (window.winfo_width(), window.winfo_height())
            self.assertTrue(size is None or now == size, name)  # no jump between pages
            size = now

    def test_opens_in_the_middle_of_the_screen(self):
        window = self.open(on_screen=True)
        middle = (window.winfo_rootx() + window.winfo_width() / 2, window.winfo_rooty() + window.winfo_height() / 2)
        self.assertAlmostEqual(middle[0], window.winfo_screenwidth() / 2, delta=20)
        self.assertAlmostEqual(middle[1], window.winfo_screenheight() / 2, delta=40)  # the title bar sits above
        window.geometry("+40+40")  # the player moves it
        self.root.update()
        window._show_tab("overlay")
        window.language.set("pt")
        window._build()  # a rebuild (language change) doesn't move it back
        self.root.update()
        self.assertLess(window.winfo_rootx(), 80)

    def test_save_without_changes_keeps_everything(self):
        window = self.open()
        window._save()
        saved = self.calls["save"][0]
        expected = {key: VALUES[key] for key in ("language", "target", "smites", "scale", "opacity", "binds",
                                                 "sound_theme", "sound_volume", "show")}
        self.assertEqual(saved, expected)
        self.assertEqual(self.calls["close"], [1])
        self.assertFalse(window.winfo_exists())

    def test_cancel_puts_back_the_previews(self):
        window = self.open()
        page = self.page(window, "overlay")
        control(page, window.opacity).set(40)
        self.assertEqual(self.calls["opacity"], [0.4])
        control(page, window.preset).choose("clock")
        self.assertEqual(self.calls["show"][-1], display.PRESETS["clock"])
        window._cancel()
        self.assertEqual(self.calls["opacity"][-1], 0.85)
        self.assertEqual(self.calls["show"][-1], display.PRESETS["full"])
        self.assertEqual(self.calls["save"], [])

    # --- general ---------------------------------------------------------------------------------

    def test_general_controls_reach_the_saved_values(self):
        window = self.open()
        page = self.page(window, "general")
        control(page, window.smites).choose(2)
        window.target.set("2:41")
        window._save()
        saved = self.calls["save"][0]
        self.assertEqual((saved["smites"], saved["target"]), (2, 161.0))

    def test_empty_target_means_none(self):
        window = self.open()
        window.target.set("  ")
        window._save()
        self.assertIsNone(self.calls["save"][0]["target"])

    def test_invalid_target_is_refused(self):
        window = self.open()
        self.page(window, "sounds")
        for text in ("250", "0:10", "abc", "20:00"):
            window.target.set(text)
            window._save()
            self.assertEqual(self.calls["save"], [], text)
            self.assertEqual(window.tab, "general")
            self.assertEqual(window.status.cget("text"), t("target_invalid"))

    def test_language_switch_rebuilds_and_cancel_undoes_it(self):
        window = self.open()
        before = language()
        control(window.pages["general"], window.language).choose("pt")
        self.root.update()
        self.assertEqual(window.title(), "Jungle Splits · Configurações")
        self.assertEqual(window.tab, "general")
        window._cancel()
        self.assertEqual(language(), before)

    def test_language_switch_keeps_the_page_and_unsaved_values(self):
        window = self.open()
        self.page(window, "overlay")
        window.preset.set("splits")
        window._apply_preset()
        window.language.set("pt")
        window._build()
        self.assertEqual(window.tab, "overlay")
        self.assertEqual(window.shown_parts(), display.PRESETS["splits"])
        window._save()
        self.assertEqual(self.calls["save"][0]["language"], "pt")
        set_language("en")

    # --- overlay ---------------------------------------------------------------------------------

    def test_presets_switch_the_parts(self):
        window = self.open()
        page = self.page(window, "overlay")
        presets = control(page, window.preset)
        for name in display.PRESET_ORDER:
            presets.choose(name)
            self.assertEqual(window.shown_parts(), display.PRESETS[name])
            self.assertEqual(self.calls["show"][-1], display.PRESETS[name])
        window._save()
        self.assertEqual(self.calls["save"][0]["show"], display.PRESETS["full"])

    def test_a_switch_makes_the_choice_custom(self):
        window = self.open()
        page = self.page(window, "overlay")
        switches = widgets(page, Switch)
        self.assertEqual(len(switches), len(display.PARTS))
        runes = next(s for s in switches if s.variable is window.show["runes"])
        runes.toggle()
        self.assertEqual(window.preset.get(), display.CUSTOM)
        self.assertFalse(self.calls["show"][-1]["runes"])
        runes.toggle()
        self.assertEqual(window.preset.get(), "full")
        window._save()
        self.assertTrue(self.calls["save"][0]["show"]["runes"])

    def test_opens_on_a_custom_choice(self):
        custom = {**display.PRESETS["full"], "video": False, "runes": False}
        window = self.open(show=custom)
        self.assertEqual(window.preset.get(), display.CUSTOM)
        self.assertEqual(window.shown_parts(), custom)
        window._save()
        self.assertEqual(self.calls["save"][0]["show"], custom)

    def test_size_slider_previews_live_and_cancel_puts_it_back(self):
        window = self.open()
        size = control(self.page(window, "overlay"), window.scale)
        size.set(120)
        size.set(120)  # no change: no second call
        size.event_generate("<B1-Motion>", x=size.track_x + size.length, y=10)  # dragged to the end
        self.assertEqual(self.calls["scale"], [1.2, 1.6])
        window._cancel()
        self.assertEqual(self.calls["scale"][-1], 0.8)
        self.assertEqual(self.calls["save"], [])

    def test_size_and_opacity_sliders(self):
        window = self.open()
        page = self.page(window, "overlay")
        size, opacity = control(page, window.scale), control(page, window.opacity)
        self.assertEqual((size.from_, size.to, size.step), (70, 160, 10))
        self.assertEqual((opacity.from_, opacity.to, opacity.step), (30, 100, 5))
        size.set(120)
        opacity.set(60)
        window._save()
        saved = self.calls["save"][0]
        self.assertEqual((saved["scale"], saved["opacity"]), (1.2, 0.6))

    # --- hotkeys ---------------------------------------------------------------------------------

    def key(self, window, keycode):
        window._key(SimpleNamespace(keycode=keycode))

    def test_hotkey_capture(self):
        window = self.open()
        self.page(window, "hotkeys")
        self.assertEqual(set(window.hotkey_buttons), set(ACTIONS))
        window.hotkey_buttons["split"].invoke()
        self.assertEqual(window.capturing, "split")
        self.assertEqual(window.hotkey_buttons["split"].text, t("press_keys"))
        self.key(window, 0x11)  # Ctrl alone: still waiting for the key
        self.assertEqual(window.capturing, "split")
        self.key(window, VK_F5)
        self.assertIsNone(window.capturing)
        self.assertEqual(window.binds["split"].lower(), "f5")
        self.assertIn("F5", window.status.cget("text"))  # no modifier: warned
        window._save()
        self.assertEqual(self.calls["save"][0]["binds"]["split"].lower(), "f5")

    def test_hotkey_taken_from_another_action(self):
        window = self.open()
        self.page(window, "hotkeys")
        window._start_capture("quit")
        self.key(window, VK_F5)
        window._start_capture("mute")
        self.key(window, VK_F5)
        self.assertEqual(window.binds["quit"], "")
        self.assertEqual(window.binds["mute"].lower(), "f5")
        self.assertEqual(window.hotkey_buttons["quit"].text, t("none"))

    def test_escape_cancels_and_restore_defaults(self):
        window = self.open()
        self.page(window, "hotkeys")
        window._start_capture("reset")
        self.key(window, VK_ESCAPE)
        self.assertEqual(window.binds["reset"], DEFAULT_BINDS["reset"])
        window._start_capture("reset")
        self.key(window, VK_A)
        self.assertNotEqual(window.binds["reset"], DEFAULT_BINDS["reset"])
        window._restore_binds()
        self.assertEqual(window.binds, DEFAULT_BINDS)

    def test_changing_page_stops_a_capture(self):
        window = self.open()
        self.page(window, "hotkeys")
        window._start_capture("undo")
        self.page(window, "sounds")
        self.key(window, VK_A)
        self.assertEqual(window.binds["undo"], DEFAULT_BINDS["undo"])

    # --- sounds ----------------------------------------------------------------------------------

    def test_sound_controls(self):
        window = self.open()
        page = self.page(window, "sounds")
        control(page, window.theme).choose("grave")
        control(page, window.volume).set(70)
        buttons = {b.text: b for b in widgets(page, Button)}
        buttons[t("sound_test")].invoke()
        buttons[t("open_sounds_folder")].invoke()
        self.assertEqual(self.calls["preview"], [("grave", 0.7)])
        self.assertEqual(self.calls["sounds"], [1])
        window._save()
        self.assertEqual((self.calls["save"][0]["sound_theme"], self.calls["save"][0]["sound_volume"]), ("grave", 0.7))

    # --- records ---------------------------------------------------------------------------------

    def popups(self, window):
        return [w for w in window.winfo_children() if isinstance(w, Popup)]

    def test_delete_records_after_confirming(self):
        window = self.open()
        self.page(window, "records")
        self.assertEqual(window.records_list.size(), 3)
        window.records_list.selection_set(0)
        window.records_list.selection_set(2)
        window._delete_records()
        confirm = self.popups(window)
        self.assertEqual(len(confirm), 1)
        self.assertEqual([b.kind for b in confirm[0].buttons], ["danger", "secondary"])
        confirm[0].buttons[0].invoke()
        self.assertEqual(self.calls["delete"], [[Path("r0.json"), Path("r2.json")]])
        self.assertEqual(window.records_list.size(), 1)
        self.assertEqual(window.tab, "records")
        self.assertEqual(window.status.cget("text"), t("records_deleted", n=2))

    def test_delete_cancelled_or_nothing_selected(self):
        window = self.open()
        self.page(window, "records")
        window._delete_records()
        self.assertEqual(window.status.cget("text"), t("records_none_selected"))
        self.assertEqual(self.popups(window), [])
        window.records_list.selection_set(1)
        window._delete_records()
        self.popups(window)[0].buttons[1].invoke()  # Cancel
        self.assertEqual(self.calls["delete"], [])
        self.assertEqual(window.records_list.size(), 3)

    def test_no_records(self):
        self.records = []
        window = self.open()
        self.page(window, "records")
        self.assertIsNone(window.records_list)
        window._delete_records()  # the button isn't there, but nothing breaks
        self.assertEqual(self.calls["delete"], [])

    def test_many_records_scroll(self):
        self.records = [SimpleNamespace(champion="Vi", camps=["Red"], smites=2, pb=None, attempts=i,
                                        path=Path(f"v{i}.json")) for i in range(25)]
        window = self.open()
        self.page(window, "records")
        self.assertEqual(window.records_list.size(), 25)
        self.assertEqual(int(window.records_list.cget("height")), 10)

    # --- about -----------------------------------------------------------------------------------

    def test_about_buttons(self):
        window = self.open()
        page = self.page(window, "about")
        texts = {b.text for b in widgets(page, Button)}
        self.assertIn(t("open_logs"), texts)
        self.assertNotIn(t("menu_update", version="9.9.9"), texts)
        next(b for b in widgets(page, Button) if b.text == t("open_logs")).invoke()
        self.assertEqual(self.calls["logs"], [1])

    def test_update_button_when_one_is_waiting(self):
        window = self.open(update_version="9.9.9")
        page = self.page(window, "about")
        update = next(b for b in widgets(page, Button) if b.text == t("menu_update", version="9.9.9"))
        update.invoke()
        self.assertEqual(self.calls["update"], [1])
        self.assertEqual(self.calls["close"], [1])  # the window closes first
        self.assertFalse(window.winfo_exists())


if __name__ == "__main__":
    unittest.main()
