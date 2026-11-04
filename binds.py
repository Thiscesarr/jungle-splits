"""Window to rebind the overlay hotkeys by pressing the new key combination."""
from __future__ import annotations

import tkinter as tk

from hotkeys import MODIFIER_VKS, combo_from_vk, has_modifier, pretty_combo

ACTION_LABELS = {
    "split": "Fechar campo na mão",
    "undo": "Desfazer último campo",
    "reset": "Nova run (zera o relógio agora)",
    "next_route": "Próxima rota do campeão",
    "move": "Mover overlay (liga/desliga)",
    "settings": "Abrir esta janela",
    "mute": "Ligar/desligar sons",
    "quit": "Fechar o app",
}
VK_ESCAPE = 0x1B

BG, PANEL, TEXT, MUTED, ACCENT, WARN = "#0e1014", "#1a1e26", "#eef0f3", "#7d8697", "#a63dff", "#ffb020"


class BindsWindow(tk.Toplevel):
    def __init__(self, master, binds: dict[str, str], defaults: dict[str, str], on_save, on_close):
        super().__init__(master)
        self.binds = {action: binds.get(action, "") for action in ACTION_LABELS}
        self.defaults = defaults
        self.on_save = on_save
        self.on_close = on_close
        self.capturing: str | None = None
        self.title("Jungle Splits · Atalhos")
        self.configure(bg=BG, padx=16, pady=14)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<KeyPress>", self._key)

        tk.Label(self, text="Clique em um atalho e aperte a nova combinação (Esc cancela).",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.buttons: dict[str, tk.Button] = {}
        for row, (action, label) in enumerate(ACTION_LABELS.items(), start=1):
            tk.Label(self, text=label, bg=BG, fg=TEXT, font=("Segoe UI", 11), anchor="w").grid(
                row=row, column=0, sticky="we", pady=3, padx=(0, 16))
            button = tk.Button(self, width=20, bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=TEXT,
                               relief="flat", font=("Consolas", 11, "bold"), takefocus=0,
                               command=lambda a=action: self._start_capture(a))
            button.grid(row=row, column=1, pady=3)
            self.buttons[action] = button
        self.status = tk.Label(self, text="", bg=BG, fg=WARN, font=("Segoe UI", 10), wraplength=420, justify="left")
        self.status.grid(row=len(ACTION_LABELS) + 1, column=0, columnspan=2, sticky="w", pady=(10, 0))

        bar = tk.Frame(self, bg=BG)
        bar.grid(row=len(ACTION_LABELS) + 2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        for text, command, color in (("Restaurar padrão", self._restore, PANEL), ("Cancelar", self._cancel, PANEL),
                                     ("Salvar", self._save, ACCENT)):
            tk.Button(bar, text=text, command=command, bg=color, fg=TEXT, relief="flat", padx=14, pady=4,
                      font=("Segoe UI Semibold", 10)).pack(side="left", padx=(8, 0))
        self._refresh()
        self.after(50, self.focus_force)

    def _refresh(self) -> None:
        for action, button in self.buttons.items():
            if action == self.capturing:
                button.configure(text="aperte as teclas…", fg=WARN)
            else:
                button.configure(text=pretty_combo(self.binds[action]) or "(nenhum)", fg=TEXT)

    def _start_capture(self, action: str) -> None:
        self.capturing = action
        self.status.configure(text="")
        self._refresh()
        self.focus_force()

    def _key(self, event) -> None:
        if self.capturing is None or event.keycode in MODIFIER_VKS:
            return
        action, self.capturing = self.capturing, None
        if event.keycode == VK_ESCAPE:
            self._refresh()
            return
        combo = combo_from_vk(event.keycode)
        notes = []
        for other, other_combo in self.binds.items():
            if other != action and other_combo.lower() == combo.lower():
                self.binds[other] = ""
                notes.append(f"{pretty_combo(combo)} saiu de \"{ACTION_LABELS[other]}\".")
        if not has_modifier(combo):
            notes.append(f"Sem Ctrl/Alt/Shift, toda vez que você apertar {pretty_combo(combo)} jogando o atalho "
                         "também dispara.")
        self.binds[action] = combo
        self.status.configure(text=" ".join(notes))
        self._refresh()

    def _restore(self) -> None:
        self.binds = {action: self.defaults.get(action, "") for action in ACTION_LABELS}
        self.capturing = None
        self.status.configure(text="")
        self._refresh()

    def _save(self) -> None:
        self.on_save(dict(self.binds))
        self.destroy()
        self.on_close()

    def _cancel(self) -> None:
        self.destroy()
        self.on_close()
