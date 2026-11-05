"""Clear tracking: auto-splits on CS (or monster gold) and compares each camp against PB and best segments."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

# Passive income is ~2.04 g/s; anything clearly above it in one sample is monster gold.
PASSIVE_GOLD_PER_SEC = 2.1
PASSIVE_GOLD_START = 65.0
MIN_KILL_GOLD = 3.0
# A whole camp pays at most ~110 gold, so bigger jumps come from the Practice Tool "add gold"
# button or from selling / undoing items at the shop.
MAX_KILL_GOLD = 150.0
# A camp only closes once at most half of its smallest monster's gold is missing. Multi-monster camps
# pay out monster by monster, often with pauses (small wolves die, the big one takes a few seconds
# more), so closing on part of the gold would close the camp early and shift every later split by one
# camp; a small raptor is only 8 gold, so the margin must follow the camp, not a fixed share.
SMALLEST_MONSTER_GOLD = {"wolves": 15, "raptors": 8, "krugs": 10}
# If a patch changes how much a camp pays, the camp still closes after a longer pause (and the real
# value is learned from that run).
FALLBACK_QUIET = 5.0
# A camp closes on the kill that completes its gold (read to about a gold; the smallest monster is 8).
FULL_CAMP_MARGIN = 2.5
FALLBACK_FRACTION = 0.85
FALLBACK_CAMP_GOLD = 60.0
GOLD_SAMPLES_KEPT = 5
# Gold a fully cleared camp pays (patch 26), measured monster by monster in the debug logs of real
# Practice Tool clears (9 clears, both sides, starting at level 1, 2 and 4): the same every time,
# whatever the game time or level. Wolves: 55 + 15 + 15. Raptors: 35 + 5 x 8. Krugs: 10 + 15 + 6 x 14.
DEFAULT_CAMP_GOLD = {
    "red": 90, "blue": 90, "gromp": 80, "wolves": 85, "raptors": 75, "krugs": 109, "scuttle": 55,
}
# Other totals a camp can end on: once the big wolf dies, a lesser wolf left behind despawns (55 + 15).
# Such a camp closes after the longer fallback pause, so a camp still being cleared gets time to finish.
OTHER_CAMP_GOLD = {"wolves": (70,)}
OTHER_CAMP_MARGIN = 0.05
# Once per clear, between 2:30 and 3:00 in every logged clear, the game pays a lone 20 gold half a
# second after a monster dies, at whatever camp the player is on. It belongs to no camp: counted as
# camp gold it made Red (90 + 20) look like Krugs and closed camps early. No monster, or monsters dying
# together, pays 18.5-21.5 gold (camps pay 8, 10, 14, 15, 35, 55 and sums of those, or 80/90).
BONUS_GOLD = (18.5, 21.5)
BONUS_DELAY = (0.3, 0.9)
# A learned value further than this from the camp's known gold came from a mis-split run.
PLAUSIBLE_GOLD_SPREAD = 0.15
MULTI_MONSTER_CAMPS = {"wolves", "raptors", "krugs"}
CAMP_ALIASES = {"raptor": "raptors", "krug": "krugs", "wolf": "wolves", "grompe": "gromp", "scuttler": "scuttle"}
RECALL = "recall"
# Any gold drop this big during a Recall step is a purchase at the shop.
PURCHASE_GOLD = 20.0

PURPLE, GREEN, RED = "purple", "green", "red"
WAITING, RUNNING, FINISHED, ABANDONED = "waiting", "running", "finished", "abandoned"
# CS tracking: "ok" once CS is seen moving 1..cs_per_camp at a time, "broken" if the game only
# reports it in big batches; until then ("unknown") camps close on gold.
CS_UNKNOWN, CS_OK, CS_BROKEN = "unknown", "ok", "broken"


def camp_key(name: str) -> str:
    key = name.strip().lower()
    return CAMP_ALIASES.get(key, key)


def plausible_camp_gold(camp: str, gold: float) -> bool:
    """Whether gold looks like one whole clear of that camp (camps without a known value always pass)."""
    known = DEFAULT_CAMP_GOLD.get(camp_key(camp))
    return known is None or abs(gold - known) <= known * PLAUSIBLE_GOLD_SPREAD


def median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def sample_gains(prev: tuple[float, float, int | None], cur: tuple[float, float, int | None],
                 ) -> tuple[float, float, int]:
    """(gold delta, monster gold, CS gained) between two (game time, gold, cs) samples."""
    (prev_time, prev_gold, prev_cs), (game_time, gold, cs) = prev, cur
    dt = max(0.0, game_time - prev_time)
    passive = PASSIVE_GOLD_PER_SEC * dt if game_time > PASSIVE_GOLD_START else 0.0
    gold_delta = gold - prev_gold
    kill_gold = gold_delta - passive
    if not MIN_KILL_GOLD <= kill_gold <= MAX_KILL_GOLD:
        kill_gold = 0.0
    cs_gain = cs - prev_cs if cs is not None and prev_cs is not None and cs > prev_cs else 0
    return gold_delta, kill_gold, cs_gain


class BonusFilter:
    """Takes the once-per-clear bonus (BONUS_GOLD) out of the monster gold."""

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.last_kill: float | None = None
        self.seen = False

    def __call__(self, t: float, kill_gold: float) -> float:
        if not kill_gold:
            return 0.0
        if (not self.seen and self.last_kill is not None and BONUS_DELAY[0] <= t - self.last_kill <= BONUS_DELAY[1]
                and BONUS_GOLD[0] <= kill_gold <= BONUS_GOLD[1]):
            self.seen = True
            return 0.0
        self.last_kill = t
        return kill_gold


def parse_clock(value: str | float) -> float:
    """'2:50.0' -> 170.0; plain numbers are seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    minutes, _, seconds = value.strip().rpartition(":")
    return int(minutes or 0) * 60 + float(seconds)


def fmt_clock(seconds: float | None) -> str:
    if seconds is None:
        return "-:--.-"
    seconds = max(0.0, seconds)
    minutes, rest = divmod(round(seconds, 1), 60)
    return f"{int(minutes)}:{rest:04.1f}"


def fmt_delta(delta: float | None) -> str:
    if delta is None:
        return ""
    sign = "-" if delta < 0 else "+"
    delta = abs(delta)
    if delta >= 60:
        return sign + fmt_clock(delta)
    return f"{sign}{delta:.1f}"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "route"


def segments_of(times: list[float], start: float) -> list[float]:
    return [t - p for t, p in zip(times, [start] + times[:-1])]


class RunClock:
    """Turns the game clock into the clock of the current attempt.

    The Practice Tool's Reset Game puts the champion back to level 1 with an empty inventory and
    starting gold, but leaves the game clock running and respawns the camps on the usual timer.
    So a reset starts a fresh clock at 0:00, and camps spawn at 0:55 of it, like in a new game.
    """

    STARTING_GOLD = 500.0

    def __init__(self):
        self.offset = 0.0
        self.prev: tuple[float, float, int | None, int | None] | None = None

    def run_time(self, game_time: float, gold: float, level: int | None = None, items: int | None = None) -> float:
        prev, self.prev = self.prev, (game_time, gold, level, items)
        if prev is not None:
            prev_time, prev_gold, prev_level, prev_items = prev
            if game_time < prev_time - 1.0:
                self.offset = 0.0  # a new game: the real clock starts over by itself
            elif self._was_reset(prev_gold, prev_level, prev_items, gold, level, items):
                self.offset = game_time
        return game_time - self.offset

    def _was_reset(self, prev_gold, prev_level, prev_items, gold, level, items) -> bool:
        if level is not None and prev_level is not None and level < prev_level:
            return True
        if items is not None and prev_items and items == 0 and gold > prev_gold:
            return True
        return gold - prev_gold > 200 and abs(gold - self.STARTING_GOLD) < 1.0

    def restart(self) -> None:
        """Starts the attempt clock now (the 'new run' hotkey)."""
        if self.prev is not None:
            self.offset = self.prev[0]


@dataclass
class Split:
    time: float
    gold: float
    cs: int
    segment: float
    color: str
    segment_delta: float | None
    total_delta: float | None
    prev_best: float | None
    manual: bool


class RouteStats:
    """PB, best segments and learned camp gold for one route, persisted as JSON."""

    def __init__(self, path: Path, camps: list[str]):
        self.path = path
        self.camps = list(camps)
        n = len(camps)
        self.pb: list[float] | None = None
        self.best_segments: list[float | None] = [None] * n
        self.gold_samples: list[list[float]] = [[] for _ in range(n)]
        self.attempts = 0
        self.completed = 0
        self.history: list[dict] = []
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                # Damaged (e.g. power cut mid-save): keep it aside for inspection and start this route over.
                path.replace(path.with_name(f"{path.stem}.{int(time.time())}.corrupt.json"))
                return
            self._load(data)

    def _load(self, data: dict) -> None:
        if data.get("camps") != self.camps:
            # The route was edited, so per-camp comparisons no longer line up: keep a backup, start over.
            self.path.rename(self.path.with_name(f"{self.path.stem}.{int(time.time())}.bak.json"))
            return
        self.restore(data)

    def restore(self, data: dict) -> None:
        self.pb = data.get("pb")
        self.best_segments = data.get("best_segments", self.best_segments)
        self.gold_samples = data.get("gold_samples", self.gold_samples)
        self.attempts = data.get("attempts", 0)
        self.completed = data.get("completed", 0)
        self.history = data.get("history", [])

    def to_dict(self) -> dict:
        return {
            "camps": self.camps,
            "pb": self.pb,
            "best_segments": self.best_segments,
            "gold_samples": self.gold_samples,
            "attempts": self.attempts,
            "completed": self.completed,
            "history": self.history,
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def expected_gold(self, i: int) -> float | None:
        """Gold of a fully cleared camp, learned from finished runs. Samples far from the camp's known
        gold (left by runs that split a camp too early) are ignored."""
        samples = [g for g in self.gold_samples[i] if plausible_camp_gold(self.camps[i], g)]
        return median(samples) if samples else None

    def reference_gold(self, i: int) -> float:
        return self.expected_gold(i) or DEFAULT_CAMP_GOLD.get(camp_key(self.camps[i]), FALLBACK_CAMP_GOLD)

    def complete_gold(self, i: int) -> float:
        """Gold after which camp i counts as cleared."""
        reference = self.reference_gold(i)
        return reference - SMALLEST_MONSTER_GOLD.get(camp_key(self.camps[i]), reference) / 2

    def fallback_gold(self, i: int) -> float:
        """Gold after which camp i counts as cleared once gold has been quiet for FALLBACK_QUIET."""
        others = OTHER_CAMP_GOLD.get(camp_key(self.camps[i]), ())
        return min([FALLBACK_FRACTION * self.reference_gold(i)]
                   + [gold * (1 - OTHER_CAMP_MARGIN) for gold in others])


class Tracker:
    def __init__(self, stats: RouteStats, camp_spawn: float = 55.0, target: float = 170.0,
                 quiet_window: float = 2.0, cs_per_camp: int = 4, cs_state: str = CS_UNKNOWN):
        self.stats = stats
        self.camp_spawn = camp_spawn
        self.target = target
        self.quiet_window = quiet_window
        self.cs_per_camp = cs_per_camp
        self.cs_state = cs_state
        self.game_time: float | None = None
        self.gold: float | None = None
        self.cs: int | None = None
        self._reset_run(WAITING)

    @property
    def camps(self) -> list[str]:
        return self.stats.camps

    def _reset_run(self, state: str) -> None:
        self.state = state
        self.splits: list[Split] = []
        self.seg_gold = 0.0
        self.seg_cs = 0
        self.last_gold_time: float | None = None
        self.bonus = BonusFilter()
        self.new_pb = False
        self._stats_before_run: dict | None = None

    def _idle_state(self) -> str:
        return WAITING if self.game_time is None or self.game_time < self.camp_spawn else ABANDONED

    # --- input -------------------------------------------------------------------------------

    def is_recall(self, i: int) -> bool:
        return i < len(self.camps) and camp_key(self.camps[i]) == RECALL

    def feed(self, game_time: float, gold: float, cs: int | None = None) -> None:
        prev_time, prev_gold, prev_cs = self.game_time, self.gold, self.cs
        self.game_time, self.gold, self.cs = game_time, gold, cs
        if prev_time is None or game_time < prev_time - 1.0:
            # First sample, a new game or a Practice Tool reset: a run can only start before camps spawn.
            self._reset_run(self._idle_state())
            return
        if self.state == WAITING and game_time >= self.camp_spawn:
            self.state = RUNNING
            self._stats_before_run = json.loads(json.dumps(self.stats.to_dict()))
            self.stats.attempts += 1
            self.stats.save()
        if self.state != RUNNING:
            return

        gold_delta, kill_gold, cs_gain = sample_gains((prev_time, prev_gold, prev_cs), (game_time, gold, cs))
        kill_gold = self.bonus(game_time, kill_gold)
        if cs_gain:
            if cs_gain > self.cs_per_camp:
                self.cs_state = CS_BROKEN
            elif self.cs_state == CS_UNKNOWN:
                self.cs_state = CS_OK

        if self.is_recall(len(self.splits)):
            # The recall ends at the first purchase; walking straight to a camp skips the shop.
            if gold_delta <= -PURCHASE_GOLD or kill_gold or cs_gain:
                self._split(game_time, manual=False)
            if self.state != RUNNING or not (kill_gold or cs_gain):
                return
        self._camp_progress(game_time, kill_gold, cs_gain)

    def _camp_progress(self, t: float, kill_gold: float, cs_gain: int) -> None:
        if kill_gold and self.cs_state != CS_OK and self._gold_says_cleared(t, kill_gold):
            # Gold was quiet long enough before this kill, or this kill would pay more than the whole
            # camp: the camp ended on its last kill and this kill is the next camp's first.
            self._close_on_gold()
            if self.state == RUNNING and self.is_recall(len(self.splits)):
                self._split(t, manual=False)  # walking straight to a camp skips the shop
            if self.state != RUNNING:
                return
        i = len(self.splits)
        if kill_gold:
            self.seg_gold += kill_gold
            self.last_gold_time = t
        self.seg_cs += cs_gain
        if self.cs_state == CS_OK:
            if self.seg_cs >= self.cs_per_camp:
                carry = self.seg_cs - self.cs_per_camp
                self._split(t, manual=False)
                if not self.is_recall(i + 1):
                    self.seg_cs = carry
            return
        if kill_gold and self.seg_gold >= self.stats.reference_gold(i) - FULL_CAMP_MARGIN:
            # The camp paid all its gold: no monster is left, close it now instead of after a pause.
            self._split(t, manual=False)
            return
        if self._gold_says_cleared(t):
            # Gold stopped arriving while walking to the next camp: the camp ended on its last kill.
            self._close_on_gold()

    def _gold_says_cleared(self, t: float, next_kill: float = 0.0) -> bool:
        """Whether the camp ended on its last kill, judged at time t (before next_kill counts)."""
        if self.last_gold_time is None:
            return False
        i, quiet = len(self.splits), t - self.last_gold_time
        overshoot = self.seg_gold + next_kill > self.stats.reference_gold(i) * (1 + OTHER_CAMP_MARGIN)
        return ((quiet >= self.quiet_window and self.seg_gold >= self.stats.complete_gold(i))
                or (quiet >= self.quiet_window and next_kill and overshoot
                    and self.seg_gold >= self.stats.fallback_gold(i))
                or (quiet >= FALLBACK_QUIET and self.seg_gold >= self.stats.fallback_gold(i)))

    def _close_on_gold(self) -> None:
        if self.cs_state == CS_UNKNOWN and self.cs is not None and self.seg_cs == 0:
            self.cs_state = CS_BROKEN  # a whole camp died and the CS did not move
        self._split(self.last_gold_time, manual=False)

    def manual_split(self) -> None:
        if self.state == RUNNING and self.game_time is not None:
            self._split(self.game_time, manual=True)

    def undo(self) -> None:
        if self.state != RUNNING or not self.splits:
            return
        split = self.splits.pop()
        i = len(self.splits)
        self.stats.best_segments[i] = split.prev_best
        self.stats.save()
        self.seg_gold += split.gold
        self.seg_cs += split.cs
        self.last_gold_time = None

    def reset(self) -> None:
        """Discard the current run; the next one starts when the game clock goes back before spawn."""
        self._reset_run(self._idle_state())

    def discard_run(self) -> None:
        """Undo everything the current run wrote to this route's stats (it is being replayed elsewhere)."""
        if self._stats_before_run is not None:
            self.stats.restore(self._stats_before_run)
            self.stats.save()
        self._reset_run(self._idle_state())

    # --- splitting ---------------------------------------------------------------------------

    def pb_segments(self) -> list[float] | None:
        return segments_of(self.stats.pb, self.camp_spawn) if self.stats.pb else None

    def _split(self, t: float, manual: bool) -> None:
        i = len(self.splits)
        prev = self.splits[-1].time if self.splits else self.camp_spawn
        segment = t - prev
        best = self.stats.best_segments[i]
        pb_segs = self.pb_segments()
        pb_seg = pb_segs[i] if pb_segs else None
        if best is None or segment <= best:
            color = PURPLE
        elif pb_seg is not None and segment <= pb_seg:
            color = GREEN
        else:
            color = RED
        self.splits.append(Split(
            time=t,
            gold=self.seg_gold,
            cs=self.seg_cs,
            segment=segment,
            color=color,
            segment_delta=segment - pb_seg if pb_seg is not None else None,
            total_delta=t - self.stats.pb[i] if self.stats.pb else None,
            prev_best=best,
            manual=manual,
        ))
        if best is None or segment < best:
            self.stats.best_segments[i] = segment
        self.seg_gold = 0.0
        self.seg_cs = 0
        self.last_gold_time = None
        if len(self.splits) == len(self.camps):
            self._finish()
        else:
            self.stats.save()

    def _finish(self) -> None:
        self.state = FINISHED
        stats = self.stats
        total = self.splits[-1].time
        stats.completed += 1
        for i, split in enumerate(self.splits):
            if camp_key(self.camps[i]) != RECALL and plausible_camp_gold(self.camps[i], split.gold):
                stats.gold_samples[i] = (stats.gold_samples[i] + [round(split.gold, 1)])[-GOLD_SAMPLES_KEPT:]
        self.new_pb = stats.pb is None or total < stats.pb[-1]
        if self.new_pb:
            stats.pb = [s.time for s in self.splits]
        stats.history.append({
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total": round(total, 2),
            "splits": [round(s.time, 2) for s in self.splits],
            "colors": [s.color for s in self.splits],
        })
        stats.save()

    # --- live comparison ---------------------------------------------------------------------

    def total(self) -> float | None:
        return self.splits[-1].time if self.state == FINISHED else None

    def sum_of_best(self) -> float | None:
        best = self.stats.best_segments
        return None if any(b is None for b in best) else self.camp_spawn + sum(best)

    def live_total_delta(self, now: float) -> float | None:
        """How far behind the PB split the current camp already is (None while still ahead)."""
        i = len(self.splits)
        if self.state != RUNNING or not self.stats.pb or now <= self.stats.pb[i]:
            return None
        return now - self.stats.pb[i]

    def projection(self, now: float) -> tuple[float | None, float | None]:
        """(finish at PB pace, best possible finish) for the running run."""
        i = len(self.splits)
        last = self.splits[-1].time if self.splits else self.camp_spawn
        elapsed = max(0.0, now - last)

        def finish_with(segs):
            if segs is None or any(s is None for s in segs[i:]):
                return None
            return last + max(elapsed, segs[i]) + sum(segs[i + 1:])

        return finish_with(self.pb_segments()), finish_with(self.stats.best_segments)

    def current_delta(self, now: float | None) -> float | None:
        """Overall gain (-) or loss (+) against the PB right now, like LiveSplit's delta: the last
        split's delta, or more once the current camp is already slower than the PB split."""
        if not self.stats.pb or not self.splits and self.state != RUNNING:
            return None
        last = self.splits[-1].total_delta if self.splits else 0.0
        if self.state != RUNNING or now is None:
            return last
        live = self.live_total_delta(now)
        return max(last, live) if live is not None else last

    def verdict(self, now: float, reset_margin: float = 2.0) -> tuple[str | None, float | None, float | None]:
        """(verdict, finish at PB pace, best possible finish) for the running run:
        'reset' when even the best segments from here can't get within reset_margin of the PB,
        'on_target' when PB pace beats the target, 'ahead'/'behind' of the PB otherwise."""
        if self.state != RUNNING or not self.stats.pb:
            return None, None, None
        pb_total = self.stats.pb[-1]
        pace, best = self.projection(now)
        if best is not None and best > pb_total + reset_margin:
            return "reset", pace, best
        if pace <= self.target:
            return "on_target", pace, best
        return ("ahead" if pace <= pb_total else "behind"), pace, best
