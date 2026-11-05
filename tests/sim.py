"""Random but realistic jungle clears for stress tests: the gold each camp pays monster by monster
(in random order, with pauses), walking between camps, passive income, recall purchases and resets,
sampled like the Live Client API (about 10 Hz, with jitter)."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from tracker import camp_key

# Gold per monster, as the game pays it out (sums match tracker.DEFAULT_CAMP_GOLD).
MONSTERS = {
    "red": [90], "blue": [90], "gromp": [80], "scuttle": [55],
    "wolves": [55, 15, 15],
    "raptors": [35, 8, 8, 8, 8, 8],
    "krugs": [10, 15, 14, 14, 14, 14, 14, 14],
}
# A lesser wolf left behind despawns once the big wolf died (tracker.OTHER_CAMP_GOLD).
OTHER_MONSTERS = {"wolves": [[55, 15]]}
OTHER_CHANCE = 0.3
# The once-per-clear bonus (tracker.BONUS_GOLD): 20 gold 0.5 s after the first kill past BONUS_AFTER.
BONUS, BONUS_AFTER, BONUS_LAG = 20, 150.0, 0.5
PASSIVE = 2.04


@dataclass
class Clear:
    camps: list[str]
    events: list[tuple[float, float]] = field(default_factory=list)  # (time, gold change)
    deaths: list[float] = field(default_factory=list)  # when each step ended (last kill or purchase)


def simulate_clear(camps: list[str], rng: random.Random, start: float = 55.0, max_gap: float = 2.5,
                   single_hit_chance: float = 0.15) -> Clear:
    """max_gap is the longest pause between two kills inside one camp."""
    clear = Clear(list(camps))
    t = start + rng.uniform(4.0, 12.0)
    for camp in camps:
        key = camp_key(camp)
        if key == "recall":
            t += rng.uniform(8.0, 13.0)  # recall channel + shopping
            clear.events.append((t, -rng.choice([300, 350, 450, 875])))
            clear.deaths.append(t)
            t += rng.uniform(8.0, 18.0)  # walk back out
            continue
        monsters = list(MONSTERS[key])
        if key in OTHER_MONSTERS and rng.random() < OTHER_CHANCE:
            monsters = list(rng.choice(OTHER_MONSTERS[key]))
        rng.shuffle(monsters)
        if len(monsters) > 1 and rng.random() < single_hit_chance:
            monsters = [sum(monsters)]  # the whole camp dies to one AoE hit
        for n, gold in enumerate(monsters):
            if n:
                t += rng.uniform(0.0, max_gap)
            clear.events.append((t, gold))
        clear.deaths.append(t)
        t += rng.uniform(5.0, 10.0)  # walk to the next camp and kill its first monster
    kills = sorted(e for e in clear.events if e[1] > 0)
    for kill_time, _ in kills:
        bonus_time = kill_time + BONUS_LAG
        # A kill in the same sample as the bonus would hide it (a known limit, see tracker.BONUS_GOLD).
        if kill_time >= BONUS_AFTER and all(abs(k - bonus_time) > 0.25 for k, _ in kills):
            clear.events.append((bonus_time, BONUS))
            break
    return clear


def samples(clear: Clear, rng: random.Random, start: float = 45.0, gold: float = 50.0,
            cs_mode: str = "batched") -> list[tuple[float, float, int | None]]:
    """(game time, gold, cs) at ~10 Hz until a few seconds after the clear. cs_mode "batched" reports
    CS in steps of 10 like the real API, "none" leaves it out."""
    events = sorted(clear.events)
    end = clear.deaths[-1] + 6.0  # past FALLBACK_QUIET, so a last camp that paid less still closes
    out, t, cs = [], start, 0
    while t < end:
        t += rng.uniform(0.08, 0.12)
        gold += PASSIVE * 0.1
        while events and events[0][0] <= t:
            _, change = events.pop(0)
            gold += change
            if change > 0:
                cs += 1
        out.append((t, gold, cs // 10 * 10 if cs_mode == "batched" else None))
    return out
