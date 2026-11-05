"""Saved records (PB, best segments and attempt history) of each champion's routes: listed and deleted from
the Settings window, so a cheated or broken clear doesn't leave an unbeatable PB behind."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tracker import slug

TWO_SMITES_SUFFIX = "-2smite"


@dataclass(frozen=True)
class Record:
    champion: str
    path: Path
    camps: tuple[str, ...]
    smites: int
    pb: float | None
    attempts: int


def champion_names(champions: list[str]) -> dict[str, str]:
    """Data folder name -> champion name as the game and the sheet write it."""
    return {slug(name): name for name in champions}


def list_records(data_dir: Path, names: dict[str, str]) -> list[Record]:
    """Every route with saved stats under data_dir/<champion>/<route>.json, by champion then route; routes
    only selected, never attempted, have nothing to delete and are left out."""
    records = []
    for folder in sorted(p for p in data_dir.iterdir() if p.is_dir()) if data_dir.is_dir() else []:
        for path in sorted(folder.glob("*.json")):
            if path.name.endswith(".corrupt.json"):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                camps = tuple(data["camps"])
            except (OSError, ValueError, KeyError, TypeError):
                continue
            pb = data.get("pb")
            attempts = int(data.get("attempts", 0))
            if not pb and not attempts:
                continue
            records.append(Record(
                champion=names.get(folder.name, folder.name.replace("-", " ").title()),
                path=path,
                camps=camps,
                smites=2 if path.stem.endswith(TWO_SMITES_SUFFIX) else 1,
                pb=pb[-1] if pb else None,
                attempts=attempts,
            ))
    return sorted(records, key=lambda r: (r.champion.lower(), r.camps, r.smites))


def delete_records(paths: list[Path]) -> int:
    """Deletes the given route files (and a champion folder left empty); returns how many were deleted."""
    deleted = 0
    for path in paths:
        try:
            path.unlink()
            deleted += 1
        except FileNotFoundError:
            continue
        try:
            path.parent.rmdir()  # only succeeds if no other route of the champion is left
        except OSError:
            pass
    return deleted
