"""Per-champion clear routes and record times from the community "Jungle Clear Compilation" sheet."""
from __future__ import annotations

import csv
import io
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from links import VIDEO_HOSTS, safe_url
from tracker import parse_clock

SHEET_URL = ("https://docs.google.com/spreadsheets/d/1jE8bnlnIJnmWv9pnVW9veMKRXJNaaJf5tneQB3xUkbI"
             "/export?format=csv&gid=1938238048")
CACHE_NAME = "clears.csv"
CACHE_MAX_AGE = 12 * 3600
TIME_RE = re.compile(r"^\d{1,2}:\d{2}(\.\d+)?$")
# Rune shards as the sheet writes them in the notes, e.g. "AS/AD/HPF".
SHARD = r"(?:AS|AD|AP|AH|MS|HPF|HPS|T&SR)"
SHARDS_RE = re.compile(rf"(?<![A-Z&]){SHARD}(?:/{SHARD})+(?![A-Z&])")


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
    shards: str = ""
    smites: int = 1
    video: str = ""

    @property
    def path(self) -> str:
        return "->".join(self.camps)

    @property
    def stats_name(self) -> str:
        """File name for this route's PB: 1-smite clears keep the plain path name."""
        return self.path if self.smites == 1 else f"{self.path}-{self.smites}smite"


def parse_path(path: str) -> tuple[str, ...]:
    return tuple(step.strip() for step in path.split("->") if step.strip())


def parse_sheet(text: str) -> dict[str, list[Route]]:
    """Champion (normalized) -> routes, one per path and smite count with its fastest time, fastest first."""
    best: dict[tuple[str, str, int], Route] = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 6 or "->" not in row[5] or not TIME_RE.match(row[4].strip()):
            continue
        notes = row[8] if len(row) > 8 else ""
        shards = SHARDS_RE.search(notes)
        smites = int(row[3]) if row[3].strip().isdigit() else 1
        # Anyone can edit the sheet: only an https link to a video site is kept (see links.py).
        video = safe_url(row[6], VIDEO_HOSTS) if len(row) > 6 else ""
        route = Route(row[0].strip(), parse_path(row[5]), parse_clock(row[4]),
                      row[7].strip() if len(row) > 7 else "", row[1].strip(), shards.group(0) if shards else "",
                      smites, video)
        key = (norm(route.champion), route.path, route.smites)
        if key not in best or route.record < best[key].record:
            best[key] = route
    routes: dict[str, list[Route]] = {}
    for (champ, _, _), route in best.items():
        routes.setdefault(champ, []).append(route)
    for champ_routes in routes.values():
        champ_routes.sort(key=lambda r: r.record)
    return routes


def routes_for_champion(sheet_routes: dict[str, list[Route]], champion: str, smites: int,
                        preferred: str | None = None, fallback: list[str] = ()) -> list[Route]:
    """The champion's routes for a smite count: sheet clears with that many smites first, then paths
    only clocked with the other count (no record to compare), then the preferred route; generic
    fallback routes for champions the sheet doesn't cover."""
    clocked = sheet_routes.get(norm(champion), [])
    routes = [r for r in clocked if r.smites == smites]
    for other in clocked:
        if all(r.path != other.path for r in routes):
            routes.append(Route(champion, other.camps, smites=smites))
    if preferred and all(r.camps != parse_path(preferred) for r in routes):
        routes.insert(0, Route(champion, parse_path(preferred), smites=smites))
    return routes or [Route(champion, parse_path(p), smites=smites) for p in fallback]


def load_routes(data_dir: Path, fallback: Path) -> dict[str, list[Route]]:
    for path in (data_dir / CACHE_NAME, fallback):
        try:
            routes = parse_sheet(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):  # missing, or not text (a damaged download)
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
