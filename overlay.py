"""Always-on-top, click-through split overlay drawn with tkinter."""
from __future__ import annotations

import ctypes
import json
import queue
import time
import tkinter as tk
from pathlib import Path

from hotkeys import HotkeyThread
from tracker import (ABANDONED, FINISHED, GREEN, PURPLE, RED, RUNNING, WAITING, RouteStats, Tracker,
                     fmt_clock, fmt_delta, parse_clock, slug)

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
SECTOR = {PURPLE: "#a63dff", GREEN: "#1fc85f", RED: "#e8333a"}
DELTA_AHEAD, DELTA_BEHIND = "#3ee07a", "#ff5a5f"

INTERPOLATE_MAX = 0.15


class App:
    def __init__(self, config: dict, data_dir: Path, source):
        self.config = config
        self.data_dir = data_dir
        self.source = source
        self.camp_spawn = parse_clock(config.get("camp_spawn", "1:30"))
        self.target = parse_clock(config.get("target", "2:50.0"))
        self.quiet_window = float(config.get("quiet_window", 2.0))
        self.routes: dict[str, list[str]] = config["routes"]
        self.ui_state_path = data_dir / "ui_state.json"
        self.ui_state = self._load_ui_state()
        self.route = self.ui_state.get("route") if self.ui_state.get("route") in self.routes else next(iter(self.routes))
        self.events: queue.Queue = queue.Queue()
        self.connected = False
        self.last_sample: tuple[float, float] | None = None
        self.last_gold = 0.0
        self.move_mode = False
        self.tracker = self._make_tracker()

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
        self.canvas.bind("<Button-3>", lambda _e: self.move_mode and self.quit())
        self.fonts = self._make_fonts()
        x, y = self.ui_state.get("x", overlay_cfg.get("x", 24)), self.ui_state.get("y", overlay_cfg.get("y", 240))
        self.root.geometry(f"+{x}+{y}")
        self.root.update_idletasks()
        self.hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        self._set_click_through(True)

        self.hotkeys = HotkeyThread(config.get("hotkeys", {}), lambda action: self.events.put(("cmd", action)))
        self.hotkeys.start()
        self.hotkeys.wait_ready()
        if self.hotkeys.failed:
            print("Atalhos que não puderam ser registrados (em uso ou inválidos):", ", ".join(self.hotkeys.failed))

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

    def _make_tracker(self) -> Tracker:
        stats = RouteStats(self.data_dir / f"{slug(self.route)}.json", self.routes[self.route])
        tracker = Tracker(stats, self.camp_spawn, self.target, self.quiet_window)
        if self.last_sample is not None:
            tracker.feed(self.last_sample[0], self.last_gold)
        return tracker

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

    def _drag_move(self, event) -> None:
        if self.move_mode:
            dx, dy = self._drag_offset
            self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    # --- loop ----------------------------------------------------------------------------------

    def run(self) -> None:
        self.source.start_feeding(self.events)
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
                _, game_time, gold, received = event
                self.connected = True
                self.last_sample = (game_time, received)
                self.last_gold = gold
                self.tracker.feed(game_time, gold)
            elif event[0] == "offline":
                self.connected = False
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
            self.tracker.reset()
        elif action == "next_route":
            names = list(self.routes)
            self.route = names[(names.index(self.route) + 1) % len(names)]
            self.ui_state["route"] = self.route
            self._save_ui_state()
            self.tracker = self._make_tracker()
        elif action == "move":
            self.move_mode = not self.move_mode
            self._set_click_through(not self.move_mode)
            if not self.move_mode:
                self.ui_state.update(x=self.root.winfo_x(), y=self.root.winfo_y())
                self._save_ui_state()
        elif action == "quit":
            self.quit()

    def _now(self) -> float | None:
        if not self.connected or self.last_sample is None:
            return None
        game_time, received = self.last_sample
        return game_time + min(time.perf_counter() - received, INTERPOLATE_MAX)

    # --- drawing -------------------------------------------------------------------------------

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

        # Header: route and the game clock.
        c.create_text(pad, round(12 * s), anchor="nw", text=self.route.upper(), fill=TEXT, font=f["title"])
        c.create_text(pad, round(32 * s), anchor="nw", fill=MUTED, font=f["small"],
                      text=self.source.label if self.connected else "SEM PARTIDA")
        if tr.state == FINISHED:
            clock, clock_color = tr.total(), SECTOR[PURPLE] if tr.new_pb else (
                DELTA_AHEAD if tr.total() <= self.target else TEXT)
        else:
            clock, clock_color = now, TEXT if tr.state == RUNNING else MUTED
        c.create_text(width - pad, round(6 * s), anchor="ne", text=fmt_clock(clock), fill=clock_color, font=f["clock"])

        y = round(54 * s)
        sob = tr.sum_of_best()
        info = f"PB {fmt_clock(tr.stats.pb[-1]) if tr.stats.pb else '-'}    META {fmt_clock(self.target)}"
        if sob is not None:
            info += f"    SOMA MELHORES {fmt_clock(sob)}"
        c.create_text(pad, y, anchor="nw", text=info, fill=MUTED, font=f["small"])

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
            c.create_text(pad + round(10 * s), mid, anchor="w", text=camp, font=f["row"],
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
        c.create_text(width // 2, y + box_h // 2, text=text, fill=color, font=f["verdict"])
        y += box_h + round(6 * s)

        footer = f"Tentativas {tr.stats.attempts} · Completas {tr.stats.completed}"
        if self.move_mode:
            footer = "MODO MOVER: arraste · tecla de mover trava · botão direito fecha"
        c.create_text(pad, y, anchor="nw", text=footer, fill=AMBER if self.move_mode else MUTED, font=f["small"])
        height = y + round(22 * s)

        if self.move_mode:
            c.create_rectangle(1, 1, width - 2, height - 2, outline=AMBER, width=2)
        if (self.root.winfo_width(), self.root.winfo_height()) != (width, height):
            self.root.geometry(f"{width}x{height}")

    def _verdict_text(self, now: float | None) -> tuple[str, str]:
        tr = self.tracker
        if not self.connected:
            return "Aguardando partida (Practice Tool, modo sem bordas)", MUTED
        if tr.state == WAITING:
            remaining = tr.camp_spawn - (now or 0)
            return f"Campos nascem em {fmt_clock(remaining)}", MUTED
        if tr.state == ABANDONED:
            return "Run descartada · resete o jogo para começar outra", MUTED
        if tr.state == FINISHED:
            total = tr.total()
            if tr.new_pb:
                return f"NOVO PB!  {fmt_clock(total)}", SECTOR[PURPLE]
            if total <= self.target:
                return f"META BATIDA  {fmt_clock(total)}", DELTA_AHEAD
            return f"FINAL {fmt_clock(total)}  ({fmt_delta(total - tr.stats.pb[-1])} PB)", TEXT
        verdict, pace, best = tr.verdict(now)
        if verdict == "reset":
            return f"RESET · melhor possível {fmt_clock(best)}", DELTA_BEHIND
        if verdict == "on_pace":
            return f"NO RITMO DA META · projeção {fmt_clock(pace)}", DELTA_AHEAD
        if verdict == "possible":
            extra = f" · proj. {fmt_clock(pace)}" if pace is not None else ""
            return f"AINDA DÁ · melhor possível {fmt_clock(best)}{extra}", AMBER
        if tr.stats.pb is None:
            return "Primeira run da rota · gravando referência", MUTED
        return "Em andamento", MUTED
