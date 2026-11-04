"""Short alert tones, generated on the fly as WAV files and played asynchronously with winsound.

Notes are synthesized like a soft mallet (a quick attack that fades out) rather than flat beeps.
A WAV with the sound's name in the custom folder (sons/purple.wav, ...) replaces the generated one.
"""
from __future__ import annotations

import math
import struct
import wave
import winsound
from pathlib import Path

RATE = 44100
SOUND_NAMES = ["tick", "go", "purple", "green", "red", "reset", "pb"]
SOUND_LABELS = {
    "tick": "contagem", "go": "campos nasceram", "purple": "setor roxo", "green": "setor verde",
    "red": "setor vermelho", "reset": "não bate o PB", "pb": "novo PB",
}
# Each sound is a sequence of (frequency Hz, seconds); 0 Hz is a pause.
THEMES = {
    "suave": {
        "tick": [(330, 0.09)],
        "go": [(440, 0.30)],
        "purple": [(392, 0.10), (523, 0.24)],
        "green": [(440, 0.22)],
        "red": [(196, 0.26)],
        "reset": [(330, 0.14), (262, 0.14), (196, 0.36)],
        "pb": [(262, 0.11), (330, 0.11), (392, 0.11), (523, 0.42)],
    },
    "grave": {
        "tick": [(165, 0.10)],
        "go": [(220, 0.32)],
        "purple": [(196, 0.11), (262, 0.26)],
        "green": [(220, 0.24)],
        "red": [(110, 0.30)],
        "reset": [(165, 0.15), (131, 0.15), (98, 0.40)],
        "pb": [(131, 0.12), (165, 0.12), (196, 0.12), (262, 0.45)],
    },
    "agudo": {
        "tick": [(880, 0.06)],
        "go": [(1319, 0.22)],
        "purple": [(1319, 0.07), (0, 0.02), (1760, 0.11)],
        "green": [(988, 0.12)],
        "red": [(330, 0.16)],
        "reset": [(784, 0.12), (587, 0.12), (392, 0.24)],
        "pb": [(1047, 0.09), (1319, 0.09), (1568, 0.09), (2093, 0.26)],
    },
}
DEFAULT_THEME = "suave"


def _note(freq: float, seconds: float, volume: float) -> list[float]:
    count = int(RATE * seconds)
    if not freq:
        return [0.0] * count
    attack = int(RATE * 0.006)
    release = min(count // 3, int(RATE * 0.03))
    out = []
    for n in range(count):
        t = n / RATE
        envelope = min(1.0, n / attack) * math.exp(-4.0 * n / count) * min(1.0, (count - n) / release)
        # A little of the 2nd and 3rd harmonics makes it rounder than a pure sine, like a mallet.
        wave_value = (math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(4 * math.pi * freq * t)
                      + 0.08 * math.sin(6 * math.pi * freq * t)) / 1.33
        out.append(wave_value * envelope * volume)
    return out


def write_tone(path: Path, notes: list[tuple[float, float]], volume: float) -> None:
    samples = [v for freq, seconds in notes for v in _note(freq, seconds, volume)]
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(b"".join(struct.pack("<h", int(v * 32767)) for v in samples))


class Sounds:
    def __init__(self, folder: Path, volume: float = 0.35, enabled: bool = True, theme: str = DEFAULT_THEME,
                 custom_folder: Path | None = None):
        self.folder = folder
        self.custom_folder = custom_folder
        self.enabled = enabled
        self.configure(theme, volume)

    def configure(self, theme: str, volume: float) -> None:
        self.theme = theme if theme in THEMES else DEFAULT_THEME
        self.volume = max(0.0, min(volume, 1.0))
        self.folder.mkdir(parents=True, exist_ok=True)
        for name, notes in THEMES[self.theme].items():
            write_tone(self.folder / f"{name}.wav", notes, self.volume)

    def path(self, name: str) -> Path:
        custom = self.custom_folder / f"{name}.wav" if self.custom_folder else None
        return custom if custom and custom.exists() else self.folder / f"{name}.wav"

    def play(self, name: str, force: bool = False) -> None:
        if self.enabled or force:
            winsound.PlaySound(str(self.path(name)),
                               winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
