"""Per-champion clear routes and record times from the community "Jungle Clear Compilation" sheet."""
from __future__ import annotations

import csv
import io
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from tracker import parse_clock

SHEET_URL = ("https://docs.google.com/spreadsheets/d/1jE8bnlnIJnmWv9pnVW9veMKRXJNaaJf5tneQB3xUkbI"
             "/export?format=csv&gid=1938238048")
CACHE_NAME = "clears.csv"
CACHE_MAX_AGE = 12 * 3600
TIME_RE = re.compile(r"^\d{1,2}:\d{2}(\.\d+)?$")


def norm(name: str) -> str:
    """'Nunu & Willump' -> 'nunuwillump', so sheet names match the game's champion names."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


@dataclass(frozen=True)
class Route:
    champion: str
    camps: tuple[str, ...]
    record: float | None = None
    player: str = ""
    patch: str = ""

    @property
    def path(self) -> str:
        return "->".join(self.camps)


def parse_path(path: str) -> tuple[str, ...]:
    return tuple(step.strip() for step in path.split("->") if step.strip())


def parse_sheet(text: str) -> dict[str, list[Route]]:
    """Champion (normalized) -> routes, one per path with its fastest time, fastest first."""
    best: dict[tuple[str, str], Route] = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 6 or "->" not in row[5] or not TIME_RE.match(row[4].strip()):
            continue
        route = Route(row[0].strip(), parse_path(row[5]), parse_clock(row[4]),
                      row[7].strip() if len(row) > 7 else "", row[1].strip())
        key = (norm(route.champion), route.path)
        if key not in best or route.record < best[key].record:
            best[key] = route
    routes: dict[str, list[Route]] = {}
    for (champ, _), route in best.items():
        routes.setdefault(champ, []).append(route)
    for champ_routes in routes.values():
        champ_routes.sort(key=lambda r: r.record)
    return routes


def load_routes(data_dir: Path, fallback: Path) -> dict[str, list[Route]]:
    for path in (data_dir / CACHE_NAME, fallback):
        try:
            routes = parse_sheet(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if routes:
            return routes
    return {}


def cache_is_stale(data_dir: Path) -> bool:
    cache = data_dir / CACHE_NAME
    return not cache.exists() or time.time() - cache.stat().st_mtime > CACHE_MAX_AGE


def refresh_sheet(data_dir: Path) -> bool:
    """Downloads the online sheet into the cache; keeps the old cache if the download looks wrong."""
    try:
        with urllib.request.urlopen(SHEET_URL, timeout=15) as resp:
            text = resp.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if not parse_sheet(text):
        return False
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / CACHE_NAME).write_text(text, encoding="utf-8")
    return True
