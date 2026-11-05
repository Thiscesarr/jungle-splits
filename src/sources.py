"""Game data feeds: Riot's Live Client Data API, plus a simulated clear for trying the overlay."""
from __future__ import annotations

import json
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
    return Runes("/".join(names), (full.get("keystone") or {}).get("displayName", ""))


def find_player(players: list[dict], active: dict) -> dict | None:
    """The scoreboard entry (CS, champion) of the local player."""
    for key in ("riotId", "summonerName"):
        if active.get(key):
            for player in players:
                if player.get(key) == active[key]:
                    return player
    return players[0] if len(players) == 1 else None


class LiveClientSource(threading.Thread):
    """Polls the official local API the game exposes on port 2999 (also in the Practice Tool)."""

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
        online = None
        while True:
            started = time.perf_counter()
            try:
                with opener.open(LIVE_CLIENT_URL, timeout=1.0) as resp:
                    data = json.load(resp)
                game_time = float(data["gameData"]["gameTime"])
                active = data["activePlayer"]
                gold = float(active["currentGold"])
                me = find_player(data.get("allPlayers", []), active) or {}
                sample = Sample(game_time, gold, (me.get("scores") or {}).get("creepScore"), active.get("level"),
                                len(me["items"]) if isinstance(me.get("items"), list) else None,
                                me.get("championName"), parse_runes(active), time.perf_counter())
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                if online is not False:
                    self.out.put(("offline",))
                    online = False
                time.sleep(1.0)
                continue
            online = True
            self.out.put(("sample", sample))
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
