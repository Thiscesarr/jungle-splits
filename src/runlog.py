"""Debug log of each attempt: the raw game samples and the splits, so a player can send a bug report."""
from __future__ import annotations

import time
from pathlib import Path

KEEP_FILES = 30


class RunLog:
    def __init__(self, folder: Path):
        self.folder = folder
        self.rows: list[tuple] = []
        self.started: str | None = None

    def add(self, game_time: float, run_time: float, gold: float, cs: int | None, level: int | None,
            items: int | None) -> None:
        if not self.rows:
            self.started = time.strftime("%Y%m%d-%H%M%S")
        self.rows.append((game_time, run_time, gold, cs, level, items))

    def clear(self) -> None:
        self.rows.clear()
        self.started = None

    def save(self, info: dict[str, object], splits: list[tuple[str, float, float, bool]]) -> Path | None:
        """Writes (or rewrites) this attempt's file: info as header lines, then one line per split
        (camp, time, gold, manual) and the samples. Keeps only the newest files."""
        if not self.rows:
            return None
        self.folder.mkdir(parents=True, exist_ok=True)
        champion = "".join(c for c in str(info.get("champion", "")) if c.isalnum()) or "run"
        target = self.folder / f"{self.started}-{champion}.csv"
        lines = [f"# {key}: {value}" for key, value in info.items()]
        lines += [f"# split: {camp} at {at:.2f} with {gold:.1f} gold{' (manual)' if manual else ''}"
                  for camp, at, gold, manual in splits]
        lines.append("game_time,run_time,gold,cs,level,items")
        lines += [",".join("" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v)) for v in row)
                  for row in self.rows]
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        for old in sorted(self.folder.glob("*.csv"))[:-KEEP_FILES]:
            old.unlink(missing_ok=True)
        return target
