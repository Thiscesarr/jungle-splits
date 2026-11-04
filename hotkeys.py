"""Global hotkeys through the Win32 RegisterHotKey API (no keyboard hook, no extra packages)."""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
MODIFIERS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "shift": MOD_SHIFT}
NAMED_KEYS = {
    **{f"F{n}": 0x6F + n for n in range(1, 25)},
    **{f"NUM{n}": 0x60 + n for n in range(10)},
    "NUMMUL": 0x6A, "NUMADD": 0x6B, "NUMSUB": 0x6D, "NUMDEC": 0x6E, "NUMDIV": 0x6F,
    "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "PAUSE": 0x13, "SCROLLLOCK": 0x91,
}


def parse_combo(combo: str) -> tuple[int, int]:
    """'ctrl+F7' -> (modifiers, virtual key)."""
    *mods, key = [part.strip() for part in combo.split("+") if part.strip()] or [""]
    flags = 0
    for mod in mods:
        flags |= MODIFIERS[mod.lower()]
    key_upper = key.upper()
    if key_upper in NAMED_KEYS:
        return flags, NAMED_KEYS[key_upper]
    if len(key) == 1 and key.isalnum():
        return flags, ord(key_upper)
    raise ValueError(f"tecla desconhecida: {combo!r}")


class HotkeyThread(threading.Thread):
    def __init__(self, bindings: dict[str, str], on_action):
        super().__init__(daemon=True)
        self.bindings = bindings
        self.on_action = on_action
        self.failed: list[str] = []
        self._thread_id = None
        self._ready = threading.Event()

    def run(self) -> None:
        # Hotkeys belong to the thread that registers them, so registration and the loop share it.
        self._thread_id = kernel32.GetCurrentThreadId()
        actions = {}
        for hotkey_id, (action, combo) in enumerate(self.bindings.items(), start=1):
            try:
                mods, vk = parse_combo(combo)
            except (KeyError, ValueError):
                self.failed.append(combo)
                continue
            if user32.RegisterHotKey(None, hotkey_id, mods | MOD_NOREPEAT, vk):
                actions[hotkey_id] = action
            else:
                self.failed.append(combo)
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in actions:
                self.on_action(actions[msg.wParam])
        for hotkey_id in actions:
            user32.UnregisterHotKey(None, hotkey_id)

    def wait_ready(self, timeout: float = 2.0) -> None:
        self._ready.wait(timeout)

    def stop(self) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
