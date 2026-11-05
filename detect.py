"""Recognizes which route is being cleared from the shape of each camp, without knowing the route.

The game does not say which camp died, but camps leave a signature: single-monster camps (Red, Blue,
Gromp) pay their gold in one go, multi-monster camps (Wolves, Raptors, Krugs) over several kills, a
Recall shows up as a shop purchase, and camps pay different gold. Matching that sequence against the
champion's known routes tells them apart within a camp or two.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tracker import (CS_OK, DEFAULT_CAMP_GOLD, BonusFilter, FALLBACK_CAMP_GOLD, FALLBACK_QUIET, MULTI_MONSTER_CAMPS,
                     OTHER_CAMP_GOLD, PURCHASE_GOLD, RECALL, camp_key, median, plausible_camp_gold,
                     sample_gains)

# Without knowing the route, a step only closes on gold that adds up to one whole camp; part of a
# camp (the small wolves alone) must not count as a camp of its own.
WHOLE_CAMP_TOLERANCE = 0.08
WHOLE_CAMP_GOLD = sorted(set(DEFAULT_CAMP_GOLD.values()))
MULTI_CAMP_GOLD = sorted({DEFAULT_CAMP_GOLD[camp] for camp in MULTI_MONSTER_CAMPS})
# Less usual totals (see tracker.OTHER_CAMP_GOLD) only close a step after the longer fallback pause.
OTHER_GOLD = sorted({gold for golds in OTHER_CAMP_GOLD.values() for gold in golds})
# Pauses inside a camp can pass the tracker's quiet window; walking to the next camp is longer.
MIN_DETECT_QUIET = 3.0
MIN_CAMP_GOLD = 40.0
# Costs of a camp not matching the route's camp.
SINGLE_SEEN_AS_MULTI = 3.0  # one monster can't die in several kills
MULTI_SEEN_AS_SINGLE = 0.3  # a multi camp can die in one AoE hit; the gold still tells camps apart
MAX_GOLD_COST = 2.0
# Camp gold is exact (measured monster by monster) and read to about a gold, so a few gold apart
# already tells camps apart: Wolves dying to one hit pay 85, a buff 90.
GOLD_COST_WEIGHT = 15
IMPOSSIBLE = float("inf")
# Switch only when the current route is clearly worse than the best one.
SWITCH_MARGIN = 0.75
GOLD_SAMPLES_KEPT = 5


@dataclass
class Step:
    kind: str  # "camp" or "recall"
    time: float
    gold: float = 0.0
    kills: int = 0

    @property
    def multi(self) -> bool:
        return self.kills >= 2


class StepDetector:
    """Splits the sample stream into camps and recalls on its own, independently of any route."""

    def __init__(self, camp_spawn: float, quiet_window: float, cs_per_camp: int):
        self.camp_spawn = camp_spawn
        self.quiet_window = max(quiet_window, MIN_DETECT_QUIET)
        self.cs_per_camp = cs_per_camp
        self.reset()

    def reset(self) -> None:
        self.steps: list[Step] = []
        self.prev: tuple[float, float, int | None] | None = None
        self.seg_gold = 0.0
        self.seg_kills = 0
        self.seg_cs = 0
        self.last_gold_time: float | None = None
        self.bonus = BonusFilter()

    def feed(self, game_time: float, gold: float, cs: int | None, cs_state: str) -> Step | None:
        """Returns the step that this sample completed, if any."""
        prev, self.prev = self.prev, (game_time, gold, cs)
        if prev is None or game_time < self.camp_spawn:
            return None
        gold_delta, kill_gold, cs_gain = sample_gains(prev, self.prev)
        kill_gold = self.bonus(game_time, kill_gold)
        if gold_delta <= -PURCHASE_GOLD and self.steps and self.steps[-1].kind == "camp" and not self.seg_kills:
            return self._emit(Step("recall", game_time))
        if kill_gold and cs_state != CS_OK and self._camp_ended(game_time, kill_gold):
            # Quiet long enough before this kill, or it would pay more than any camp: it is the next
            # camp's first.
            step = self._emit(Step("camp", self.last_gold_time, self.seg_gold, self.seg_kills))
            self.seg_gold, self.seg_kills, self.last_gold_time = kill_gold, 1, game_time
            self.seg_cs = cs_gain
            return step
        if kill_gold:
            self.seg_gold += kill_gold
            self.seg_kills += 1
            self.last_gold_time = game_time
        self.seg_cs += cs_gain
        if cs_state == CS_OK:
            if self.seg_cs >= self.cs_per_camp:
                return self._emit(Step("camp", game_time, self.seg_gold, self.seg_kills))
        elif self._camp_ended(game_time):
            return self._emit(Step("camp", self.last_gold_time, self.seg_gold, self.seg_kills))
        return None

    def _camp_ended(self, now: float, next_kill: float = 0.0) -> bool:
        """Whether the camp ended on its last kill, judged at time now (before next_kill counts)."""
        if self.last_gold_time is None:
            return False
        quiet = now - self.last_gold_time
        overshoot = self.seg_gold + next_kill > max(WHOLE_CAMP_GOLD) * (1 + WHOLE_CAMP_TOLERANCE)
        return ((quiet >= self.quiet_window and is_whole_camp(self.seg_gold, self.seg_kills))
                or (quiet >= MIN_DETECT_QUIET and next_kill and overshoot
                    and is_whole_camp(self.seg_gold, self.seg_kills, others=True))
                or (quiet >= FALLBACK_QUIET and is_whole_camp(self.seg_gold, self.seg_kills, others=True)))

    def _emit(self, step: Step) -> Step:
        self.steps.append(step)
        self.seg_gold, self.seg_kills, self.seg_cs, self.last_gold_time = 0.0, 0, 0, None
        return step


def is_whole_camp(gold: float, kills: int, others: bool = False) -> bool:
    """Gold paid over several kills can only be a multi-monster camp; a single payout can be any camp
    (one AoE hit can kill a whole wolf pack). others also accepts the less usual totals."""
    candidates = (MULTI_CAMP_GOLD if kills >= 2 else WHOLE_CAMP_GOLD) + (OTHER_GOLD if others else [])
    return any(abs(gold - camp) <= camp * WHOLE_CAMP_TOLERANCE for camp in candidates)


class CampGold:
    """Gold each camp pays, learned across all champions and routes (camp gold doesn't depend on them)."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.samples: dict[str, list[float]] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.samples = {}

    def expected(self, camp: str) -> tuple[float, bool]:
        """(gold, whether it was learned rather than the known default). Samples far from the camp's
        known gold, saved by runs that split a camp early, are ignored."""
        samples = [g for g in self.samples.get(camp_key(camp), []) if plausible_camp_gold(camp, g)]
        if samples:
            return median(samples), True
        return DEFAULT_CAMP_GOLD.get(camp_key(camp), FALLBACK_CAMP_GOLD), False

    def learn(self, camps: list[str], golds: list[float]) -> None:
        for camp, gold in zip(camps, golds):
            if camp_key(camp) != RECALL and gold >= MIN_CAMP_GOLD and plausible_camp_gold(camp, gold):
                key = camp_key(camp)
                self.samples[key] = (self.samples.get(key, []) + [round(gold, 1)])[-GOLD_SAMPLES_KEPT:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.samples, indent=2), encoding="utf-8")


def step_cost(step: Step, camp: str, camp_gold: CampGold) -> float:
    is_recall = camp_key(camp) == RECALL
    if (step.kind == "recall") != is_recall:
        return IMPOSSIBLE
    if is_recall:
        return 0.0
    cost = 0.0
    expects_multi = camp_key(camp) in MULTI_MONSTER_CAMPS
    if step.multi and not expects_multi:
        cost += SINGLE_SEEN_AS_MULTI
    elif not step.multi and expects_multi:
        cost += MULTI_SEEN_AS_SINGLE
    expected, learned = camp_gold.expected(camp)
    candidates = (expected, *OTHER_CAMP_GOLD.get(camp_key(camp), ()))
    gold_cost = min(MAX_GOLD_COST, min(abs(step.gold - gold) / gold * GOLD_COST_WEIGHT for gold in candidates))
    # Known camp gold is measured from real clears, so it counts fully even before any is learned.
    return cost + gold_cost


def route_cost(steps: list[Step], camps: list[str], camp_gold: CampGold) -> float:
    if len(steps) > len(camps):
        return IMPOSSIBLE
    return sum(step_cost(step, camp, camp_gold) for step, camp in zip(steps, camps))


def best_route(steps: list[Step], routes: list, current, camp_gold: CampGold):
    """The route the steps so far fit best, or None to keep the current one. Ties keep the
    current route, then follow the given order."""
    if not steps or not routes:
        return None
    costs = [(route_cost(steps, list(r.camps), camp_gold), i, r) for i, r in enumerate(routes)]
    current_cost = next((c for c, _, r in costs if r.path == current.path), IMPOSSIBLE)
    cost, _, route = min(costs, key=lambda item: item[:2])
    if cost == IMPOSSIBLE or route.path == current.path or current_cost - cost < SWITCH_MARGIN:
        return None
    return route
