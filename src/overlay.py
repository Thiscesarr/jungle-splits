"""Always-on-top, click-through split overlay: tkinter runs the window and its events, render.py draws
it and layered.py shows it with per-pixel transparency."""
from __future__ import annotations

import ctypes
import json
import math
import os
import queue
import threading
import time
import tkinter as tk
from datetime import date
from pathlib import Path

import display
import notices
import records
import sheet
from detect import CampGold, StepDetector, best_route, route_cost
from hotkeys import HotkeyThread, pretty_combo
from i18n import language, set_language, system_language, t
from layered import LayeredSurface
from links import GITHUB_HOSTS, VIDEO_HOSTS, open_url
from render import Frame, Renderer, rgba
import updater
from paths import FROZEN, ICON_ICO, ICON_PNG, INSTALL_DIR, installer_language
from runlog import RunLog
from settings_window import SettingsWindow
from sheet import Route, norm, parse_path
from sound import SOUND_NAMES, Sounds
from sources import Runes, Sample, champion_name
from ui import menu_colors, use_dark_menus
from tracker import (ABANDONED, CS_OK, CS_UNKNOWN, FINISHED, PURPLE, RUNNING, WAITING, RouteStats, RunClock,
                     Tracker, fmt_clock, fmt_delta, parse_clock, slug)
from version import __version__
from popup import Popup
from welcome import WelcomeWindow

user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x20, 0x80, 0x80000, 0x8000000
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10

BG = "#0e1014"
# Tints laid over the translucent panel, so rows stay glass instead of opaque blocks.
ROW_ALT = (255, 255, 255, 8)
ROW_CURRENT = (120, 160, 255, 38)
SOFT = (255, 255, 255, 26)
TEXT = "#eef0f3"
MUTED = "#7d8697"
AMBER = "#ffb020"
LINK = "#7fb4ff"
SECTOR = {PURPLE: "#a63dff", "green": "#1fc85f", "red": "#e8333a"}
DELTA_AHEAD, DELTA_BEHIND = "#3ee07a", "#ff5a5f"

INTERPOLATE_MAX = 0.15
DEFAULT_CHAMPION = "Lee Sin"
NO_BOX = (0, 0, -1, -1)


def in_box(box: tuple, x: int, y: int) -> bool:
    left, top, right, bottom = box
    return left <= x <= right and top <= y <= bottom


class App:
    def __init__(self, config: dict, data_dir: Path, source, fallback_sheet: Path, custom_sounds_dir: Path,
                 open_settings: bool = False, opaque: bool = False):
        self.config = config
        self.data_dir = data_dir
        self.source = source
        self.custom_sounds_dir = custom_sounds_dir
        self.camp_spawn = parse_clock(config.get("camp_spawn", "0:55"))
        self.quiet_window = float(config.get("quiet_window", 2.0))
        self.cs_per_camp = int(config.get("cs_per_camp", 4))
        self.reset_margin = float(config.get("reset_margin", 2.0))
        self.default_hotkeys: dict[str, str] = config.get("hotkeys", {})
        self.ui_state_path = data_dir / "ui_state.json"
        self.ui_state = self._load_ui_state()
        set_language(self.ui_state.get("language") or installer_language() or system_language())
        self.fallback_sheet = fallback_sheet
        self.sheet_routes = sheet.load_routes(data_dir, fallback_sheet)

        self.events: queue.Queue = queue.Queue()
        self.connected = False
        self.last_sample: tuple[float, float] | None = None
        self.move_mode = False
        self.minimized = False  # hidden until the move hotkey or the tray brings it back; timing goes on
        # The mode of a running game that isn't the Practice Tool (a ranked game...): nothing of it is read
        # and the overlay stays hidden until it ends.
        self.other_game: str | None = None
        # Pop-ups waiting to be shown one at a time, never during a game: ("update", Update) or ("notice", Notice).
        self.popups: list[tuple[str, object]] = []
        self.popup_open = False
        self.settings_window: SettingsWindow | None = None
        # Samples of the current run, replayed into a new tracker when the route changes mid-run.
        self.run_log: list[tuple[float, float, int | None]] = []
        self.detector = StepDetector(self.camp_spawn, self.quiet_window, self.cs_per_camp)
        self.camp_gold = CampGold(data_dir / "camp_gold.json")
        self.auto_detect = bool(config.get("auto_detect_route", True))
        self.route_locked = False
        self.learned_this_run = False
        self.notice: tuple[str, float] | None = None
        self.run_clock = RunClock()
        self.runes: Runes | None = None
        self.sound_cfg = config.get("sounds", {})
        self.sounds = Sounds(data_dir / "sounds", float(self.ui_state.get("sound_volume", self.sound_cfg.get("volume", 0.35))),
                             bool(self.sound_cfg.get("enabled", True)) and not self.ui_state.get("muted", False),
                             self.ui_state.get("sound_theme", self.sound_cfg.get("theme", "suave")),
                             custom_folder=custom_sounds_dir)
        # What the current run has already played, so replays and redraws stay silent.
        self.announced = 0
        self.alerts_played: set = set()
        self._preview_until = 0.0
        self.run_debug_log = RunLog(data_dir / "logs")
        self.closing = False
        self._tick_id: str | None = None  # the next turn of the loop, booked with Tk
        self.update: updater.Update | None = None
        self.updating = False
        # A damaged settings file must not keep the app from opening.
        self.champion = champion_name(self.ui_state.get("champion")) or DEFAULT_CHAMPION
        self.route: Route = self._pick_route()
        self.tracker = self._make_tracker(CS_UNKNOWN)
        self.tray = None

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass
        use_dark_menus()  # the tray icon's menu
        self.root = tk.Tk()
        self.root.title("Jungle Splits")
        if ICON_ICO.exists():
            self.root.iconbitmap(default=str(ICON_ICO))
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        overlay_cfg = config.get("overlay", {})
        self.opaque = opaque
        self.opacity = float(self.ui_state.get("opacity", overlay_cfg.get("opacity", 0.85)))
        self.show = display.normalize(self.ui_state.get("overlay_show"))  # which parts the overlay shows
        self.shown_opacity = self.opacity
        self.renderer = Renderer()
        self.surface = LayeredSurface()
        self._frame_key: tuple | None = None  # what's on screen; an equal frame isn't drawn again
        self.last_image = None
        self.dpi_scale = self.root.winfo_fpixels("1i") / 96
        self._apply_scale(float(self.ui_state.get("scale", overlay_cfg.get("scale", 1.0))))
        self.root.bind("<ButtonPress-1>", self._drag_start)
        self.root.bind("<B1-Motion>", self._drag_move)
        self.root.bind("<ButtonRelease-1>", self._click_release)
        self.root.bind("<Button-3>", self._show_menu)
        self._close_box = self._minimize_box = self._video_box = self._update_box = NO_BOX
        x, y = self.ui_state.get("x", overlay_cfg.get("x", 16)), self.ui_state.get("y", overlay_cfg.get("y", 16))
        # The saved position is the panel's; the window starts a shadow's width further out.
        self.root.geometry(f"+{x - self.margin}+{y - self.margin}")
        self.root.update_idletasks()
        self.hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        self._set_click_through(True)  # also draws the first frame
        self.icon_image = tk.PhotoImage(master=self.root, file=str(ICON_PNG)).subsample(8) if ICON_PNG.exists() else None

        self.hotkeys: HotkeyThread | None = None
        self._start_hotkeys()
        if open_settings:
            self.root.after(300, self._open_settings)

    # --- setup ---------------------------------------------------------------------------------

    def _apply_scale(self, user_scale: float) -> None:
        self.user_scale = user_scale
        self.scale = user_scale * self.dpi_scale
        s = self.scale
        # (face, pixel size); faces are in render.FACES.
        self.fonts = {
            "clock": ("num_bold", round(32 * s)),
            "title": ("ui_semibold", round(14 * s)),
            "small": ("ui", round(11 * s)),
            "label": ("ui_semibold", round(10 * s)),
            "row": ("ui_semibold", round(14 * s)),
            "num": ("num", round(16 * s)),
            "num_bold": ("num_bold", round(16 * s)),
            "verdict": ("ui_bold", round(13 * s)),
        }
        self.margin = round(12 * s)  # around the panel, for its shadow
        self.radius = round(12 * s)
        self._frame_key = None

    def _load_ui_state(self) -> dict:
        try:
            state = json.loads(self.ui_state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return state if isinstance(state, dict) else {}

    def _save_ui_state(self) -> None:
        self.ui_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.ui_state_path.write_text(json.dumps(self.ui_state, indent=2), encoding="utf-8")

    def _per_champion(self, key: str) -> dict:
        return self.ui_state.setdefault(key, {})

    def hotkey_binds(self) -> dict[str, str]:
        return {**self.default_hotkeys, **self.ui_state.get("hotkeys", {})}

    def _start_hotkeys(self) -> None:
        if self.hotkeys:
            self.hotkeys.stop()
        self.hotkeys = HotkeyThread(self.hotkey_binds(), lambda action: self.events.put(("cmd", action)))
        self.hotkeys.start()
        self.hotkeys.wait_ready()

    # --- champion, route and tracker -------------------------------------------------------------

    def smites(self) -> int:
        """1 or 2 smites, as last chosen for this champion (1 until chosen)."""
        return int(self.ui_state.get("smites", {}).get(norm(self.champion), 1))

    def champion_routes(self) -> list[Route]:
        return sheet.routes_for_champion(self.sheet_routes, self.champion, self.smites(),
                                         self.config.get("preferred_routes", {}).get(self.champion),
                                         self.config.get("fallback_routes", []))

    def _pick_route(self) -> Route:
        routes = self.champion_routes()
        chosen = self.ui_state.get("routes", {}).get(norm(self.champion))
        preferred = self.config.get("preferred_routes", {}).get(self.champion)
        for path in (chosen, "->".join(parse_path(preferred)) if preferred else None):
            for route in routes:
                if route.path == path:
                    return route
        return routes[0]

    def target(self) -> float:
        saved = self.ui_state.get("targets", {}).get(norm(self.champion))
        if saved is not None:
            return float(saved)
        targets = self.config.get("targets", {})
        if self.champion in targets:
            return parse_clock(targets[self.champion])
        if self.route.record is not None:
            return self.route.record + float(self.config.get("default_target_margin", 5.0))
        return parse_clock(self.config.get("default_target", "3:00.0"))

    def _make_tracker(self, cs_state: str) -> Tracker:
        path = self.data_dir / slug(self.champion) / f"{slug(self.route.stats_name)}.json"
        tracker = Tracker(RouteStats(path, list(self.route.camps)), self.camp_spawn, self.target(),
                          self.quiet_window, self.cs_per_camp, cs_state)
        for sample in self.run_log:
            tracker.feed(*sample)
        return tracker

    def _replace_tracker(self) -> None:
        """Moves the run in progress to the current route: the old route forgets it, the new one replays it."""
        self.tracker.discard_run()
        self.tracker = self._make_tracker(self.tracker.cs_state)
        self.announced = len(self.tracker.splits)  # the replay re-created splits already heard

    def _select_route(self, route: Route, detected: bool = False) -> None:
        self.route = route
        self._per_champion("routes")[norm(self.champion)] = route.path
        self._save_ui_state()
        self._replace_tracker()
        if detected:
            path = "-".join(camp[:3] for camp in route.camps)
            self.notice = (t("notice_route", path=path), time.perf_counter() + 5.0)
        elif self.tracker.state == RUNNING:
            self.route_locked = True  # picked by hand: don't second-guess it for the rest of the run

    def _set_smites(self, smites: int) -> None:
        """Switches between 1- and 2-smite clears; kept as this champion's default from now on."""
        self._per_champion("smites")[norm(self.champion)] = smites
        self._save_ui_state()
        path = self.route.path
        self.route = next((r for r in self.champion_routes() if r.path == path), None) or self._pick_route()
        self._replace_tracker()
        self.notice = (t("notice_smites", n=smites, champion=self.champion.upper()), time.perf_counter() + 4.0)

    def _set_champion(self, champion: str) -> None:
        champion = champion_name(champion)
        if champion is None:
            return  # not a name: nothing is saved or shown
        self.champion = champion
        self.ui_state["champion"] = champion
        self._save_ui_state()
        self.route = self._pick_route()
        # Another champion means another game: start clean instead of moving the old run over.
        self._new_run_log()
        self.tracker = self._make_tracker(self.tracker.cs_state)

    def _save_debug_log(self) -> None:
        """Saves the attempt's debug log, if it got as far as the camps spawning."""
        if not any(row[1] >= self.camp_spawn for row in self.run_debug_log.rows):
            return
        tr = self.tracker
        info = {"version": __version__, "champion": self.champion, "route": self.route.path,
                "smites": self.smites(), "state": tr.state, "detection": tr.cs_state, "camp_spawn": self.camp_spawn}
        splits = [(camp, s.time, s.gold, s.manual) for camp, s in zip(tr.camps, tr.splits)]
        try:
            self.run_debug_log.save(info, splits)
        except OSError:
            pass  # a debug log must never get in the way of the timer

    def _new_run_log(self) -> None:
        self._save_debug_log()
        self.run_debug_log.clear()
        self.run_log.clear()
        self.detector.reset()
        self.route_locked = False
        self.learned_this_run = False
        self.announced = 0
        self.alerts_played.clear()

    def _on_sample(self, game_time: float, gold: float, cs: int | None) -> None:
        if self.run_log and game_time < self.run_log[-1][0] - 1.0:
            self._new_run_log()  # Practice Tool reset or a new game
        self.run_log.append((game_time, gold, cs))
        step = self.detector.feed(game_time, gold, cs, self.tracker.cs_state)
        if (step and self.auto_detect and not self.route_locked
                and self.tracker.state in (RUNNING, FINISHED)):
            route = best_route(self.detector.steps, self.champion_routes(), self.route, self.camp_gold)
            if route is not None:
                self._select_route(route, detected=True)  # the replay already fed this sample
                return
        state_before = self.tracker.state
        self.tracker.feed(game_time, gold, cs)
        self._play_alerts(game_time, state_before)
        if self.tracker.state == FINISHED and not self.learned_this_run:
            self.learned_this_run = True
            self._save_debug_log()
            camps = self.tracker.camps
            if route_cost(self.detector.steps, camps, self.camp_gold) != float("inf"):
                self.camp_gold.learn(camps, [split.gold for split in self.tracker.splits])

    def _play_alerts(self, now: float, state_before: str) -> None:
        """Sounds for when the eyes are on the clear: countdown to spawn, each camp's sector color,
        a warning once the run can't beat the PB, and a fanfare for a new PB."""
        tr, cfg = self.tracker, self.sound_cfg
        if tr.state == WAITING and cfg.get("countdown", True):
            second = math.ceil(tr.camp_spawn - now)
            if second in (1, 2, 3) and ("tick", second) not in self.alerts_played:
                self.alerts_played.add(("tick", second))
                self.sounds.play("tick")
        if state_before == WAITING and tr.state == RUNNING and cfg.get("countdown", True):
            self.sounds.play("go")
        self.announced = min(self.announced, len(tr.splits))
        while self.announced < len(tr.splits):
            split = tr.splits[self.announced]
            self.announced += 1
            if tr.state == FINISHED and self.announced == len(tr.splits) and tr.new_pb:
                self.sounds.play("pb")
            elif cfg.get("splits", True):
                self.sounds.play(split.color)
        if (tr.state == RUNNING and cfg.get("reset_alert", True) and "reset" not in self.alerts_played
                and tr.verdict(now, self.reset_margin)[0] == "reset"):
            self.alerts_played.add("reset")
            self.sounds.play("reset")

    def _refresh_sheet_in_background(self) -> None:
        if not self.config.get("auto_update_sheet", True) or not sheet.cache_is_stale(self.data_dir):
            return

        def work():
            if sheet.refresh_sheet(self.data_dir):
                self.events.put(("sheet_updated",))

        threading.Thread(target=work, daemon=True).start()

    # --- window behaviour ----------------------------------------------------------------------

    def _set_click_through(self, enabled: bool) -> None:
        self.click_through = enabled
        self._show_opacity(self.opacity)

    def _show_scale(self, user_scale: float) -> None:
        """Resizes the overlay now; Settings calls it while the size slider moves. The panel's top-left
        corner stays where it is (the window around it grows with the shadow's margin)."""
        if user_scale == self.user_scale:
            return
        self.root.update_idletasks()  # a move asked for a moment ago (the last step of a drag) is in place
        x, y = self.root.winfo_x() + self.margin, self.root.winfo_y() + self.margin
        self._apply_scale(user_scale)
        self.root.geometry(f"+{x - self.margin}+{y - self.margin}")
        self._redraw()

    def _show_opacity(self, value: float) -> None:
        """Opacity of the panel's glass; text and sector colors always stay fully opaque."""
        self.shown_opacity = 1.0 if self.opaque else max(0.2, min(value, 1.0))
        # Never Tk's -alpha: it would make the window a constant-alpha one, which can't show per-pixel alpha.
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        style = style | WS_EX_TRANSPARENT if self.click_through else style & ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style)
        self._redraw()

    def _show_parts(self, show: dict) -> None:
        """Shows these parts of the overlay; Settings calls it while the player picks (then on Save or Cancel)."""
        self.show = display.normalize(show)
        self._redraw()

    def _redraw(self) -> None:
        """Draws now even if the frame looks the same (opacity, scale or visibility changed)."""
        self._frame_key = None
        if not self.hidden:
            self._draw()

    def _keep_on_top(self) -> None:
        # Borderless games can push themselves above other topmost windows; re-assert now and then.
        if not self.hidden:
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        self.root.after(2000, self._keep_on_top)

    def _drag_start(self, event) -> None:
        self._drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())
        self._drag_moved = False

    def _drag_move(self, event) -> None:
        if self.move_mode:
            dx, dy = self._drag_offset
            self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")
            self._drag_moved = True

    def _click_release(self, event) -> None:
        # The overlay is one image, so buttons are hit-tested by position, in panel coordinates.
        if not self.move_mode or getattr(self, "_drag_moved", False):
            return
        x, y = event.x - self.margin, event.y - self.margin
        if in_box(self._close_box, x, y):
            self.quit()
        elif in_box(self._minimize_box, x, y):
            self._set_minimized(True)
        elif in_box(self._video_box, x, y):
            self._open_video()
        elif in_box(self._update_box, x, y):
            self._install_update()

    def _set_move_mode(self, on: bool) -> None:
        self.move_mode = on
        self._set_click_through(not on)
        if not on:
            self.ui_state.update(x=self.root.winfo_x() + self.margin, y=self.root.winfo_y() + self.margin)
            self._save_ui_state()
        if self.tray:
            self.tray.refresh()

    def _set_minimized(self, minimized: bool) -> None:
        """Hides the overlay without stopping it (splits, sounds and hotkeys keep working)."""
        if minimized and self.move_mode:
            self._set_move_mode(False)
        self.minimized = minimized
        self._apply_visibility()
        if self.tray:
            self.tray.refresh()

    @property
    def hidden(self) -> bool:
        return self.minimized or self.other_game is not None

    def _apply_visibility(self) -> None:
        if self.hidden:
            self.root.withdraw()
        else:
            self.root.deiconify()
            self._set_click_through(True)
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def _set_other_game(self, mode: str | None) -> None:
        """A game that isn't the Practice Tool started (its mode) or ended (None): the overlay hides for
        as long as it runs, and comes back as the player left it."""
        if mode == self.other_game:
            return
        if mode and self.move_mode:
            self._set_move_mode(False)
        self.other_game = mode
        if mode:
            self.connected = False
        self._apply_visibility()
        if self.tray:
            self.tray.set_title(t("tray_paused", mode=mode) if mode else "Jungle Splits")

    def _open_video(self) -> None:
        open_url(self.route.video, VIDEO_HOSTS)

    def _show_menu(self, event) -> None:
        menu = tk.Menu(self.root, tearoff=0, **menu_colors())
        routes_menu = tk.Menu(menu, tearoff=0, **menu_colors())
        self._route_var = tk.StringVar(master=menu, value=self.route.path)
        for route in self.champion_routes():
            record = f"   {fmt_clock(route.record)[:-2]} {route.player}" if route.record else ""
            routes_menu.add_radiobutton(label=" → ".join(route.camps) + record,
                                        command=lambda r=route: self._select_route(r),
                                        value=route.path, variable=self._route_var)
        menu.add_cascade(label=t("menu_route", champion=self.champion), menu=routes_menu)
        smites_menu = tk.Menu(menu, tearoff=0, **menu_colors())
        self._smites_var = tk.IntVar(master=menu, value=self.smites())
        for n in (1, 2):
            smites_menu.add_radiobutton(label=t("menu_smite_n", n=n), value=n, variable=self._smites_var,
                                        command=lambda n=n: self._set_smites(n))
        menu.add_cascade(label=t("menu_smites", champion=self.champion), menu=smites_menu)
        menu.add_command(label=t("menu_new_run"), command=lambda: self._command("reset"))
        menu.add_command(label=t("menu_video"), command=self._open_video,
                         state="normal" if self.route.video else "disabled")
        menu.add_command(label=t("menu_settings"), command=self._open_settings)
        menu.add_command(label=t("menu_lock"), command=lambda: self._command("move"))
        menu.add_separator()
        menu.add_command(label=t("menu_quit"), command=self.quit)
        menu.tk_popup(event.x_root, event.y_root)

    # --- settings, welcome and tray -----------------------------------------------------------

    def _open_settings(self) -> None:
        if self.settings_window is not None:
            self.settings_window.lift()
            return
        # Pause the hotkeys so typing a new combination doesn't also trigger the old one.
        self.hotkeys.stop()
        saved_target = self.ui_state.get("targets", {}).get(norm(self.champion))
        values = {
            "language": self.ui_state.get("language") or installer_language() or system_language(),
            "champion": self.champion,
            "target": saved_target,
            "smites": self.smites(),
            "scale": self.user_scale,
            "opacity": self.opacity,
            "show": dict(self.show),
            "update_version": self.update.version if self.update else "",
            "binds": self.hotkey_binds(),
            "default_binds": self.default_hotkeys,
            "sound_theme": self.sounds.theme,
            "sound_volume": self.sounds.volume,
        }

        def save(new: dict) -> None:
            self.ui_state.update(language=new["language"], scale=new["scale"], opacity=new["opacity"],
                                 overlay_show=new["show"],
                                 hotkeys=new["binds"], sound_theme=new["sound_theme"],
                                 sound_volume=new["sound_volume"])
            targets = self._per_champion("targets")
            if new["target"] is None:
                targets.pop(norm(self.champion), None)
            else:
                targets[norm(self.champion)] = new["target"]
            self._save_ui_state()
            set_language(new["language"])
            self._show_scale(new["scale"])
            self.opacity = new["opacity"]
            self._show_opacity(self.opacity)
            self._show_parts(new["show"])
            self.sounds.configure(new["sound_theme"], new["sound_volume"])
            self.tracker.target = self.target()
            if new["smites"] != self.smites():
                self._set_smites(new["smites"])
            if self.tray:
                self.tray.refresh()

        def closed() -> None:
            self.settings_window = None
            self._start_hotkeys()

        self.settings_window = SettingsWindow(self.root, values, save, closed, self._preview_sounds,
                                              lambda: os.startfile(self.custom_sounds_dir), self._show_opacity,
                                              self._open_logs, self._install_update, self._records,
                                              self._delete_records, self._show_parts, self.icon_image,
                                              self._show_scale)

    def _records(self) -> list[records.Record]:
        champions = [route.champion for routes in self.sheet_routes.values() for route in routes] + [self.champion]
        return records.list_records(self.data_dir, records.champion_names(champions))

    def _delete_records(self, paths: list[Path]) -> int:
        deleted = records.delete_records(paths)
        current = self.data_dir / slug(self.champion) / f"{slug(self.route.stats_name)}.json"
        if current in paths:
            # Forget the deleted stats held in memory too, or the next attempt would write them back.
            self._new_run_log()
            self.tracker = self._make_tracker(self.tracker.cs_state)
        return deleted

    def _check_for_update_in_background(self) -> None:
        # Only the installed app updates itself; a source checkout updates with git.
        if not FROZEN or not self.config.get("check_updates", True):
            return

        def work():
            update = updater.check_latest()
            if update:
                self.events.put(("update_available", update))

        threading.Thread(target=work, daemon=True).start()

    def _check_notices_in_background(self) -> None:
        if not self.config.get("check_notices", True):
            return

        def work():
            data = notices.fetch_notices()
            if data is not None:
                self.events.put(("notices", data))

        threading.Thread(target=work, daemon=True).start()

    def _show_next_popup(self) -> None:
        """Shows the next waiting pop-up, but not over a game (it would take the focus mid-clear), the
        first-run screen or the settings: it waits until the game is closed."""
        if (self.popup_open or not self.popups or self.connected or self.other_game
                or not self.ui_state.get("welcomed") or self.settings_window is not None):
            return
        kind, item = self.popups.pop(0)
        if kind == "update":
            title = t("update_popup_title", version=item.version)
            text = t("update_popup_text", current=__version__, version=item.version)
            buttons = [(t("update_now"), self._install_update, True), (t("update_later"), None, False),
                       (t("whats_new"), lambda: open_url(item.page_url, GITHUB_HOSTS), False)]
            note = t("update_popup_note")
        else:
            self.ui_state["notices_seen"] = self.ui_state.get("notices_seen", []) + [item.id]
            self._save_ui_state()
            title, text, note = item.title, item.text, ""
            buttons = [(t("popup_ok"), None, True)]
            if item.link:
                buttons.append((item.link_label or t("open_link"), lambda: open_url(item.link), False))
        self.popup_open = True

        def closed() -> None:
            self.popup_open = False

        Popup(self.root, self.icon_image, title, text, buttons, closed, note)

    def _install_update(self) -> None:
        if self.update is None or self.updating:
            return
        if not (INSTALL_DIR / "unins000.exe").exists():
            open_url(self.update.page_url, GITHUB_HOSTS)  # portable copy: the installer would put it elsewhere
            return
        self.updating = True
        self._save_debug_log()

        def work():
            try:
                self.events.put(("update_ready", updater.download(self.update, self.data_dir / "updates")))
            except (OSError, ValueError):
                self.events.put(("update_failed",))

        threading.Thread(target=work, daemon=True).start()

    def _open_logs(self) -> None:
        self._save_debug_log()
        self.run_debug_log.folder.mkdir(parents=True, exist_ok=True)
        os.startfile(self.run_debug_log.folder)

    def _preview_sounds(self, theme: str, volume: float) -> None:
        """Plays every alert of a theme in turn, without touching the saved sounds. Clicks while a
        preview is still playing are ignored, so sequences never pile up on top of each other."""
        if time.perf_counter() < self._preview_until:
            return
        self._preview_until = time.perf_counter() + len(SOUND_NAMES) * 0.7
        preview = Sounds(self.data_dir / "sounds_preview", volume, True, theme, self.custom_sounds_dir)
        for i, name in enumerate(SOUND_NAMES):
            self.root.after(i * 700, lambda n=name: preview.play(n))

    def _show_welcome(self) -> None:
        binds = self.hotkey_binds()

        def done(language: str) -> None:
            self.ui_state.update(language=language, welcomed=True)
            self._save_ui_state()
            if self.tray:
                self.tray.refresh()

        WelcomeWindow(self.root, self.icon_image,
                      {"settings": pretty_combo(binds.get("settings", "")), "move": pretty_combo(binds.get("move", ""))},
                      done)

    def _start_tray(self) -> None:
        try:
            from tray import Tray
        except ImportError:
            return  # running from source without pystray: hotkeys and the right-click menu still work
        self.tray = Tray(ICON_PNG, lambda action: self.events.put(("cmd", action)),
                         lambda: {"move": self.move_mode, "minimized": self.minimized,
                                  "sound": self.sounds.enabled, "video": bool(self.route.video),
                                  "update": self.update.version if self.update else ""})
        self.tray.start()

    # --- loop ----------------------------------------------------------------------------------

    def run(self) -> None:
        self.source.start_feeding(self.events)
        self._refresh_sheet_in_background()
        self._check_for_update_in_background()
        self._check_notices_in_background()
        self._start_tray()
        if not self.ui_state.get("welcomed"):
            self.root.after(400, self._show_welcome)
        self.root.after(0, self._tick)
        self.root.after(2000, self._keep_on_top)
        try:
            self.root.mainloop()
        finally:
            self._save_debug_log()
            self.hotkeys.stop()
            self.surface.close()
            if self.tray:
                self.tray.stop()

    def quit(self) -> None:
        self.closing = True
        if self._tick_id is not None:
            self.root.after_cancel(self._tick_id)
        self.root.destroy()

    def _tick(self) -> None:
        """One turn of the app's loop, 30 times a second. The next turn is booked even if this one fails
        (Tk reports the error), so one bad event can't leave the overlay frozen for good."""
        try:
            self._step()
        finally:
            if not self.closing:
                if self._tick_id is not None:
                    self.root.after_cancel(self._tick_id)  # only ever one turn waiting
                self._tick_id = self.root.after(33, self._tick)

    def _step(self) -> None:
        while not self.closing:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event[0] == "sample":
                sample: Sample = event[1]
                self._set_other_game(None)
                self.connected = True
                if sample.champion and sample.champion != self.champion:
                    self._set_champion(sample.champion)
                self.runes = sample.runes or self.runes
                run_time = self.run_clock.run_time(sample.game_time, sample.gold, sample.level, sample.items)
                self.last_sample = (run_time, sample.received)
                self._on_sample(run_time, sample.gold, sample.cs)
                self.run_debug_log.add(sample.game_time, run_time, sample.gold, sample.cs, sample.level,
                                       sample.items)
            elif event[0] == "offline":
                self.connected = False
                self._set_other_game(None)
            elif event[0] == "other_game":
                self._set_other_game(event[1])
            elif event[0] == "update_available":
                self.update = event[1]
                self.popups.append(("update", self.update))
                if self.tray:
                    self.tray.refresh()
            elif event[0] == "notices":
                seen = set(self.ui_state.get("notices_seen", []))
                for notice in notices.parse_notices(event[1], __version__, language(), seen, date.today()):
                    self.popups.append(("notice", notice))
            elif event[0] == "update_ready":
                updater.run_installer(event[1])
                self.quit()
            elif event[0] == "update_failed":
                self.updating = False
                self.notice = (t("update_failed"), time.perf_counter() + 6.0)
                open_url(self.update.page_url, GITHUB_HOSTS)
            elif event[0] == "sheet_updated":
                self.sheet_routes = sheet.load_routes(self.data_dir, self.fallback_sheet)
                route = self._pick_route()
                moved = route.path != self.route.path
                self.route = route  # same path may come with a newer record
                if moved:
                    self._replace_tracker()
            elif event[0] == "cmd":
                self._command(event[1])
        if self.closing:
            return  # an event closed the app (quit, update): the window is gone
        self._show_next_popup()
        if not self.hidden:
            self._draw()  # builds the frame; draws only if it differs from the one on screen

    def _command(self, action: str) -> None:
        if action == "split":
            self.tracker.manual_split()
        elif action == "undo":
            self.tracker.undo()
        elif action == "reset":
            # Same as a Practice Tool reset the overlay didn't catch: a new attempt starts at 0:00 now.
            self.run_clock.restart()
        elif action == "next_route":
            routes = self.champion_routes()
            index = next((i for i, r in enumerate(routes) if r.path == self.route.path), -1)
            self._select_route(routes[(index + 1) % len(routes)])
        elif action == "smites":
            self._set_smites(2 if self.smites() == 1 else 1)
        elif action == "move":
            if self.other_game:
                pass  # hidden for a game that isn't the Practice Tool: nothing to move
            elif self.minimized:
                self._set_minimized(False)  # the move hotkey brings a minimized overlay back
            else:
                self._set_move_mode(not self.move_mode)
        elif action == "show":
            self._set_minimized(False)
        elif action == "settings":
            self._open_settings()
        elif action == "video":
            self._open_video()
        elif action == "logs":
            self._open_logs()
        elif action == "update":
            self._install_update()
        elif action == "mute":
            self.sounds.enabled = not self.sounds.enabled
            self.ui_state["muted"] = not self.sounds.enabled
            self._save_ui_state()
            self.notice = (t("notice_sound_on" if self.sounds.enabled else "notice_sound_off"),
                           time.perf_counter() + 3.0)
            if self.tray:
                self.tray.refresh()
        elif action == "quit":
            self.quit()

    def _now(self) -> float | None:
        if not self.connected or self.last_sample is None:
            return None
        game_time, received = self.last_sample
        return game_time + min(time.perf_counter() - received, INTERPOLATE_MAX)

    # --- drawing -------------------------------------------------------------------------------

    def _fit(self, text: str, font_key: str, max_width: int) -> tuple[str, int]:
        """The font for text, shrunk until the text fits in max_width pixels."""
        face, size = self.fonts[font_key]
        while size > 8 and self.renderer.measure(text, face, size) > max_width:
            size -= 1
        return face, size

    def _text_width(self, text: str, font: tuple[str, int]) -> float:
        return self.renderer.measure(text, *font)

    def _draw(self) -> None:
        """Builds the frame and puts it on screen, unless it is the frame already there."""
        s = self.scale
        f = self.fonts
        tr = self.tracker
        now = self._now()

        width = round(340 * s)
        pad = round(12 * s)
        inset = round(6 * s)  # rows and boxes sit this far inside the panel's edges
        row_h = round(27 * s)
        x_time = round(196 * s)
        x_delta = round(256 * s)
        pill_l, pill_r = round(264 * s), width - pad
        small_r = round(6 * s)
        fr = Frame(width)

        show = self.show
        compact = display.clock_only(show)
        if tr.state == FINISHED:
            clock, clock_color = tr.total(), SECTOR[PURPLE] if tr.new_pb else (
                DELTA_AHEAD if tr.total() <= tr.target else TEXT)
        else:
            clock, clock_color = now, TEXT if tr.state == RUNNING else MUTED
        delta = tr.current_delta(now) if show["delta"] else None
        if compact:
            # Just the clock: a small panel as wide as the clock needs (its digits all take the same width).
            clock_w = max(self._text_width(fmt_clock(clock), f["clock"]), self._text_width("0:00.0", f["clock"]))
            width = max(round(170 * s), round(clock_w) + 2 * pad)
            fr = Frame(width)

        stripe = max(2, round(3 * s))  # the brand stripe is part of the panel (render.Renderer.panel)
        head = stripe
        self._close_box = self._minimize_box = NO_BOX
        if self.move_mode:
            # Title bar with close and minimize buttons, only while the overlay can be clicked.
            bar = round(26 * s)
            top = head + round(4 * s)
            fr.rect(inset, top, width - inset, top + bar, SOFT, small_r)
            button = bar - round(6 * s)
            gap = round(3 * s)
            self._close_box = (width - inset - gap - button, top + gap, width - inset - gap, top + gap + button)
            fr.rect(*self._close_box, SECTOR["red"], round(5 * s))
            fr.text((self._close_box[0] + self._close_box[2]) // 2, top + bar // 2, "✕", "#ffffff",
                    ("symbol", round(12 * s)))
            self._minimize_box = (self._close_box[0] - gap - button, top + gap, self._close_box[0] - gap,
                                  top + gap + button)
            fr.rect(*self._minimize_box, (255, 255, 255, 40), round(5 * s))
            fr.text((self._minimize_box[0] + self._minimize_box[2]) // 2, top + bar // 2, "–", "#ffffff", f["row"])
            fr.text(pad, top + bar // 2, t("move_bar"), AMBER,
                    self._fit(t("move_bar"), "label", self._minimize_box[0] - pad - gap), "w")
            head = top + bar

        delta_text = f"{fmt_delta(delta)} PB" if delta is not None else ""
        delta_color = DELTA_AHEAD if delta is not None and delta <= 0 else DELTA_BEHIND
        if compact:
            fr.text(width // 2, head + round(4 * s), fmt_clock(clock), clock_color, f["clock"], "n")
            y = head + round(46 * s)
            if delta is not None:
                fr.text(width // 2, y, delta_text, delta_color, f["num_bold"], "n")
            if show["delta"]:
                y += round(22 * s)
            fr.height = y + round(6 * s)
            if self.move_mode:
                fr.outline(0, 0, width, fr.height, AMBER, max(2, round(2 * s)), self.radius)
            self._video_box = self._update_box = NO_BOX
            self._present(fr)
            return

        if show["header"]:
            # Header: champion, the sheet record, the game clock and the overall delta to the PB.
            fr.text(pad, head + round(10 * s), self.champion.upper(), TEXT, f["title"], "nw")
            smite_tag = t("smite_tag", n=self.smites())
            if self.route.record is not None:
                reference = t("record_line", time=fmt_clock(self.route.record)[:-2], player=self.route.player,
                              patch=self.route.patch) + f" · {smite_tag}"
            else:
                reference = f"{t('custom_route')} · {smite_tag}"
            fr.text(pad, head + round(30 * s), reference, MUTED,
                    self._fit(reference, "small", width - 2 * pad - round(118 * s)), "nw")
            fr.text(width - pad, head + round(4 * s), fmt_clock(clock), clock_color, f["clock"], "ne")
            if delta is not None:
                fr.text(width - pad, head + round(38 * s), delta_text, delta_color, f["num_bold"], "ne")
            y = head + round(60 * s)
        else:
            # No header: the clock on the left, its delta on the right.
            fr.text(pad, head + round(4 * s), fmt_clock(clock), clock_color, f["clock"], "nw")
            if delta is not None:
                fr.text(width - pad, head + round(24 * s), delta_text, delta_color, f["num_bold"], "e")
            y = head + round(48 * s)

        if show["info"]:
            sob = tr.sum_of_best()
            info = t("info_line", pb=fmt_clock(tr.stats.pb[-1]) if tr.stats.pb else "-", target=fmt_clock(tr.target))
            if sob is not None:
                info += t("sum_of_best", time=fmt_clock(sob))
            fr.text(pad, y, info, MUTED, self._fit(info, "small", width - 2 * pad), "nw")
            y += round(22 * s)

        if show["camps"]:
            for key, x, anchor in (("col_camp", pad + round(10 * s), "nw"), ("col_time", x_time, "ne"),
                                   ("col_delta", x_delta, "ne"), ("col_sector", (pill_l + pill_r) // 2, "n")):
                fr.text(x, y, t(key).upper(), MUTED, f["label"], anchor)
            y += round(17 * s)

            current = len(tr.splits) if tr.state == RUNNING else -1
            pb = tr.stats.pb
            pb_segs = tr.pb_segments()
            for i, camp in enumerate(tr.camps):
                top, bottom = y + i * row_h, y + (i + 1) * row_h - 1
                mid = (top + bottom) // 2
                bg = ROW_CURRENT if i == current else (ROW_ALT if i % 2 else None)
                if bg:
                    fr.rect(inset, top, width - inset, bottom, bg, small_r)
                split = tr.splits[i] if i < len(tr.splits) else None
                bar = SECTOR[split.color] if split else (AMBER if i == current else SOFT)
                fr.rect(pad - round(3 * s), top + round(5 * s), pad, bottom - round(5 * s), bar, round(2 * s))
                label = camp
                if i == current and tr.cs_state == CS_OK and not tr.is_recall(i):
                    label += f"  {tr.seg_cs}/{tr.cs_per_camp}"
                fr.text(pad + round(10 * s), mid, label, TEXT if split or i == current else MUTED,
                        self._fit(label, "row", x_time - pad - round(80 * s)), "w")

                pill = (pill_l, top + round(4 * s), pill_r, bottom - round(4 * s))
                if split:
                    fr.text(x_time, mid, fmt_clock(split.time), TEXT, f["num"], "e")
                    if split.total_delta is not None:
                        fr.text(x_delta, mid, fmt_delta(split.total_delta),
                                DELTA_AHEAD if split.total_delta <= 0 else DELTA_BEHIND, f["num"], "e")
                    pill_text = fmt_delta(split.segment_delta) if split.segment_delta is not None else f"{split.segment:.1f}"
                    fr.rect(*pill, SECTOR[split.color], small_r)
                    fr.text((pill_l + pill_r) // 2, mid, pill_text, "#ffffff", f["num_bold"])
                    continue

                if pb:
                    fr.text(x_time, mid, fmt_clock(pb[i]), MUTED, f["num"], "e")
                if i == current and now is not None:
                    live = tr.live_total_delta(now)
                    if live is not None:
                        fr.text(x_delta, mid, fmt_delta(live), DELTA_BEHIND, f["num"], "e")
                    elapsed = now - (tr.splits[-1].time if tr.splits else tr.camp_spawn)
                    losing = pb_segs is not None and elapsed > pb_segs[i]
                    fr.rect(*pill, SOFT, small_r)
                    fr.text((pill_l + pill_r) // 2, mid, f"{max(0.0, elapsed):.1f}", DELTA_BEHIND if losing else TEXT,
                            f["num_bold"])

            y += len(tr.camps) * row_h + round(8 * s)
        if show["verdict"]:
            text, color = self._verdict_text(now)
            box_h = round(30 * s)
            fr.rect(inset, y, width - inset, y + box_h, rgba(color, 30), round(8 * s))
            fr.outline(inset, y, width - inset, y + box_h, rgba(color, 200), max(1, round(1.5 * s)), round(8 * s))
            fr.text(width // 2, y + box_h // 2, text, color,
                    self._fit(text, "verdict", width - 2 * pad - round(12 * s)))
            y += box_h + round(8 * s)

        # The footer's lines; move mode keeps its instructions and the update line even with the footer off.
        footer_shown = show["footer"] or self.move_mode
        if show["runes"] and self.runes is not None and self.connected:
            # Rune shards next to the record's, as the sheet notes them (e.g. AS/AD/HPS).
            mine = t("runes", runes=self.runes.shards + (f" · {self.runes.keystone}" if self.runes.keystone else ""))
            same = bool(self.route.shards) and self.runes.shards.startswith(self.route.shards)
            record = t("record_shards", shards=self.route.shards) if self.route.shards else ""
            record_font = self._fit(record, "small", width // 2)
            record_w = self._text_width(record, record_font)
            fr.text(pad, y, mine, DELTA_AHEAD if same else TEXT,
                    self._fit(mine, "small", width - 2 * pad - record_w - round(10 * s)), "nw")
            fr.text(width - pad, y, record, MUTED, record_font, "ne")
            y += round(18 * s)

        self._update_box = NO_BOX
        if self.update and footer_shown:
            key = "updating" if self.updating else ("update_click" if self.move_mode else "update_available")
            text = t(key, version=self.update.version)
            update_font = self._fit(text, "small", width - 2 * pad)
            fr.text(pad, y, text, AMBER, update_font, "nw")
            self._update_box = (pad, y, pad + round(self._text_width(text, update_font)), y + round(16 * s))
            y += round(18 * s)

        self._video_box = NO_BOX
        if show["video"] and self.route.video:
            video = t("video_click" if self.move_mode else "video", player=self.route.player)
            video_font = self._fit(video, "small", width - 2 * pad)
            fr.text(pad, y, video, LINK, video_font, "nw")
            self._video_box = (pad, y, pad + round(self._text_width(video, video_font)), y + round(16 * s))
            y += round(18 * s)

        if footer_shown:
            notice = self.notice if self.notice and time.perf_counter() < self.notice[1] else None
            if self.move_mode:
                footer = t("move_footer", key=pretty_combo(self.hotkey_binds().get("move", "")) or "-")
            elif notice:
                footer = notice[0]
            elif not self.connected:
                footer = t("footer_offline", key=pretty_combo(self.hotkey_binds().get("settings", "")) or "-")
            else:
                mode = {CS_OK: "mode_cs", CS_UNKNOWN: "mode_both"}.get(tr.cs_state, "mode_gold")
                footer = t("footer_stats", attempts=tr.stats.attempts, completed=tr.stats.completed, mode=t(mode))
                if not self.sounds.enabled:
                    footer += t("sound_off_tag")
            fr.text(pad, y, footer, AMBER if self.move_mode or notice else MUTED,
                    self._fit(footer, "small", width - 2 * pad), "nw")
            y += round(18 * s)
        fr.height = y + round(6 * s)
        if self.move_mode:
            fr.outline(0, 0, width, fr.height, AMBER, max(2, round(2 * s)), self.radius)
        self._present(fr)

    def _present(self, fr: Frame) -> None:
        key = (fr.key(), self.shown_opacity, self.margin, self.radius)
        if key == self._frame_key:
            return  # same as on screen: nothing to draw
        self._frame_key = key
        stripe = max(2, round(3 * self.scale))
        panel = self.renderer.panel(fr.width, fr.height, self.shown_opacity, self.radius, self.margin, BG,
                                    (SECTOR[PURPLE], SECTOR["green"], SECTOR["red"]), stripe)
        image = self.renderer.render(fr, panel, self.margin)
        self.last_image = image
        if (self.root.winfo_width(), self.root.winfo_height()) != image.size:
            self.root.geometry(f"{image.width}x{image.height}")
        self.surface.present(self.hwnd, image)

    def _verdict_text(self, now: float | None) -> tuple[str, str]:
        tr = self.tracker
        if not self.connected:
            return t("waiting_game"), MUTED
        if tr.state == WAITING:
            return t("spawn_in", time=fmt_clock(tr.camp_spawn - (now or 0))), MUTED
        if tr.state == ABANDONED:
            return t("abandoned"), MUTED
        if tr.state == FINISHED:
            total = tr.total()
            if tr.new_pb:
                return t("new_pb", time=fmt_clock(total)), SECTOR[PURPLE]
            if total <= tr.target:
                return t("target_hit", time=fmt_clock(total)), DELTA_AHEAD
            return t("final", time=fmt_clock(total), delta=fmt_delta(total - tr.stats.pb[-1])), TEXT
        verdict, pace, best = tr.verdict(now, self.reset_margin)
        if verdict == "reset":
            return t("v_reset", time=fmt_clock(best)), DELTA_BEHIND
        if verdict == "on_target":
            return t("v_on_target", time=fmt_clock(pace)), SECTOR[PURPLE]
        if verdict == "ahead":
            return t("v_ahead", time=fmt_clock(pace)), DELTA_AHEAD
        if verdict == "behind":
            best_text = t("best_suffix", time=fmt_clock(best)) if best is not None else ""
            return t("v_behind", best=best_text), AMBER
        return t("first_run_route"), MUTED
