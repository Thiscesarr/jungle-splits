"""First-run screen: pick the language and learn the basics in a few lines."""
from __future__ import annotations

import tkinter as tk

from i18n import LANGUAGES, language, set_language, t
from settings_window import ACCENT, BG, MUTED, PANEL, TEXT

SECTORS = ("#a63dff", "#1fc85f", "#e8333a")


class WelcomeWindow(tk.Toplevel):
    def __init__(self, master, icon_image, hotkeys: dict[str, str], on_done):
        """hotkeys holds the readable 'settings' and 'move' combos; on_done(language) runs on close."""
        super().__init__(master)
        self.icon_image = icon_image
        self.hotkeys = hotkeys
        self.on_done = on_done
        self.configure(bg=BG, padx=28, pady=24)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._done)
        self._build()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")
        self.after(50, self.focus_force)

    def _build(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self.title(t("welcome_title"))
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x")
        if self.icon_image is not None:
            tk.Label(head, image=self.icon_image, bg=BG).pack(side="left", padx=(0, 16))
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left")
        tk.Label(titles, text=t("welcome_title"), bg=BG, fg=TEXT, font=("Segoe UI Semibold", 18)).pack(anchor="w")
        tk.Label(titles, text=t("welcome_subtitle"), bg=BG, fg=MUTED, font=("Segoe UI", 11)).pack(anchor="w")
        stripe = tk.Frame(titles, bg=BG)
        stripe.pack(anchor="w", pady=(8, 0))
        for color in SECTORS:
            tk.Frame(stripe, bg=color, width=46, height=5).pack(side="left", padx=(0, 6))

        langs = tk.Frame(self, bg=BG)
        langs.pack(fill="x", pady=(20, 0))
        for code, name in LANGUAGES.items():
            selected = code == language()
            tk.Button(langs, text=name, command=lambda c=code: self._pick(c), relief="flat", bd=0, padx=16, pady=6,
                      bg=ACCENT if selected else PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=TEXT,
                      font=("Segoe UI Semibold", 10), takefocus=0).pack(side="left", padx=(0, 8))

        tk.Label(self, text=t("welcome_steps"), bg=BG, fg=TEXT, font=("Segoe UI", 11), justify="left").pack(
            anchor="w", pady=(20, 0))
        tk.Label(self, text=t("welcome_colors"), bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(14, 0))
        tk.Label(self, text=t("welcome_keys", **self.hotkeys), bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(
            anchor="w", pady=(4, 0))
        tk.Button(self, text=t("welcome_start"), command=self._done, relief="flat", bd=0, padx=26, pady=7,
                  bg=ACCENT, fg=TEXT, activebackground=ACCENT, activeforeground=TEXT,
                  font=("Segoe UI Semibold", 11), takefocus=0).pack(anchor="e", pady=(22, 0))

    def _pick(self, code: str) -> None:
        set_language(code)
        self._build()

    def _done(self) -> None:
        self.destroy()
        self.on_done(language())
