"""What the overlay shows: the clock always, the other parts as the player picks them, by hand or through
a preset (just the clock, the clock and the camps, everything). Only the drawing reads this; timing,
splits, sounds and records work the same whatever is shown."""
from __future__ import annotations

# In the order they appear on the overlay, top to bottom.
PARTS = ("header", "delta", "info", "camps", "verdict", "runes", "video", "footer")

PRESETS = {
    "clock": {part: False for part in PARTS},
    "splits": {part: part in ("delta", "camps") for part in PARTS},
    "full": {part: True for part in PARTS},
}
PRESET_ORDER = ("clock", "splits", "full")
CUSTOM = "custom"


def normalize(saved) -> dict[str, bool]:
    """The saved choice, with anything missing or broken shown (as before this setting existed)."""
    saved = saved if isinstance(saved, dict) else {}
    return {part: bool(saved.get(part, True)) for part in PARTS}


def preset_of(show: dict[str, bool]) -> str:
    """The preset these choices match, or CUSTOM."""
    show = normalize(show)
    return next((name for name in PRESET_ORDER if PRESETS[name] == show), CUSTOM)


def clock_only(show: dict[str, bool]) -> bool:
    """Nothing but the clock (and maybe its delta): the overlay shrinks to a small panel."""
    show = normalize(show)
    return not any(show[part] for part in PARTS if part != "delta")
