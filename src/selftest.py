"""`JungleSplits.exe --self-test REPORT`: checks, inside the packaged app, everything a release needs at
runtime (bundled files, libraries loaded on demand, sounds, a window), then exits 0 if all passed.
Packaging mistakes (a data file or hidden import left out of the build) only show up here, not in
the unit tests, which run from source."""
from __future__ import annotations

import json
import tempfile
import traceback
from pathlib import Path


def run_checks() -> list[tuple[str, bool, str]]:
    results = []

    def check(name, fn):
        try:
            detail = fn()
            results.append((name, True, str(detail or "")))
        except Exception:  # noqa: BLE001 - every failure must end up in the report
            results.append((name, False, traceback.format_exc(limit=3)))

    import paths

    def bundled_files():
        missing = [str(p) for p in (paths.CONFIG, paths.FALLBACK_SHEET, paths.ICON_ICO, paths.ICON_PNG,
                                    paths.BUNDLE_DIR / "sons" / "LEIA-ME.txt") if not p.exists()]
        assert not missing, f"missing: {missing}"
        return paths.BUNDLE_DIR

    def config():
        data = json.loads(paths.CONFIG.read_text(encoding="utf-8"))
        assert data["hotkeys"] and data["camp_spawn"]
        return f"{len(data['hotkeys'])} hotkeys"

    def sheet():
        import sheet as sheet_module
        routes = sheet_module.parse_sheet(paths.FALLBACK_SHEET.read_text(encoding="utf-8"))
        assert len(routes) > 50, len(routes)
        return f"{len(routes)} champions"

    def tray_library():
        import pystray._win32  # loaded by name at runtime, easy to leave out of a build
        from PIL import Image
        Image.open(paths.ICON_PNG).load()
        return "pystray + Pillow"

    def sounds():
        from sound import SOUND_NAMES, Sounds
        with tempfile.TemporaryDirectory() as tmp:
            made = Sounds(Path(tmp), volume=0.1, enabled=False)
            assert all(made.path(name).stat().st_size > 1000 for name in SOUND_NAMES)
        return f"{len(SOUND_NAMES)} tones"

    def window():
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.iconbitmap(default=str(paths.ICON_ICO))
        tk.Canvas(root).pack()
        root.update()
        root.destroy()
        return "tk"

    def renderer():
        # The overlay's own drawing: Windows fonts found, text opaque on the translucent panel.
        from render import FACES, Frame, Renderer
        r = Renderer()
        names = {face: " ".join(r.font(face, 16).getname()) for face in FACES}
        frame = Frame(120)
        frame.height = 40
        frame.text(10, 20, "1:23.4 ▶", "#ffffff", ("num_bold", 20), "w")
        image = r.render(frame, r.panel(120, 40, 0.5, 8, 6, "#0e1014", ("#a63dff",), 3), 6)
        alphas = image.getchannel("A").getextrema()
        assert alphas[1] == 255 and image.getpixel((6 + 100, 6 + 30))[3] < 255, alphas
        return f"{names['num_bold']}, {names['ui']}"

    def windows():
        # Settings, first-run screen and pop-ups draw their widgets with Pillow through ImageTk.
        import tkinter as tk
        import display
        from popup import Popup
        from settings_window import ACTIONS, PAGES, SettingsWindow
        from welcome import WelcomeWindow
        root = tk.Tk()
        root.withdraw()
        try:
            noop = lambda *_a: None  # noqa: E731
            values = {"language": "en", "champion": "Lee Sin", "target": None, "smites": 1, "scale": 1.0,
                      "opacity": 0.85, "show": display.PRESETS["full"], "update_version": "", "sound_theme": "suave",
                      "sound_volume": 0.3, "binds": {a: "" for a in ACTIONS}, "default_binds": {}}
            settings = SettingsWindow(root, values, noop, noop, noop, noop, noop, noop, None, list, noop, noop)
            for page in PAGES:
                settings._show_tab(page)
                root.update()
            settings._cancel()
            WelcomeWindow(root, None, {"settings": "-", "move": "-"}, noop)._done()
            Popup(root, None, "Title", "Text", [("OK", None, True)], noop)._close()
        finally:
            root.destroy()
        return f"{len(PAGES)} settings pages"

    def logic():
        from tracker import RouteStats, Tracker
        camps = ["Red", "Gromp"]
        with tempfile.TemporaryDirectory() as tmp:
            tracker = Tracker(RouteStats(Path(tmp) / "r.json", camps), camp_spawn=55.0)
            gold, t = 50.0, 50.0
            for kill_at, kill_gold in ((70.0, 90), (85.0, 80)):
                while t < kill_at + 3:
                    t += 0.1
                    gold += 0.2 + (kill_gold if abs(t - kill_at) < 0.05 else 0)
                    tracker.feed(t, gold, None)
            assert tracker.state == "finished", tracker.state
        return f"{len(tracker.splits)} splits"

    def updater_module():
        import updater
        from version import __version__
        assert updater.version_tuple(__version__) > (0,)
        return __version__

    for name, fn in (("bundled files", bundled_files), ("config", config), ("sheet", sheet),
                     ("tray library", tray_library), ("sounds", sounds), ("window", window), ("renderer", renderer), ("windows", windows),
                     ("timing logic", logic), ("updater", updater_module)):
        check(name, fn)
    return results


def main(report: Path) -> int:
    results = run_checks()
    lines = [f"{'PASS' if ok else 'FAIL'}  {name}  {detail}".rstrip() for name, ok, detail in results]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if all(ok for _, ok, _ in results) else 1
