"""A message window in the app's style: a new version to install, or a notice published on GitHub."""
from __future__ import annotations

import tkinter as tk

from settings_window import ACCENT, BG, MUTED, PANEL, TEXT

SECTORS = ("#a63dff", "#1fc85f", "#e8333a")


class Popup(tk.Toplevel):
    def __init__(self, master, icon_image, title: str, text: str, buttons: list[tuple[str, object, bool]],
                 on_close, note: str = ""):
        """buttons: (label, action, primary) from right to left, each closing the window after its action;
        on_close() runs once the window is gone, whichever way it closed."""
        super().__init__(master)
        self.on_close = on_close
        self.title(title)
        self.configure(bg=BG, padx=28, pady=22)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._close)

        head = tk.Frame(self, bg=BG)
        head.pack(fill="x")
        if icon_image is not None:
            tk.Label(head, image=icon_image, bg=BG).pack(side="left", padx=(0, 16))
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left")
        tk.Label(titles, text=title, bg=BG, fg=TEXT, font=("Segoe UI Semibold", 16), justify="left",
                 wraplength=380).pack(anchor="w")
        stripe = tk.Frame(titles, bg=BG)
        stripe.pack(anchor="w", pady=(8, 0))
        for color in SECTORS:
            tk.Frame(stripe, bg=color, width=40, height=4).pack(side="left", padx=(0, 6))

        tk.Label(self, text=text, bg=BG, fg=TEXT, font=("Segoe UI", 11), justify="left", wraplength=460).pack(
            anchor="w", pady=(18, 0))
        if note:
            tk.Label(self, text=note, bg=BG, fg=MUTED, font=("Segoe UI", 9), justify="left", wraplength=460).pack(
                anchor="w", pady=(8, 0))

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", pady=(22, 0))
        for label, action, primary in buttons:
            tk.Button(bar, text=label, command=lambda a=action: self._click(a), relief="flat", bd=0, padx=18, pady=6,
                      bg=ACCENT if primary else PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=TEXT,
                      font=("Segoe UI Semibold", 10), takefocus=0).pack(side="right", padx=(8, 0))

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _click(self, action) -> None:
        self._close()
        if action is not None:
            action()

    def _close(self) -> None:
        if self.winfo_exists():
            self.destroy()
            self.on_close()
