"""Game data feeds: Riot's Live Client Data API, plus a simulated clear for trying the overlay."""
from __future__ import annotations

import json
import queue
import random
import ssl
import threading
import time
import urllib.request

from tracker import DEFAULT_CAMP_GOLD, FALLBACK_CAMP_GOLD, PASSIVE_GOLD_PER_SEC, PASSIVE_GOLD_START

LIVE_CLIENT_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"
MULTI_MONSTER_CAMPS = {"wolves", "raptors", "krugs"}


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
                gold = float(data["activePlayer"]["currentGold"])
            except (OSError, ValueError, KeyError, TypeError):
                if online is not False:
                    self.out.put(("offline",))
                    online = False
                time.sleep(1.0)
                continue
            online = True
            self.out.put(("sample", game_time, gold, time.perf_counter()))
            time.sleep(max(0.0, self.interval - (time.perf_counter() - started)))


class DemoSource(threading.Thread):
    """Plays fake clears in a loop (reset after each one) so the overlay can be tried without the game."""

    label = "DEMO"
    BASE_SEGMENTS = [14.0, 13.5, 12.5, 13.5, 14.0, 12.0]

    def __init__(self, camps_fn, camp_spawn: float = 90.0, speed: float = 1.0, seed: int | None = None):
        super().__init__(daemon=True)
        self.camps_fn = camps_fn
        self.camp_spawn = camp_spawn
        self.speed = speed
        self.rng = random.Random(seed)
        self.out: queue.Queue | None = None

    def start_feeding(self, out: queue.Queue) -> None:
        self.out = out
        self.start()

    def plan(self, camps: list[str]) -> list[tuple[float, float]]:
        """(game time, gold) kill events of one simulated clear."""
        events = []
        t = self.camp_spawn
        for i, camp in enumerate(camps):
            t += self.BASE_SEGMENTS[i % len(self.BASE_SEGMENTS)] + self.rng.gauss(0, 0.9)
            gold = DEFAULT_CAMP_GOLD.get(camp.lower(), FALLBACK_CAMP_GOLD)
            if camp.lower() in MULTI_MONSTER_CAMPS:
                events += [(t - 1.2, gold * 0.55), (t - 0.6, gold * 0.25), (t, gold * 0.20)]
            else:
                events.append((t, gold))
        return events

    def run(self) -> None:
        while True:
            events = self.plan(self.camps_fn())
            end = events[-1][0] + 4.0
            game_time, gold = self.camp_spawn - 8.0, 50.0
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
                    gold += events.pop(0)[1]
                self.out.put(("sample", game_time, gold, now))
            # The loop restarts the clock, like the Practice Tool reset.
