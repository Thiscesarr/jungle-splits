"""Game data feeds: Riot's Live Client Data API, plus a simulated clear for trying the overlay."""
from __future__ import annotations

import json
import math
import queue
import random
import ssl
import threading
import time
import urllib.request
from dataclasses import dataclass

from tracker import (DEFAULT_CAMP_GOLD, FALLBACK_CAMP_GOLD, MULTI_MONSTER_CAMPS, PASSIVE_GOLD_PER_SEC,
                     PASSIVE_GOLD_START, RECALL, camp_key)

LIVE_CLIENT_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"
PRACTICE_MODE = "PRACTICETOOL"  # gameData.gameMode in the Practice Tool
MAX_GAME_TIME, MAX_GOLD, MAX_CS, MAX_LEVEL, MAX_NAME = 86400.0, 1_000_000.0, 5000, 30, 40
OTHER_GAME_POLL = 5.0  # seconds between checks while a game that isn't the Practice Tool runs
# Stat shard ids, named like the clear sheet does (Adaptive becomes AD or AP).
SHARD_NAMES = {5008: "ADAPTIVE", 5005: "AS", 5007: "AH", 5010: "MS", 5001: "HPS", 5011: "HPF", 5013: "T&SR",
               5002: "AR", 5003: "MR"}
SHARD_DESCRIPTIONS = [("Adaptive", "ADAPTIVE"), ("AttackSpeed", "AS"), ("CDR", "AH"), ("Haste", "AH"),
                      ("MovementSpeed", "MS"), ("HealthScaling", "HPS"), ("HealthFlat", "HPF"),
                      ("HealthPlus", "HPF"), ("Tenacity", "T&SR"), ("Armor", "AR"), ("MagicRes", "MR")]


@dataclass(frozen=True)
class Runes:
    shards: str  # "AS/AD/HPS"
    keystone: str


@dataclass
class Sample:
    game_time: float
    gold: float
    cs: int | None
    level: int | None
    items: int | None
    champion: str | None
    runes: Runes | None
    received: float


def number(value, low: float, high: float) -> float:
    """value as a finite number within the limits; ValueError for anything else (text, NaN, a list...)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"not a number: {value!r}")
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"out of range: {value!r}")
    return value


def whole(value, low: int, high: int) -> int | None:
    """value as a whole number within the limits, or None."""
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        return None
    return value


def champion_name(value) -> str | None:
    """A champion's name as the game or the sheet writes it ("Lee Sin", "Cho'Gath", "Nunu & Willump"),
    or None for anything else. The name is saved and used in file names and on screen."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not 1 <= len(value) <= MAX_NAME or not all(c.isalnum() or c in " '.&-" for c in value):
        return None
    return value


def parse_runes(active: dict) -> Runes | None:
    full = active.get("fullRunes") or {}
    stats = full.get("statRunes") or []
    if not stats:
        return None
    adaptive = "AP" if (active.get("championStats") or {}).get("abilityPower", 0) > 0 else "AD"
    names = []
    for shard in stats:
        name = SHARD_NAMES.get(shard.get("id"))
        if name is None:
            description = shard.get("rawDescription", "")
            name = next((n for key, n in SHARD_DESCRIPTIONS if key.lower() in description.lower()), "?")
        names.append(adaptive if name == "ADAPTIVE" else name)
    keystone = (full.get("keystone") or {}).get("displayName", "")
    return Runes("/".join(names), keystone if isinstance(keystone, str) and len(keystone) <= MAX_NAME else "")


def find_player(players: list[dict], active: dict) -> dict | None:
    """The scoreboard entry (CS, champion) of the local player."""
    for key in ("riotId", "summonerName"):
        if active.get(key):
            for player in players:
                if player.get(key) == active[key]:
                    return player
    return players[0] if len(players) == 1 else None


def game_mode(data: dict) -> str:
    """The game's mode as the API names it, in capitals without separators: PRACTICETOOL, CLASSIC (normal
    and ranked games on Summoner's Rift), ARAM... Empty when the game doesn't say."""
    mode = (data.get("gameData") or {}).get("gameMode")
    return "".join(c for c in mode.upper() if c.isalnum()) if isinstance(mode, str) else ""


def read_game(data: dict, received: float) -> tuple:
    """One answer of the API as an event for the app: ("sample", Sample) in the Practice Tool, and
    ("other_game", mode) in any other game, whose gold and CS are never read: a laner's gold would
    otherwise be timed as jungle camps."""
    mode = game_mode(data)
    if mode != PRACTICE_MODE:
        return "other_game", mode or "?"
    # Anything can answer on the game's port while the game is closed, so every value is checked. What
    # the timing needs must be right (an error here means "no game"); the rest is dropped when it's odd.
    game_time = number(data["gameData"]["gameTime"], 0, MAX_GAME_TIME)
    active = data["activePlayer"]
    gold = number(active["currentGold"], 0, MAX_GOLD)
    me = find_player(data.get("allPlayers", []), active) or {}
    return "sample", Sample(game_time, gold, whole((me.get("scores") or {}).get("creepScore"), 0, MAX_CS),
                            whole(active.get("level"), 1, MAX_LEVEL),
                            len(me["items"]) if isinstance(me.get("items"), list) else None,
                            champion_name(me.get("championName")), parse_runes(active), received)


class LiveClientSource(threading.Thread):
    """Polls the official local API the game exposes on port 2999. Only the Practice Tool is timed: in
    any other game it says so once and then only checks, every few seconds, whether that game is over."""

    label = "LIVE CLIENT"

    def __init__(self, interval: float = 0.1):
        super().__init__(daemon=True)
        self.interval = interval
        self.out: queue.Queue | None = None

    def start_feeding(self, out: queue.Queue) -> None:
        self.out = out
        self.start()

    def run(self) -> None:
        # The game serves a self-signed certificate on localhost only.
        ctx = ssl._create_unverified_context()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                             urllib.request.HTTPSHandler(context=ctx))
        state = None  # "offline", "practice" or the mode of another game: said to the app when it changes
        while True:
            started = time.perf_counter()
            try:
                with opener.open(LIVE_CLIENT_URL, timeout=1.0) as resp:
                    data = json.load(resp)
                event = read_game(data, time.perf_counter())
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                if state != "offline":
                    self.out.put(("offline",))
                    state = "offline"
                time.sleep(1.0)
                continue
            if event[0] == "other_game":
                if state != event[1]:
                    self.out.put(event)
                    state = event[1]
                time.sleep(OTHER_GAME_POLL)
                continue
            state = "practice"
            self.out.put(event)
            time.sleep(max(0.0, self.interval - (time.perf_counter() - started)))


class DemoSource(threading.Thread):
    """Plays fake clears in a loop so the overlay can be tried without the game. Like the real
    Practice Tool, each new attempt is a Reset Game: level, items and gold go back to the start but
    the clock keeps running (the demo then fast-forwards to the camp spawn)."""

    label = "DEMO"
    # Seconds from the previous step, roughly a 2:50 clear with spawn at 0:55.
    # Multi-monster camps in three payouts, as monsters die in real clears (sums of tracker.DEFAULT_CAMP_GOLD).
    PAYOUTS = {"wolves": (15, 15, 55), "raptors": (16, 24, 35), "krugs": (24, 29, 56)}
    BASE_SEGMENTS = {"raptors": 16, "red": 14, "krugs": 15, "recall": 12, "wolves": 24, "gromp": 15, "blue": 14}
    RUNES = Runes("AS/AD/HPS", "Conqueror")

    def __init__(self, camps_fn, champion: str, camp_spawn: float = 55.0, speed: float = 1.0,
                 seed: int | None = None):
        super().__init__(daemon=True)
        self.camps_fn = camps_fn
        self.champion = champion
        self.camp_spawn = camp_spawn
        self.speed = speed
        self.rng = random.Random(seed)
        self.out: queue.Queue | None = None

    def start_feeding(self, out: queue.Queue) -> None:
        self.out = out
        self.start()

    def plan(self, camps: list[str], start: float = 0.0) -> list[tuple[float, float, int]]:
        """(game time, gold, cs) events of one simulated clear; a negative gold is the recall purchase."""
        events = []
        t = start + self.camp_spawn
        for camp in camps:
            key = camp_key(camp)
            t += self.BASE_SEGMENTS.get(key, 15) + self.rng.gauss(0, 0.9)
            if key == RECALL:
                events.append((t, -350, 0))
                continue
            gold = DEFAULT_CAMP_GOLD.get(key, FALLBACK_CAMP_GOLD)
            if key in self.PAYOUTS:
                first, second, last = self.PAYOUTS[key]
                events += [(t - 1.2, first, 2), (t - 0.6, second, 1), (t, last, 1)]
            else:
                events.append((t, gold, 4))
        return events

    def run(self) -> None:
        game_time = 0.0
        while True:
            start = game_time  # 0 for the first game, then the moment of each reset
            events = self.plan(self.camps_fn(), start)
            end = events[-1][0] + 4.0
            game_time = start + self.camp_spawn - 8.0  # fast-forward to just before the spawn
            gold, cs, level, items = 50.0, 0, 1, 1  # starting item already bought
            last = time.perf_counter()
            while game_time < end:
                time.sleep(0.1)
                now = time.perf_counter()
                step = (now - last) * self.speed
                last = now
                game_time += step
                if game_time - start > PASSIVE_GOLD_START:
                    gold += PASSIVE_GOLD_PER_SEC * 0.97 * step
                while events and events[0][0] <= game_time:
                    _, gold_gain, cs_gain = events.pop(0)
                    gold += gold_gain
                    cs += cs_gain
                    level = min(1 + cs // 4, 4)
                    items += gold_gain < 0
                # The real API only reports CS in steps of 10, so the demo does too.
                self.out.put(("sample", Sample(game_time, gold, cs // 10 * 10, level, items, self.champion,
                                               self.RUNES, now)))
            # Reset Game: champion back to the start, clock keeps going.
            self.out.put(("sample", Sample(game_time, 500.0, 0, 1, 0, self.champion, self.RUNES, time.perf_counter())))
