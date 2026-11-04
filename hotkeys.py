"""Global hotkeys read straight from the keyboard state (no keyboard hook, no extra packages).

RegisterHotKey would be simpler, but games register their raw keyboard input with RIDEV_NOHOTKEYS,
which silences registered hotkeys while the game window has focus. Polling the key state works
regardless of which window is in front.
"""
from __future__ import annotations

import ctypes
import threading

user32 = ctypes.windll.user32

POLL_INTERVAL = 0.015
MOD_ALT, MOD_CONTROL, MOD_SHIFT = 0x1, 0x2, 0x4
MODIFIERS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "shift": MOD_SHIFT}
NAMED_KEYS = {
    **{f"F{n}": 0x6F + n for n in range(1, 25)},
    **{f"NUM{n}": 0x60 + n for n in range(10)},
    "NUMMUL": 0x6A, "NUMADD": 0x6B, "NUMSUB": 0x6D, "NUMDEC": 0x6E, "NUMDIV": 0x6F,
    "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "PAUSE": 0x13, "SCROLLLOCK": 0x91, "SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D, "BACKSPACE": 0x08,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
    # Symbol keys by position rather than symbol, so a binding survives a layout change.
    # On ABNT2: OEM1 = ç, OEM2 = ;, OEM4 = ´, OEM5 = ], OEM6 = [, OEM7 = ~ (US: ; / [ \ ] ').
    "OEM1": 0xBA, "OEM2": 0xBF, "OEM3": 0xC0, "OEM4": 0xDB, "OEM5": 0xDC, "OEM6": 0xDD, "OEM7": 0xDE,
    "OEM102": 0xE2, "COMMA": 0xBC, "PERIOD": 0xBE, "MINUS": 0xBD, "PLUS": 0xBB,
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
        for char in (key, key.lower()):
            scan = user32.VkKeyScanW(ord(char)) & 0xFFFF
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


def key_label(vk: int) -> str:
    """What the key shows on the active keyboard layout."""
    char = chr(user32.MapVirtualKeyW(vk, MAPVK_VK_TO_CHAR) & 0xFFFF)
    return char.upper() if char.isprintable() and char.strip() else VK_NAMES.get(vk, f"VK{vk}")


def pretty_combo(combo: str) -> str:
    """'ctrl+shift+OEM1' -> 'Ctrl+Shift+Ç' on an ABNT2 keyboard."""
    if not combo:
        return ""
    *mods, _ = combo.split("+")
    try:
        key = key_label(parse_combo(combo)[1])
    except (KeyError, ValueError):
        return combo
    return "+".join([m.capitalize() for m in mods] + [key])


def has_modifier(combo: str) -> bool:
    return any(part.lower() in MODIFIERS for part in combo.split("+")[:-1])


def is_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def held_modifiers() -> int:
    return ((MOD_CONTROL if is_down(VK_CONTROL) else 0) | (MOD_ALT if is_down(VK_MENU) else 0)
            | (MOD_SHIFT if is_down(VK_SHIFT) else 0))


class HotkeyThread(threading.Thread):
    def __init__(self, bindings: dict[str, str], on_action):
        super().__init__(daemon=True)
        self.bindings = bindings
        self.on_action = on_action
        self.failed: list[str] = []
        self._ready = threading.Event()
        self._stopped = threading.Event()

    def run(self) -> None:
        combos = {}
        for action, combo in self.bindings.items():
            if not combo:
                continue
            try:
                combos[action] = parse_combo(combo)
            except (KeyError, ValueError):
                self.failed.append(combo)
        self._ready.set()
        pressed: set[str] = set()
        while not self._stopped.wait(POLL_INTERVAL):
            mods = held_modifiers()
            for action, (combo_mods, vk) in combos.items():
                # Exact modifiers, so Ctrl+Shift+X doesn't also fire a Shift+X binding.
                if mods == combo_mods and is_down(vk):
                    if action not in pressed:
                        pressed.add(action)
                        self.on_action(action)
                else:
                    pressed.discard(action)

    def wait_ready(self, timeout: float = 2.0) -> None:
        self._ready.wait(timeout)

    def stop(self) -> None:
        self._stopped.set()
        if self.is_alive():
            self.join(timeout=1.0)
