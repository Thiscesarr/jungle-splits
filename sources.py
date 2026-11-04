"""Game data feeds: Riot's Live Client Data API, plus a simulated clear for trying the overlay."""
from __future__ import annotations

import json
import queue
import random
import ssl
import threading
import time
import urllib.request

from tracker import (DEFAULT_CAMP_GOLD, FALLBACK_CAMP_GOLD, PASSIVE_GOLD_PER_SEC, PASSIVE_GOLD_START, RECALL,
                     camp_key)

LIVE_CLIENT_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"
MULTI_MONSTER_CAMPS = {"wolves", "raptors", "krugs"}


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
                me = find_player(data.get("allPlayers", []), active)
            except (OSError, ValueError, KeyError, TypeError):
                if online is not False:
                    self.out.put(("offline",))
                    online = False
                time.sleep(1.0)
                continue
            online = True
            cs = me.get("scores", {}).get("creepScore") if me else None
            champion = me.get("championName") if me else None
            self.out.put(("sample", game_time, gold, cs, champion, time.perf_counter()))
            time.sleep(max(0.0, self.interval - (time.perf_counter() - started)))


class DemoSource(threading.Thread):
    """Plays fake clears in a loop (reset after each one) so the overlay can be tried without the game."""

    label = "DEMO"
    # Seconds from the previous step, roughly a 2:50 clear with spawn at 0:55.
    BASE_SEGMENTS = {"raptors": 16, "red": 14, "krugs": 15, "recall": 12, "wolves": 24, "gromp": 15, "blue": 14}

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

    def plan(self, camps: list[str]) -> list[tuple[float, float, int]]:
        """(game time, gold, cs) events of one simulated clear; a negative gold is the recall purchase."""
        events = []
        t = self.camp_spawn
        for camp in camps:
            key = camp_key(camp)
            t += self.BASE_SEGMENTS.get(key, 15) + self.rng.gauss(0, 0.9)
            if key == RECALL:
                events.append((t, -350, 0))
                continue
            gold = DEFAULT_CAMP_GOLD.get(key, FALLBACK_CAMP_GOLD)
            if key in MULTI_MONSTER_CAMPS:
                events += [(t - 1.2, gold * 0.55, 2), (t - 0.6, gold * 0.25, 1), (t, gold * 0.20, 1)]
            else:
                events.append((t, gold, 4))
        return events

    def run(self) -> None:
        while True:
            events = self.plan(self.camps_fn())
            end = events[-1][0] + 4.0
            game_time, gold, cs = self.camp_spawn - 8.0, 500.0, 0
            last = time.perf_counter()
            while game_time < end:
                time.sleep(0.1)
                now = time.perf_counter()
                step = (now - last) * self.speed
                last = now
                game_time += step
                if game_time > PASSIVE_GOLD_START:
                    gold += PASSIVE_GOLD_PER_SEC * 0.97 * step
                while events and events[0][0] <= game_time:
                    _, gold_gain, cs_gain = events.pop(0)
                    gold += gold_gain
                    cs += cs_gain
                self.out.put(("sample", game_time, gold, cs, self.champion, now))
            # The loop restarts the clock, like the Practice Tool reset.
