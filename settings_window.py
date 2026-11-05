"""Settings window: language, target, smites and overlay size; hotkeys; sounds; about."""
from __future__ import annotations

import tkinter as tk
import webbrowser

from hotkeys import MODIFIER_VKS, combo_from_vk, has_modifier, pretty_combo
from i18n import LANGUAGES, language, set_language, t
from sound import THEMES
from tracker import fmt_clock, parse_clock
from version import GITHUB_URL, SHEET_VIEW_URL, __version__

ACTIONS = ["split", "undo", "reset", "next_route", "smites", "move", "settings", "mute", "quit"]
VK_ESCAPE = 0x1B

BG, PANEL, PANEL_HI, TEXT, MUTED, ACCENT, WARN = ("#0e1014", "#1a1e26", "#262b36", "#eef0f3", "#7d8697",
                                                  "#a63dff", "#ffb020")
FONT = ("Segoe UI", 10)
FONT_LABEL = ("Segoe UI", 11)
FONT_HEAD = ("Segoe UI Semibold", 15)


def parse_target(text: str) -> float | None:
    """'2:50' -> 170.0; raises ValueError for anything that isn't m:ss."""
    text = text.strip()
    if not text:
        return None
    if ":" not in text:
        raise ValueError(text)
    seconds = parse_clock(text)
    if not 30 <= seconds <= 900:
        raise ValueError(text)
    return seconds


class SettingsWindow(tk.Toplevel):
    def __init__(self, master, values: dict, on_save, on_close, on_preview, on_open_sounds, on_opacity,
                 on_open_logs, on_update=None):
        """values: language, champion, target (seconds or None), smites, scale, opacity, binds, default_binds,
        sound_theme, sound_volume. on_save receives the same keys with the new values; on_opacity(value)
        previews an opacity while the slider moves."""
        super().__init__(master)
        self.values = dict(values)
        self.on_save, self.on_close = on_save, on_close
        self.on_preview, self.on_open_sounds, self.on_opacity = on_preview, on_open_sounds, on_opacity
        self.on_open_logs = on_open_logs
        self.on_update = on_update
        self.binds = {a: values["binds"].get(a, "") for a in ACTIONS}
        self.capturing: str | None = None
        self.tab = "general"
        self.original_language = language()
        self.configure(bg=BG, padx=18, pady=16)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<KeyPress>", self._key)
        self.language = tk.StringVar(self, value=values["language"])
        self.target = tk.StringVar(self, value=fmt_clock(values["target"])[:-2] if values["target"] else "")
        self.smites = tk.IntVar(self, value=values["smites"])
        self.scale = tk.IntVar(self, value=round(values["scale"] * 100))
        self.opacity = tk.IntVar(self, value=round(values["opacity"] * 100))
        self.theme = tk.StringVar(self, value=values["sound_theme"])
        self.volume = tk.IntVar(self, value=round(values["sound_volume"] * 100))
        self._build()
        self.after(50, self.focus_force)

    # --- layout ------------------------------------------------------------------------------

    def _build(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self.title(t("settings_title"))
        tabs = tk.Frame(self, bg=BG)
        tabs.pack(fill="x", pady=(0, 14))
        for key in ("general", "hotkeys", "sounds", "about"):
            active = key == self.tab
            tk.Button(tabs, text=t(f"tab_{key}"), command=lambda k=key: self._show_tab(k), relief="flat",
                      bg=ACCENT if active else PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=TEXT,
                      font=("Segoe UI Semibold", 10), padx=14, pady=5, takefocus=0, bd=0).pack(side="left", padx=(0, 6))
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        getattr(self, f"_tab_{self.tab}")(body)
        self.status = tk.Label(self, text="", bg=BG, fg=WARN, font=FONT, wraplength=440, justify="left")
        self.status.pack(fill="x", pady=(10, 0))
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", pady=(12, 0))
        tk.Label(bar, text=t("version", version=__version__), bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        for text, command, color in ((t("save"), self._save, ACCENT), (t("cancel"), self._cancel, PANEL)):
            self._button(bar, text, command, color).pack(side="right", padx=(8, 0))

    def _show_tab(self, tab: str) -> None:
        self.tab = tab
        self.capturing = None
        self._build()

    def _button(self, parent, text, command, color=PANEL):
        return tk.Button(parent, text=text, command=command, bg=color, fg=TEXT, relief="flat", bd=0, padx=14, pady=5,
                         activebackground=ACCENT, activeforeground=TEXT, font=("Segoe UI Semibold", 10), takefocus=0)

    def _row(self, parent, row: int, label: str, widget_factory, hint: str = "") -> None:
        tk.Label(parent, text=label, bg=BG, fg=TEXT, font=FONT_LABEL, anchor="w").grid(
            row=row * 2, column=0, sticky="w", pady=(6, 0), padx=(0, 18))
        widget_factory(parent).grid(row=row * 2, column=1, sticky="w", pady=(6, 0))
        if hint:
            tk.Label(parent, text=hint, bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=420, justify="left").grid(
                row=row * 2 + 1, column=0, columnspan=2, sticky="w")

    def _choices(self, parent, variable, options: list[tuple[object, str]], on_change=None):
        frame = tk.Frame(parent, bg=BG)
        for value, label in options:
            def pick(v=value):
                variable.set(v)
                if on_change:
                    on_change()
                else:
                    self._build()
            selected = variable.get() == value
            tk.Button(frame, text=label, command=pick, relief="flat", bd=0, padx=12, pady=4, takefocus=0,
                      bg=ACCENT if selected else PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=TEXT,
                      font=FONT).pack(side="left", padx=(0, 6))
        return frame

    # --- tabs --------------------------------------------------------------------------------

    def _tab_general(self, body) -> None:
        champion = self.values["champion"]

        def change_language():
            set_language(self.language.get())
            self._build()

        self._row(body, 0, t("language"),
                  lambda p: self._choices(p, self.language, list(LANGUAGES.items()), change_language))
        self._row(body, 1, t("target_for", champion=champion),
                  lambda p: tk.Entry(p, textvariable=self.target, width=8, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                                     relief="flat", font=("Consolas", 13)),
                  t("target_hint"))
        self._row(body, 2, t("smites_for", champion=champion),
                  lambda p: self._choices(p, self.smites, [(1, "1 smite"), (2, "2 smites")]), t("smites_hint"))
        self._row(body, 3, t("overlay_size"),
                  lambda p: tk.Scale(p, from_=70, to=160, resolution=10, orient="horizontal", variable=self.scale,
                                     bg=BG, fg=TEXT, troughcolor=PANEL, highlightthickness=0, length=200,
                                     activebackground=ACCENT, takefocus=0))
        self._row(body, 4, t("overlay_opacity"),
                  lambda p: tk.Scale(p, from_=30, to=100, resolution=5, orient="horizontal", variable=self.opacity,
                                     bg=BG, fg=TEXT, troughcolor=PANEL, highlightthickness=0, length=200,
                                     activebackground=ACCENT, takefocus=0,
                                     command=lambda v: self.on_opacity(float(v) / 100)),
                  t("opacity_hint"))

    def _tab_hotkeys(self, body) -> None:
        tk.Label(body, text=t("hotkeys_hint"), bg=BG, fg=MUTED, font=FONT).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.hotkey_buttons: dict[str, tk.Button] = {}
        for row, action in enumerate(ACTIONS, start=1):
            tk.Label(body, text=t(f"act_{action}"), bg=BG, fg=TEXT, font=FONT_LABEL, anchor="w").grid(
                row=row, column=0, sticky="we", pady=3, padx=(0, 16))
            button = tk.Button(body, width=20, bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=TEXT,
                               relief="flat", bd=0, font=("Consolas", 11, "bold"), takefocus=0, pady=3,
                               command=lambda a=action: self._start_capture(a))
            button.grid(row=row, column=1, pady=3)
            self.hotkey_buttons[action] = button
        self._button(body, t("restore"), self._restore_binds).grid(row=len(ACTIONS) + 1, column=1, sticky="e",
                                                                   pady=(10, 0))
        self._refresh_binds()

    def _tab_sounds(self, body) -> None:
        themes = [(key, t(f"theme_{key}")) for key in THEMES]
        self._row(body, 0, t("sound_style"), lambda p: self._choices(p, self.theme, themes))
        self._row(body, 1, t("sound_volume"),
                  lambda p: tk.Scale(p, from_=0, to=100, orient="horizontal", variable=self.volume, bg=BG, fg=TEXT,
                                     troughcolor=PANEL, highlightthickness=0, activebackground=ACCENT, length=200,
                                     takefocus=0))
        self._row(body, 2, "", lambda p: self._button(
            p, t("sound_test"), lambda: self.on_preview(self.theme.get(), self.volume.get() / 100)))
        self._row(body, 3, "", lambda p: self._button(p, t("open_sounds_folder"), self.on_open_sounds),
                  t("sound_custom"))

    def _tab_about(self, body) -> None:
        tk.Label(body, text="Jungle Splits", bg=BG, fg=TEXT, font=FONT_HEAD).pack(anchor="w")
        tk.Label(body, text=t("about_text"), bg=BG, fg=TEXT, font=FONT, justify="left", wraplength=440).pack(
            anchor="w", pady=(4, 10))
        links = tk.Frame(body, bg=BG)
        links.pack(anchor="w")
        self._button(links, t("open_github"), lambda: webbrowser.open(GITHUB_URL)).pack(side="left", padx=(0, 8))
        self._button(links, t("open_sheet"), lambda: webbrowser.open(SHEET_VIEW_URL)).pack(side="left")
        if self.values.get("update_version") and self.on_update:
            self._button(body, t("menu_update", version=self.values["update_version"]), self._update,
                         ACCENT).pack(anchor="w", pady=(10, 0))
        self._button(body, t("open_logs"), self.on_open_logs).pack(anchor="w", pady=(10, 0))
        tk.Label(body, text=t("logs_hint"), bg=BG, fg=MUTED, font=("Segoe UI", 9), justify="left",
                 wraplength=440).pack(anchor="w", pady=(4, 0))
        tk.Label(body, text=t("disclaimer"), bg=BG, fg=MUTED, font=("Segoe UI", 8), justify="left",
                 wraplength=440).pack(anchor="w", pady=(14, 0))

    # --- hotkey capture ----------------------------------------------------------------------

    def _refresh_binds(self) -> None:
        for action, button in getattr(self, "hotkey_buttons", {}).items():
            if action == self.capturing:
                button.configure(text=t("press_keys"), fg=WARN)
            else:
                button.configure(text=pretty_combo(self.binds[action]) or t("none"), fg=TEXT)

    def _start_capture(self, action: str) -> None:
        self.capturing = action
        self.status.configure(text="")
        self._refresh_binds()
        self.focus_force()

    def _key(self, event) -> None:
        if self.capturing is None or event.keycode in MODIFIER_VKS:
            return
        action, self.capturing = self.capturing, None
        if event.keycode == VK_ESCAPE:
            self._refresh_binds()
            return
        combo = combo_from_vk(event.keycode)
        notes = []
        for other, other_combo in self.binds.items():
            if other != action and other_combo.lower() == combo.lower():
                self.binds[other] = ""
                notes.append(t("hotkey_moved", key=pretty_combo(combo), action=t(f"act_{other}")))
        if not has_modifier(combo):
            notes.append(t("hotkey_no_modifier", key=pretty_combo(combo)))
        self.binds[action] = combo
        self.status.configure(text=" ".join(notes))
        self._refresh_binds()

    def _restore_binds(self) -> None:
        self.binds = {a: self.values["default_binds"].get(a, "") for a in ACTIONS}
        self.capturing = None
        self._refresh_binds()

    # --- closing -----------------------------------------------------------------------------

    def _save(self) -> None:
        try:
            target = parse_target(self.target.get())
        except ValueError:
            self.tab = "general"
            self._build()
            self.status.configure(text=t("target_invalid"))
            return
        self.on_save({
            "language": self.language.get(),
            "target": target,
            "smites": self.smites.get(),
            "scale": self.scale.get() / 100,
            "opacity": self.opacity.get() / 100,
            "binds": dict(self.binds),
            "sound_theme": self.theme.get(),
            "sound_volume": self.volume.get() / 100,
        })
        self.destroy()
        self.on_close()

    def _update(self) -> None:
        self._cancel()
        self.on_update()

    def _cancel(self) -> None:
        set_language(self.original_language)
        self.on_opacity(self.values["opacity"])
        self.destroy()
        self.on_close()
