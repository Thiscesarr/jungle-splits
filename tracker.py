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
# Bigger jumps come from the Practice Tool "add gold" button or selling items.
MAX_KILL_GOLD = 400.0
# Before a camp's gold is learned, a quiet window only closes the camp once this share of the
# rough default gold arrived, so a pause mid-camp (krugs splitting) does not split too early.
MIN_GOLD_FRACTION = 0.5
FALLBACK_CAMP_GOLD = 60.0
GOLD_SAMPLES_KEPT = 5
# Rough per-camp gold, only used until a full run teaches the real values.
DEFAULT_CAMP_GOLD = {
    "red": 90, "blue": 90, "gromp": 80, "wolves": 85, "raptors": 85, "krugs": 100, "scuttle": 55,
}
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
            self._load(json.loads(path.read_text(encoding="utf-8")))

    def _load(self, data: dict) -> None:
        if data.get("camps") != self.camps:
            # The route was edited, so per-camp comparisons no longer line up: keep a backup, start over.
            self.path.rename(self.path.with_name(f"{self.path.stem}.{int(time.time())}.bak.json"))
            return
        self.pb = data.get("pb")
        self.best_segments = data.get("best_segments", self.best_segments)
        self.gold_samples = data.get("gold_samples", self.gold_samples)
        self.attempts = data.get("attempts", 0)
        self.completed = data.get("completed", 0)
        self.history = data.get("history", [])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "camps": self.camps,
            "pb": self.pb,
            "best_segments": self.best_segments,
            "gold_samples": self.gold_samples,
            "attempts": self.attempts,
            "completed": self.completed,
            "history": self.history,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def expected_gold(self, i: int) -> float | None:
        """Gold of a fully cleared camp, learned from finished runs."""
        return max(self.gold_samples[i]) if self.gold_samples[i] else None

    def reference_gold(self, i: int) -> float:
        return self.expected_gold(i) or DEFAULT_CAMP_GOLD.get(camp_key(self.camps[i]), FALLBACK_CAMP_GOLD)


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
        self.new_pb = False

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
            self.stats.attempts += 1
            self.stats.save()
        if self.state != RUNNING:
            return

        dt = max(0.0, game_time - prev_time)
        passive = PASSIVE_GOLD_PER_SEC * dt if game_time > PASSIVE_GOLD_START else 0.0
        gold_delta = gold - prev_gold
        kill_gold = gold_delta - passive
        if not MIN_KILL_GOLD <= kill_gold <= MAX_KILL_GOLD:
            kill_gold = 0.0
        cs_gain = cs - prev_cs if cs is not None and prev_cs is not None and cs > prev_cs else 0
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
        expected = self.stats.expected_gold(i)
        if kill_gold and expected is not None and self.seg_gold >= expected - 1.5:
            self._split(t, manual=False)
            return
        if (self.last_gold_time is not None
                and t - self.last_gold_time >= self.quiet_window
                and self.seg_gold >= MIN_GOLD_FRACTION * self.stats.reference_gold(i)):
            # Gold stopped arriving while walking to the next camp: the camp ended on its last kill.
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
            if split.gold >= 20:
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

    def verdict(self, now: float) -> tuple[str | None, float | None, float | None]:
        """'reset' when even the best segments can't beat the target, 'on_pace' when PB pace
        beats it, 'possible' otherwise."""
        if self.state != RUNNING:
            return None, None, None
        pace, best = self.projection(now)
        if best is not None and best > self.target:
            return "reset", pace, best
        if pace is not None and pace <= self.target:
            return "on_pace", pace, best
        if best is not None:
            return "possible", pace, best
        return None, pace, best
