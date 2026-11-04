"""Always-on-top, click-through split overlay drawn with tkinter."""
from __future__ import annotations

import ctypes
import json
import math
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

import sheet
from binds import BindsWindow
from detect import CampGold, StepDetector, best_route, route_cost
from hotkeys import HotkeyThread, pretty_combo
from sheet import Route, norm, parse_path
from sound import SOUND_NAMES, Sounds
from sources import Runes, Sample
from tracker import (ABANDONED, CS_OK, CS_UNKNOWN, FINISHED, PURPLE, RUNNING, WAITING, RouteStats, RunClock,
                     Tracker, fmt_clock, fmt_delta, parse_clock, slug)

user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x20, 0x80, 0x80000, 0x8000000
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10

BG = "#0e1014"
ROW_ALT = "#14171d"
ROW_CURRENT = "#1e2430"
DIVIDER = "#262b36"
TEXT = "#eef0f3"
MUTED = "#7d8697"
AMBER = "#ffb020"
SECTOR = {PURPLE: "#a63dff", "green": "#1fc85f", "red": "#e8333a"}
DELTA_AHEAD, DELTA_BEHIND = "#3ee07a", "#ff5a5f"

INTERPOLATE_MAX = 0.15
DEFAULT_CHAMPION = "Lee Sin"


class App:
    def __init__(self, config: dict, data_dir: Path, source, fallback_sheet: Path, open_binds: bool = False):
        self.config = config
        self.data_dir = data_dir
        self.source = source
        self.camp_spawn = parse_clock(config.get("camp_spawn", "0:55"))
        self.quiet_window = float(config.get("quiet_window", 2.0))
        self.cs_per_camp = int(config.get("cs_per_camp", 4))
        self.default_hotkeys: dict[str, str] = config.get("hotkeys", {})
        self.ui_state_path = data_dir / "ui_state.json"
        self.ui_state = self._load_ui_state()
        self.fallback_sheet = fallback_sheet
        self.sheet_routes = sheet.load_routes(data_dir, fallback_sheet)

        self.events: queue.Queue = queue.Queue()
        self.connected = False
        self.last_sample: tuple[float, float] | None = None
        self.move_mode = False
        self.binds_window: BindsWindow | None = None
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
        self.reset_margin = float(config.get("reset_margin", 2.0))
        sound_cfg = config.get("sounds", {})
        self.sound_cfg = sound_cfg
        self.sounds = Sounds(data_dir / "sounds", float(self.ui_state.get("sound_volume", sound_cfg.get("volume", 0.35))),
                             bool(sound_cfg.get("enabled", True)) and not self.ui_state.get("muted", False),
                             self.ui_state.get("sound_theme", sound_cfg.get("theme", "suave")),
                             custom_folder=data_dir.parent / "sons")
        # What the current run has already played, so replays and redraws stay silent.
        self.announced = 0
        self.alerts_played: set = set()
        self._preview_until = 0.0
        self.champion = self.ui_state.get("champion", DEFAULT_CHAMPION)
        self.route: Route = self._pick_route()
        self.tracker = self._make_tracker(CS_UNKNOWN)

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass
        self.root = tk.Tk()
        self.root.title("Jungle Splits")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        overlay_cfg = config.get("overlay", {})
        self.opacity = float(overlay_cfg.get("opacity", 0.9))
        self.scale = float(overlay_cfg.get("scale", 1.0)) * self.root.winfo_fpixels("1i") / 96
        self.canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._click_release)
        self._close_box = (0, 0, 0, 0)
        self.canvas.bind("<Button-3>", self._show_menu)
        self.fonts = self._make_fonts()
        self._font_cache: dict[tuple, tkfont.Font] = {}
        x, y = self.ui_state.get("x", overlay_cfg.get("x", 24)), self.ui_state.get("y", overlay_cfg.get("y", 240))
        self.root.geometry(f"+{x}+{y}")
        self.root.update_idletasks()
        self.hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        self._set_click_through(True)

        self.hotkeys: HotkeyThread | None = None
        self._start_hotkeys()
        if open_binds:
            self.root.after(300, self._open_binds)

    # --- setup ---------------------------------------------------------------------------------

    def _make_fonts(self) -> dict:
        s = self.scale
        return {
            "clock": ("Consolas", -round(30 * s), "bold"),
            "title": ("Segoe UI Semibold", -round(14 * s)),
            "small": ("Segoe UI", -round(11 * s)),
            "label": ("Segoe UI Semibold", -round(10 * s)),
            "row": ("Segoe UI Semibold", -round(14 * s)),
            "num": ("Consolas", -round(15 * s)),
            "num_bold": ("Consolas", -round(15 * s), "bold"),
            "verdict": ("Segoe UI", -round(13 * s), "bold"),
        }

    def _load_ui_state(self) -> dict:
        try:
            return json.loads(self.ui_state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_ui_state(self) -> None:
        self.ui_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.ui_state_path.write_text(json.dumps(self.ui_state, indent=2), encoding="utf-8")

    def hotkey_binds(self) -> dict[str, str]:
        return {**self.default_hotkeys, **self.ui_state.get("hotkeys", {})}

    def _start_hotkeys(self) -> None:
        if self.hotkeys:
            self.hotkeys.stop()
        self.hotkeys = HotkeyThread(self.hotkey_binds(), lambda action: self.events.put(("cmd", action)))
        self.hotkeys.start()
        self.hotkeys.wait_ready()
        if self.hotkeys.failed:
            print("Atalhos que não puderam ser registrados (em uso ou inválidos):", ", ".join(self.hotkeys.failed))

    # --- champion, route and tracker -------------------------------------------------------------

    def champion_routes(self) -> list[Route]:
        """Sheet routes for the champion, plus the configured preferred route if the sheet lacks it."""
        routes = list(self.sheet_routes.get(norm(self.champion), []))
        preferred = self.config.get("preferred_routes", {}).get(self.champion)
        if preferred and all(r.camps != parse_path(preferred) for r in routes):
            routes.insert(0, Route(self.champion, parse_path(preferred)))
        if not routes:
            routes = [Route(self.champion, parse_path(p)) for p in self.config.get("fallback_routes", [])]
        return routes

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
        targets = self.config.get("targets", {})
        if self.champion in targets:
            return parse_clock(targets[self.champion])
        if self.route.record is not None:
            return self.route.record + float(self.config.get("default_target_margin", 5.0))
        return parse_clock(self.config.get("default_target", "3:00.0"))

    def _make_tracker(self, cs_state: str) -> Tracker:
        path = self.data_dir / slug(self.champion) / f"{slug(self.route.path)}.json"
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
        self.ui_state.setdefault("routes", {})[norm(self.champion)] = route.path
        self._save_ui_state()
        self._replace_tracker()
        if detected:
            path = "-".join(camp[:3] for camp in route.camps)
            self.notice = (f"ROTA DETECTADA: {path}", time.perf_counter() + 5.0)
        elif self.tracker.state == RUNNING:
            self.route_locked = True  # picked by hand: don't second-guess it for the rest of the run

    def _set_champion(self, champion: str) -> None:
        self.champion = champion
        self.ui_state["champion"] = champion
        self._save_ui_state()
        self.route = self._pick_route()
        # Another champion means another game: start clean instead of moving the old run over.
        self._new_run_log()
        self.tracker = self._make_tracker(self.tracker.cs_state)

    def _new_run_log(self) -> None:
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
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        style = style | WS_EX_TRANSPARENT if enabled else style & ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style)
        self.root.attributes("-alpha", self.opacity)

    def _keep_on_top(self) -> None:
        # Borderless games can push themselves above other topmost windows; re-assert now and then.
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        self.root.after(2000, self._keep_on_top)

    def _drag_start(self, event) -> None:
        self._drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _click_release(self, event) -> None:
        # The canvas is redrawn every frame, so hit-test the close button by position, not by item.
        left, top, right, bottom = self._close_box
        if self.move_mode and left <= event.x <= right and top <= event.y <= bottom:
            self.quit()

    def _drag_move(self, event) -> None:
        if self.move_mode:
            dx, dy = self._drag_offset
            self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def _show_menu(self, event) -> None:
        menu = tk.Menu(self.root, tearoff=0)
        routes_menu = tk.Menu(menu, tearoff=0)
        self._route_var = tk.StringVar(master=menu, value=self.route.path)
        for route in self.champion_routes():
            record = f"   {fmt_clock(route.record)[:-2]} {route.player}" if route.record else ""
            routes_menu.add_radiobutton(label=" → ".join(route.camps) + record,
                                        command=lambda r=route: self._select_route(r),
                                        value=route.path, variable=self._route_var)
        menu.add_cascade(label=f"Rota ({self.champion})", menu=routes_menu)
        menu.add_command(label="Nova run (zera o relógio agora)", command=lambda: self._command("reset"))
        menu.add_command(label="Atalhos e sons…", command=self._open_binds)
        menu.add_command(label="Travar posição", command=lambda: self._command("move"))
        menu.add_separator()
        menu.add_command(label="Fechar overlay", command=self.quit)
        menu.tk_popup(event.x_root, event.y_root)

    def _open_binds(self) -> None:
        if self.binds_window is not None:
            self.binds_window.lift()
            return
        # Pause the hotkeys so typing a new combination doesn't also trigger the old one.
        self.hotkeys.stop()

        def save(binds, sound):
            self.ui_state["hotkeys"] = binds
            self.ui_state["sound_theme"], self.ui_state["sound_volume"] = sound["theme"], sound["volume"]
            self._save_ui_state()
            self.sounds.configure(sound["theme"], sound["volume"])

        def closed():
            self.binds_window = None
            self._start_hotkeys()

        self.binds_window = BindsWindow(self.root, self.hotkey_binds(), self.default_hotkeys,
                                        {"theme": self.sounds.theme, "volume": self.sounds.volume},
                                        save, closed, self._preview_sounds)

    def _preview_sounds(self, theme: str, volume: float) -> None:
        """Plays every alert of a theme in turn, without touching the saved sounds. Clicks while a
        preview is still playing are ignored, so sequences never pile up on top of each other."""
        if time.perf_counter() < self._preview_until:
            return
        self._preview_until = time.perf_counter() + len(SOUND_NAMES) * 0.7
        preview = Sounds(self.data_dir / "sounds_preview", volume, True, theme, self.data_dir.parent / "sons")
        for i, name in enumerate(SOUND_NAMES):
            self.root.after(i * 700, lambda n=name: preview.play(n))

    # --- loop ----------------------------------------------------------------------------------

    def run(self) -> None:
        self.source.start_feeding(self.events)
        self._refresh_sheet_in_background()
        self.root.after(0, self._tick)
        self.root.after(2000, self._keep_on_top)
        try:
            self.root.mainloop()
        finally:
            self.hotkeys.stop()

    def quit(self) -> None:
        self.root.destroy()

    def _tick(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event[0] == "sample":
                sample: Sample = event[1]
                self.connected = True
                if sample.champion and sample.champion != self.champion:
                    self._set_champion(sample.champion)
                self.runes = sample.runes or self.runes
                run_time = self.run_clock.run_time(sample.game_time, sample.gold, sample.level, sample.items)
                self.last_sample = (run_time, sample.received)
                self._on_sample(run_time, sample.gold, sample.cs)
            elif event[0] == "offline":
                self.connected = False
            elif event[0] == "sheet_updated":
                self.sheet_routes = sheet.load_routes(self.data_dir, self.fallback_sheet)
                route = self._pick_route()
                moved = route.path != self.route.path
                self.route = route  # same path may come with a newer record
                if moved:
                    self._replace_tracker()
            elif event[0] == "cmd":
                self._command(event[1])
        self._draw()
        self.root.after(33, self._tick)

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
        elif action == "move":
            self.move_mode = not self.move_mode
            self._set_click_through(not self.move_mode)
            if not self.move_mode:
                self.ui_state.update(x=self.root.winfo_x(), y=self.root.winfo_y())
                self._save_ui_state()
        elif action == "settings":
            self._open_binds()
        elif action == "mute":
            self.sounds.enabled = not self.sounds.enabled
            self.ui_state["muted"] = not self.sounds.enabled
            self._save_ui_state()
            self.notice = ("SOM LIGADO" if self.sounds.enabled else "SOM DESLIGADO", time.perf_counter() + 3.0)
        elif action == "quit":
            self.quit()

    def _now(self) -> float | None:
        if not self.connected or self.last_sample is None:
            return None
        game_time, received = self.last_sample
        return game_time + min(time.perf_counter() - received, INTERPOLATE_MAX)

    # --- drawing -------------------------------------------------------------------------------

    def _fit(self, text: str, font_key: str, max_width: int) -> tuple:
        """The font for text, shrunk until the text fits in max_width pixels."""
        family, size, *style = self.fonts[font_key]
        while True:
            key = (family, size, *style)
            if key not in self._font_cache:
                self._font_cache[key] = tkfont.Font(root=self.root, family=family, size=size,
                                                    weight="bold" if "bold" in style else "normal")
            if self._font_cache[key].measure(text) <= max_width or size >= -8:
                return key
            size += 1  # sizes are negative pixel heights

    def _draw(self) -> None:
        s = self.scale
        c = self.canvas
        f = self.fonts
        tr = self.tracker
        now = self._now()
        c.delete("all")

        width = round(340 * s)
        pad = round(12 * s)
        row_h = round(27 * s)
        x_time = round(196 * s)
        x_delta = round(256 * s)
        pill_l, pill_r = round(264 * s), width - pad

        top = 0
        if self.move_mode:
            # Title bar with a close button, like a window tab, only while the overlay can be clicked.
            top = round(26 * s)
            c.create_rectangle(0, 0, width, top, fill=DIVIDER, width=0)
            c.create_text(pad, top // 2, anchor="w", text="ARRASTE PARA MOVER", fill=AMBER, font=f["label"])
            self._close_box = (width - top, 0, width, top)
            c.create_rectangle(*self._close_box, fill=SECTOR["red"], width=0)
            c.create_text(width - top // 2, top // 2, text="✕", fill="#ffffff", font=f["row"])

        # Header: champion, the sheet record, the game clock and the overall delta to the PB.
        c.create_text(pad, top + round(12 * s), anchor="nw", text=self.champion.upper(), fill=TEXT, font=f["title"])
        if self.route.record is not None:
            reference = f"RECORDE {fmt_clock(self.route.record)[:-2]} · {self.route.player} · {self.route.patch}"
        else:
            reference = "ROTA PERSONALIZADA"
        c.create_text(pad, top + round(32 * s), anchor="nw", fill=MUTED, text=reference,
                      font=self._fit(reference, "small", width - 2 * pad - round(118 * s)))
        if tr.state == FINISHED:
            clock, clock_color = tr.total(), SECTOR[PURPLE] if tr.new_pb else (
                DELTA_AHEAD if tr.total() <= tr.target else TEXT)
        else:
            clock, clock_color = now, TEXT if tr.state == RUNNING else MUTED
        c.create_text(width - pad, top + round(4 * s), anchor="ne", text=fmt_clock(clock), fill=clock_color,
                      font=f["clock"])
        delta = tr.current_delta(now)
        if delta is not None:
            c.create_text(width - pad, top + round(38 * s), anchor="ne", text=f"{fmt_delta(delta)} PB",
                          fill=DELTA_AHEAD if delta <= 0 else DELTA_BEHIND, font=f["num_bold"])

        y = top + round(60 * s)
        sob = tr.sum_of_best()
        info = f"PB {fmt_clock(tr.stats.pb[-1]) if tr.stats.pb else '-'}    META {fmt_clock(tr.target)}"
        if sob is not None:
            info += f"    SOMA MELHORES {fmt_clock(sob)}"
        c.create_text(pad, y, anchor="nw", text=info, fill=MUTED, font=self._fit(info, "small", width - 2 * pad))

        y += round(22 * s)
        for text, x, anchor in (("CAMPO", pad + round(10 * s), "nw"), ("TEMPO", x_time, "ne"),
                                ("Δ PB", x_delta, "ne"), ("SETOR", (pill_l + pill_r) // 2, "n")):
            c.create_text(x, y, anchor=anchor, text=text, fill=MUTED, font=f["label"])
        y += round(16 * s)

        current = len(tr.splits) if tr.state == RUNNING else -1
        pb = tr.stats.pb
        pb_segs = tr.pb_segments()
        for i, camp in enumerate(tr.camps):
            top, bottom = y + i * row_h, y + (i + 1) * row_h - 1
            mid = (top + bottom) // 2
            bg = ROW_CURRENT if i == current else (ROW_ALT if i % 2 else BG)
            c.create_rectangle(0, top, width, bottom, fill=bg, width=0)
            split = tr.splits[i] if i < len(tr.splits) else None
            bar = SECTOR[split.color] if split else (AMBER if i == current else DIVIDER)
            c.create_rectangle(pad - round(4 * s), top + 3, pad, bottom - 3, fill=bar, width=0)
            label = camp
            if i == current and tr.cs_state == CS_OK and not tr.is_recall(i):
                label += f"  {tr.seg_cs}/{tr.cs_per_camp}"
            c.create_text(pad + round(10 * s), mid, anchor="w", text=label,
                          font=self._fit(label, "row", x_time - pad - round(80 * s)),
                          fill=TEXT if split or i == current else MUTED)

            if split:
                c.create_text(x_time, mid, anchor="e", text=fmt_clock(split.time), fill=TEXT, font=f["num"])
                if split.total_delta is not None:
                    c.create_text(x_delta, mid, anchor="e", text=fmt_delta(split.total_delta), font=f["num"],
                                  fill=DELTA_AHEAD if split.total_delta <= 0 else DELTA_BEHIND)
                pill_text = fmt_delta(split.segment_delta) if split.segment_delta is not None else f"{split.segment:.1f}"
                c.create_rectangle(pill_l, top + 3, pill_r, bottom - 3, fill=SECTOR[split.color], width=0)
                c.create_text((pill_l + pill_r) // 2, mid, text=pill_text, fill="#ffffff", font=f["num_bold"])
                continue

            if pb:
                c.create_text(x_time, mid, anchor="e", text=fmt_clock(pb[i]), fill=MUTED, font=f["num"])
            if i == current and now is not None:
                live = tr.live_total_delta(now)
                if live is not None:
                    c.create_text(x_delta, mid, anchor="e", text=fmt_delta(live), fill=DELTA_BEHIND, font=f["num"])
                elapsed = now - (tr.splits[-1].time if tr.splits else tr.camp_spawn)
                losing = pb_segs is not None and elapsed > pb_segs[i]
                c.create_rectangle(pill_l, top + 3, pill_r, bottom - 3, fill=DIVIDER, width=0)
                c.create_text((pill_l + pill_r) // 2, mid, text=f"{max(0.0, elapsed):.1f}", font=f["num_bold"],
                              fill=DELTA_BEHIND if losing else TEXT)

        y += len(tr.camps) * row_h + round(8 * s)
        text, color = self._verdict_text(now)
        box_h = round(30 * s)
        c.create_rectangle(pad, y, width - pad, y + box_h, fill=BG, outline=color, width=max(1, round(2 * s)))
        c.create_text(width // 2, y + box_h // 2, text=text, fill=color,
                      font=self._fit(text, "verdict", width - 2 * pad - round(12 * s)))
        y += box_h + round(6 * s)

        if self.runes is not None and self.connected:
            # Rune shards next to the record's, as the sheet notes them (e.g. AS/AD/HPS).
            mine = self.runes.shards + (f" · {self.runes.keystone}" if self.runes.keystone else "")
            same = bool(self.route.shards) and self.runes.shards.startswith(self.route.shards)
            record = f"recorde {self.route.shards}" if self.route.shards else ""
            record_font = self._fit(record, "small", width // 2)
            record_w = self._font_cache[record_font].measure(record)
            c.create_text(pad, y, anchor="nw", text=f"RUNAS {mine}", fill=DELTA_AHEAD if same else TEXT,
                          font=self._fit(f"RUNAS {mine}", "small", width - 2 * pad - record_w - round(10 * s)))
            c.create_text(width - pad, y, anchor="ne", text=record, fill=MUTED, font=record_font)
            y += round(18 * s)

        notice = self.notice if self.notice and time.perf_counter() < self.notice[1] else None
        if self.move_mode:
            footer = "MODO MOVER: arraste · botão direito: rotas, atalhos, fechar"
        elif notice:
            footer = notice[0]
        elif not self.connected:
            footer = f"Atalhos: {pretty_combo(self.hotkey_binds().get('settings', '')) or 'botão direito no modo mover'}"
        else:
            detection = {CS_OK: "CS", CS_UNKNOWN: "CS/ouro"}.get(tr.cs_state, "ouro")
            footer = f"Tentativas {tr.stats.attempts} · Completas {tr.stats.completed} · fecha por {detection}"
            if not self.sounds.enabled:
                footer += " · som off"
        c.create_text(pad, y, anchor="nw", text=footer, fill=AMBER if self.move_mode or notice else MUTED,
                      font=self._fit(footer, "small", width - 2 * pad))
        height = y + round(22 * s)

        if self.move_mode:
            c.create_rectangle(1, 1, width - 2, height - 2, outline=AMBER, width=2)
        if (self.root.winfo_width(), self.root.winfo_height()) != (width, height):
            self.root.geometry(f"{width}x{height}")

    def _verdict_text(self, now: float | None) -> tuple[str, str]:
        tr = self.tracker
        if not self.connected:
            return "Aguardando o Practice Tool", MUTED
        if tr.state == WAITING:
            remaining = tr.camp_spawn - (now or 0)
            return f"Campos nascem em {fmt_clock(remaining)}", MUTED
        if tr.state == ABANDONED:
            return "Run descartada · Reset Game para outra", MUTED
        if tr.state == FINISHED:
            total = tr.total()
            if tr.new_pb:
                return f"NOVO PB!  {fmt_clock(total)}", SECTOR[PURPLE]
            if total <= tr.target:
                return f"META BATIDA  {fmt_clock(total)}", DELTA_AHEAD
            return f"FINAL {fmt_clock(total)}  ({fmt_delta(total - tr.stats.pb[-1])} PB)", TEXT
        verdict, pace, best = tr.verdict(now, self.reset_margin)
        if verdict == "reset":
            return f"RESET · não bate o PB (melhor possível {fmt_clock(best)})", DELTA_BEHIND
        if verdict == "on_target":
            return f"NO RITMO DA META · projeção {fmt_clock(pace)}", SECTOR[PURPLE]
        if verdict == "ahead":
            return f"À FRENTE DO PB · projeção {fmt_clock(pace)}", DELTA_AHEAD
        if verdict == "behind":
            best_text = f" · melhor possível {fmt_clock(best)}" if best is not None else ""
            return f"ATRÁS DO PB · ainda dá{best_text}", AMBER
        return "Primeira run da rota · gravando referência", MUTED
