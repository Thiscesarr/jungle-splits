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
    "PAUSE": 0x13, "SCROLLLOCK": 0x91, "SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D, "BACKSPACE": 0x08,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
}
MAPVK_VK_TO_CHAR = 2
VK_NAMES = {vk: name for name, vk in NAMED_KEYS.items()}
MODIFIER_VKS = {0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12


def parse_combo(combo: str) -> tuple[int, int]:
    """'ctrl+shift+S' -> (modifiers, virtual key)."""
    *mods, key = [part.strip() for part in combo.split("+") if part.strip()] or [""]
    flags = 0
    for mod in mods:
        flags |= MODIFIERS[mod.lower()]
    key_upper = key.upper()
    if key_upper in NAMED_KEYS:
        return flags, NAMED_KEYS[key_upper]
    if len(key) == 1 and key.isascii() and key.isalnum():
        return flags, ord(key_upper)
    if len(key) == 1:
        # Symbol keys (; / ç ´ ...) sit on different virtual keys per layout, so ask the active one.
        scan = user32.VkKeyScanW(ord(key)) & 0xFFFF
        if scan != 0xFFFF and not scan >> 8:  # reachable without Shift/AltGr
            return flags, scan & 0xFF
    if key_upper.startswith("VK") and key_upper[2:].isdigit():
        return flags, int(key_upper[2:])
    raise ValueError(f"tecla desconhecida: {combo!r}")


def combo_from_vk(vk: int) -> str:
    """Combo string for a key pressed now, reading which modifiers are held."""
    held = [name for name, mod_vk in (("ctrl", VK_CONTROL), ("alt", VK_MENU), ("shift", VK_SHIFT))
            if user32.GetAsyncKeyState(mod_vk) & 0x8000]
    if vk in VK_NAMES:
        key = VK_NAMES[vk]
    elif 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        key = chr(vk)
    else:
        char = chr(user32.MapVirtualKeyW(vk, MAPVK_VK_TO_CHAR) & 0xFFFF)
        key = char.upper() if char.isprintable() and char not in " +" else f"VK{vk}"
    return "+".join(held + [key])


def has_modifier(combo: str) -> bool:
    return any(part.lower() in MODIFIERS for part in combo.split("+")[:-1])


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
            if not combo:
                continue
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
            self.join(timeout=1.0)
