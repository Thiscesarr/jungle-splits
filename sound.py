"""Short alert tones, generated on the fly as WAV files and played asynchronously with winsound."""
from __future__ import annotations

import math
import struct
import wave
import winsound
from pathlib import Path

RATE = 44100
# Each sound is a sequence of (frequency Hz, seconds); 0 Hz is a pause.
TONES = {
    "purple": [(1319, 0.07), (0, 0.02), (1760, 0.11)],  # best segment ever: bright double chirp
    "green": [(988, 0.12)],  # faster than PB
    "red": [(330, 0.16)],  # slower than PB: low thud
    "reset": [(784, 0.12), (587, 0.12), (392, 0.24)],  # run can no longer beat the PB
    "pb": [(1047, 0.09), (1319, 0.09), (1568, 0.09), (2093, 0.26)],  # new PB
    "tick": [(880, 0.06)],  # countdown to camp spawn
    "go": [(1319, 0.22)],
}


def _samples(notes: list[tuple[float, float]], volume: float) -> bytes:
    frames = bytearray()
    for freq, seconds in notes:
        count = int(RATE * seconds)
        fade = min(count // 4, int(RATE * 0.008))  # short fades so tones don't click
        for n in range(count):
            envelope = min(1.0, n / fade if fade else 1.0, (count - n) / fade if fade else 1.0)
            value = math.sin(2 * math.pi * freq * n / RATE) * envelope * volume if freq else 0.0
            frames += struct.pack("<h", int(value * 32767))
    return bytes(frames)


class Sounds:
    def __init__(self, folder: Path, volume: float = 0.5, enabled: bool = True):
        self.folder = folder
        self.enabled = enabled
        folder.mkdir(parents=True, exist_ok=True)
        for name, notes in TONES.items():
            with wave.open(str(folder / f"{name}.wav"), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(RATE)
                wav.writeframes(_samples(notes, max(0.0, min(volume, 1.0))))

    def play(self, name: str) -> None:
        if self.enabled:
            winsound.PlaySound(str(self.folder / f"{name}.wav"),
                               winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
