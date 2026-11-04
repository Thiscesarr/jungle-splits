"""Jungle Splits: F1-style split timer overlay for jungle full clears in the Practice Tool."""
from __future__ import annotations

import argparse
import ctypes
import json
import random
import sys

import paths
from i18n import set_language, system_language, t
from overlay import DEFAULT_CHAMPION, App
from sources import DemoSource, LiveClientSource
from tracker import parse_clock

ERROR_ALREADY_EXISTS = 183
MB_ICONINFORMATION = 0x40


def single_instance() -> object | None:
    """A named mutex held for the app's lifetime; None if another copy already holds it."""
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "JungleSplits.SingleInstance")
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return mutex


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="simulated clears, no game needed")
    parser.add_argument("--demo-speed", type=float, default=1.0, help="simulation speed (e.g. 3)")
    parser.add_argument("--demo-champion", default=DEFAULT_CHAMPION, help="champion used by the demo")
    parser.add_argument("--demo-random-route", action="store_true",
                        help="each simulated clear uses a random route of the champion (shows route detection)")
    parser.add_argument("--settings", "--binds", action="store_true", help="open the settings window on start")
    parser.add_argument("--opaque", action="store_true", help="fully opaque overlay (for screenshots)")
    args = parser.parse_args()

    mutex = single_instance()
    if mutex is None and not args.demo:
        set_language(paths.installer_language() or system_language())
        ctypes.windll.user32.MessageBoxW(None, t("already_running"), "Jungle Splits", MB_ICONINFORMATION)
        sys.exit(0)
    # Own taskbar identity, so Windows shows the app's icon instead of Python's.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("JungleSplits.Overlay")

    config = json.loads(paths.CONFIG.read_text(encoding="utf-8"))
    sounds_dir = paths.ensure_custom_sounds_dir()
    if args.demo:
        # Demo runs keep their own PBs so they never mix with real ones.
        def demo_camps():
            if args.demo_random_route:
                return list(random.choice(app.champion_routes()).camps)
            return app.tracker.camps

        source = DemoSource(demo_camps, args.demo_champion,
                            parse_clock(config.get("camp_spawn", "0:55")), args.demo_speed)
        app = App(config, paths.DEMO_DATA_DIR, source, paths.FALLBACK_SHEET, sounds_dir, args.settings, args.opaque)
    else:
        app = App(config, paths.DATA_DIR, LiveClientSource(), paths.FALLBACK_SHEET, sounds_dir, args.settings,
                  args.opaque)
    app.run()


if __name__ == "__main__":
    main()
