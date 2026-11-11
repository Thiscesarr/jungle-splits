"""A message window in the app's style: a new version to install, a notice published on GitHub, or a
question before something that can't be undone."""
from __future__ import annotations

import tkinter as tk

from ui import BG, FONT_LABEL, FONT_SMALL, MUTED, Button, Card, label, px, stripe, style_window


class Popup(tk.Toplevel):
    def __init__(self, master, icon_image, title: str, text: str, buttons: list[tuple[str, object, bool | str]],
                 on_close, note: str = ""):
        """buttons: (label, action, kind) from right to left, each closing the window after its action; kind is
        True for the main button, False for the others, or a ui.KINDS name ("danger"). on_close() runs once
        the window is gone, whichever way it closed."""
        super().__init__(master)
        self.on_close = on_close
        self.title(title)
        self.configure(bg=BG, padx=px(self, 26), pady=px(self, 22))
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._close)

        head = tk.Frame(self, bg=BG)
        head.pack(fill="x")
        if icon_image is not None:
            tk.Label(head, image=icon_image, bg=BG).pack(side="left", padx=(0, px(self, 14)))
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left")
        label(titles, title, ("Segoe UI Semibold", 15), wrap=380).pack(anchor="w")
        stripe(titles, 36, 4).pack(anchor="w", pady=(px(self, 8), 0))

        card = Card(self, padx=18, pady=14)
        card.pack(fill="x", pady=(px(self, 18), 0))
        label(card.body, text, FONT_LABEL, wrap=430).pack(anchor="w")
        if note:
            label(card.body, note, FONT_SMALL, MUTED, wrap=430).pack(anchor="w", pady=(px(self, 8), 0))

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", pady=(px(self, 18), 0))
        self.buttons = []
        for text_, action, kind in buttons:
            kind = {True: "primary", False: "secondary"}.get(kind, kind)
            button = Button(bar, text_, lambda a=action: self._click(a), kind, padx=18)
            button.pack(side="right", padx=(px(self, 8), 0))
            self.buttons.append(button)

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")
        style_window(self)

    def _click(self, action) -> None:
        self._close()
        if action is not None:
            action()

    def _close(self) -> None:
        if self.winfo_exists():
            self.destroy()
            self.on_close()
