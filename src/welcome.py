"""First-run screen: pick the language and learn the basics in a few lines."""
from __future__ import annotations

import tkinter as tk

from i18n import LANGUAGES, language, set_language, t
from ui import BG, FONT, FONT_LABEL, MUTED, Button, Card, Segmented, label, px, stripe, style_window


class WelcomeWindow(tk.Toplevel):
    def __init__(self, master, icon_image, hotkeys: dict[str, str], on_done):
        """hotkeys holds the readable 'settings' and 'move' combos; on_done(language) runs on close."""
        super().__init__(master)
        self.icon_image = icon_image
        self.hotkeys = hotkeys
        self.on_done = on_done
        self.configure(bg=BG, padx=px(self, 28), pady=px(self, 24))
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._done)
        self.language = tk.StringVar(self, value=language())
        self._build()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")
        style_window(self)
        self.after(50, self.focus_force)

    def _build(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self.title(t("welcome_title"))
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x")
        if self.icon_image is not None:
            tk.Label(head, image=self.icon_image, bg=BG).pack(side="left", padx=(0, px(self, 16)))
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left")
        label(titles, t("welcome_title"), ("Segoe UI Semibold", 18)).pack(anchor="w")
        label(titles, t("welcome_subtitle"), FONT_LABEL, MUTED).pack(anchor="w")
        stripe(titles, 46, 5).pack(anchor="w", pady=(px(self, 8), 0))

        Segmented(self, self.language, list(LANGUAGES.items()), self._pick, padx=16).pack(
            anchor="w", pady=(px(self, 20), 0))

        card = Card(self)
        card.pack(fill="x", pady=(px(self, 16), 0))
        label(card.body, t("welcome_steps"), FONT_LABEL).pack(anchor="w")
        label(card.body, t("welcome_colors"), FONT, MUTED).pack(anchor="w", pady=(px(self, 12), 0))
        label(card.body, t("welcome_keys", **self.hotkeys), FONT, MUTED).pack(anchor="w", pady=(px(self, 2), 0))
        Button(self, t("welcome_start"), self._done, "primary", font=("Segoe UI Semibold", 11), padx=26).pack(
            anchor="e", pady=(px(self, 20), 0))

    def _pick(self) -> None:
        set_language(self.language.get())
        self._build()

    def _done(self) -> None:
        self.destroy()
        self.on_done(language())
