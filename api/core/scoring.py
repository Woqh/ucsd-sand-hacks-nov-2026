"""Analytics derived from state-transition events. Pure.

Everything here works from the `events` rows (kind='transition' carries from/to state and a
timestamp), so it behaves identically for real, simulated and seeded data.

Posture score (the explainable formula the UI shows):
    seated time = time in GOOD + DEVIATING + SLOUCHING   (AWAY is excluded)
    score       = 100 x (GOOD + DEVIATING) / seated time
i.e. "the % of the time you were sitting that you weren't slouching". DEVIATING is the grace
window the user chose, so short lapses under their slouch threshold are not penalised.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from api.core.state_machine import AWAY, DEVIATING, GOOD, SLOUCHING

DAY_MS = 86_400_000
HOUR_MS = 3_600_000
GOOD_THRESHOLD_PCT = 70   # "on track" line for the outlook, day streaks and the daily goal
LONG_AWAY_MS = 120_000    # an away gap at least this long counts as a real break
OPEN_GRACE_MS = 15_000    # phone heard from this recently => the open segment extends to "now"


@dataclass(frozen=True)
class Segment:
    state: str
    start: int
    end: int

    @property
    def dur(self) -> int:
        return self.end - self.start


# ------------------------------------------------------------------ segments

def build_segments(events: Iterable[dict[str, Any]], prior_event: Optional[dict[str, Any]],
                   since: int, until: int, last_seen_ms: Optional[int] = None) -> list[Segment]:
    """Turn transition events into contiguous (state, start, end) segments over [since, until).

    `prior_event` is the last event before `since` (gives the opening state; None -> AWAY).
    `last_seen_ms`: the open final segment can't extend past the last time we heard from the phone
    (nothing runs in the background to emit AWAY), so anything after it is AWAY.
    """
    evs = sorted((e for e in events if e.get("kind", "transition") == "transition"
                  and since <= e["t"] < until), key=lambda e: e["t"])
    cur_state = prior_event["to_state"] if prior_event else (evs[0]["from_state"] if evs else AWAY)
    cur_start = since
    segs: list[Segment] = []
    for e in evs:
        if e["t"] > cur_start:
            segs.append(Segment(cur_state, cur_start, e["t"]))
            cur_start = e["t"]
        cur_state = e["to_state"]
    end = until
    # Only cut the open segment short if the phone has actually gone quiet. A live phone's last
    # sample is always a moment behind `until`, which must not read as a sliver of AWAY.
    if last_seen_ms is not None and cur_state != AWAY and until - last_seen_ms > OPEN_GRACE_MS:
        end = max(cur_start, min(until, last_seen_ms))
    if end > cur_start:
        segs.append(Segment(cur_state, cur_start, end))
    if end < until:
        segs.append(Segment(AWAY, max(end, cur_start), until))
    return segs


def clip(segs: Iterable[Segment], a: int, b: int) -> list[Segment]:
    out = []
    for s in segs:
        lo, hi = max(s.start, a), min(s.end, b)
        if hi > lo:
            out.append(Segment(s.state, lo, hi))
    return out


def split_at(segs: Iterable[Segment], bucket_ms: int, offset_ms: int) -> list[tuple[int, Segment]]:
    """Split segments at local bucket boundaries. Returns (bucket_index, segment) pairs where
    bucket_index = floor((t + offset) / bucket_ms)."""
    out: list[tuple[int, Segment]] = []
    for s in segs:
        cur = s.start
        while cur < s.end:
            idx = (cur + offset_ms) // bucket_ms
            boundary = (idx + 1) * bucket_ms - offset_ms
            nxt = min(s.end, boundary)
            out.append((idx, Segment(s.state, cur, nxt)))
            cur = nxt
    return out


# ------------------------------------------------------------------ summaries

def _totals(segs: Iterable[Segment]) -> dict[str, float]:
    t = {GOOD: 0.0, DEVIATING: 0.0, SLOUCHING: 0.0, AWAY: 0.0}
    for s in segs:
        t[s.state] = t.get(s.state, 0.0) + s.dur / 1000
    return t


def good_pct(good_sec: float, seated_sec: float) -> Optional[float]:
    return None if seated_sec <= 0 else round(100 * good_sec / seated_sec, 1)


def summarize(segs: list[Segment], events: Iterable[dict[str, Any]], since: int, until: int) -> dict[str, Any]:
    tot = _totals(segs)
    seated = tot[GOOD] + tot[DEVIATING] + tot[SLOUCHING]
    pct = good_pct(tot[GOOD] + tot[DEVIATING], seated)
    evs = sorted((e for e in events if since <= e["t"] < until), key=lambda e: e["t"])
    slouch_events = sum(1 for e in evs if e.get("kind", "transition") == "transition"
                        and e["to_state"] == SLOUCHING)
    return {
        "score": None if pct is None else int(round(pct)),
        "goodPct": pct,
        "seatedSec": round(seated),
        "goodSec": round(tot[GOOD]),
        "graceSec": round(tot[DEVIATING]),
        "slouchSec": round(tot[SLOUCHING]),
        "awaySec": round(tot[AWAY]),
        "slouchEvents": slouch_events,
        "slouchEventsPerHour": round(slouch_events / (seated / 3600), 2) if seated >= 60 else None,
        "longestGoodStreakSec": longest_good_streak(segs),
        "avgRecoverySec": avg_recovery_sec(evs),
    }


def longest_good_streak(segs: Iterable[Segment]) -> int:
    """Longest run of seated time without slouching. AWAY pauses the streak, SLOUCHING resets it."""
    best = run = 0.0
    for s in sorted(segs, key=lambda s: s.start):
        if s.state in (GOOD, DEVIATING):
            run += s.dur / 1000
            best = max(best, run)
        elif s.state == SLOUCHING:
            run = 0.0
    return int(round(best))


def avg_recovery_sec(events: list[dict[str, Any]]) -> Optional[float]:
    """Mean seconds from an alert to the user sitting back up (GOOD). Alerts that ended with the
    user walking away (or are still unresolved) are skipped."""
    times = []
    for i, e in enumerate(events):
        if not e.get("alert"):
            continue
        for nxt in events[i + 1:]:
            if nxt.get("kind", "transition") != "transition":
                continue
            if nxt["to_state"] == GOOD:
                times.append((nxt["t"] - e["t"]) / 1000)
            if nxt["to_state"] in (GOOD, AWAY):
                break
    return round(sum(times) / len(times), 1) if times else None


def daily_breakdown(segs: list[Segment], tz_offset_min: int) -> list[dict[str, Any]]:
    off = tz_offset_min * 60_000
    days: dict[int, dict[str, float]] = {}
    for idx, s in split_at(segs, DAY_MS, off):
        d = days.setdefault(idx, {GOOD: 0.0, DEVIATING: 0.0, SLOUCHING: 0.0, AWAY: 0.0})
        d[s.state] += s.dur / 1000
    out = []
    for idx in sorted(days):
        d = days[idx]
        seated = d[GOOD] + d[DEVIATING] + d[SLOUCHING]
        pct = good_pct(d[GOOD] + d[DEVIATING], seated)
        out.append({"date": date_str(idx), "dayIndex": idx, "seatedSec": round(seated),
                    "goodPct": pct, "score": None if pct is None else int(round(pct))})
    return out


def fill_days(daily: list[dict[str, Any]], first_idx: int, last_idx: int) -> list[dict[str, Any]]:
    """Ensure one entry per day in [first_idx, last_idx] (empty days have null scores)."""
    by = {d["dayIndex"]: d for d in daily}
    return [by.get(i, {"date": date_str(i), "dayIndex": i, "seatedSec": 0, "goodPct": None, "score": None})
            for i in range(first_idx, last_idx + 1)]


def heatmap(segs: list[Segment], tz_offset_min: int) -> list[dict[str, Any]]:
    """Weekday x hour-of-day grid of good-posture %. day: 0 = Monday ... 6 = Sunday."""
    off = tz_offset_min * 60_000
    cells: dict[tuple[int, int], dict[str, float]] = {}
    for idx, s in split_at(segs, HOUR_MS, off):
        if s.state == AWAY:
            continue
        day_idx, hour = divmod(idx, 24)
        key = ((day_idx + 3) % 7, hour)  # 1970-01-01 was a Thursday
        c = cells.setdefault(key, {"seated": 0.0, "good": 0.0})
        c["seated"] += s.dur / 1000
        if s.state in (GOOD, DEVIATING):
            c["good"] += s.dur / 1000
    return [{"day": d, "hour": h, "seatedSec": round(c["seated"]),
             "goodPct": good_pct(c["good"], c["seated"])} for (d, h), c in sorted(cells.items())]


def day_streak(daily: list[dict[str, Any]], today_idx: int) -> int:
    """Consecutive days at/above GOOD_THRESHOLD_PCT, ending today (or yesterday if today hasn't
    qualified yet: today is still in progress and never breaks a streak). Days with no data are
    skipped, a below-threshold day breaks it."""
    by = {d["dayIndex"]: d for d in daily}
    streak = 0
    today = by.get(today_idx)
    if today and today["goodPct"] is not None and today["goodPct"] >= GOOD_THRESHOLD_PCT:
        streak += 1
    idx = today_idx - 1
    earliest = min(by) if by else today_idx
    while idx >= earliest:
        d = by.get(idx)
        if d and d["goodPct"] is not None:
            if d["goodPct"] >= GOOD_THRESHOLD_PCT:
                streak += 1
            else:
                break
        idx -= 1
    return streak


def next_goal_pct(previous_pct: Optional[float]) -> int:
    """Progressive goal: the next multiple of 5 above last period's result (60 -> 65), capped at 95."""
    if previous_pct is None:
        return 60
    return min(95, (int(math.floor(previous_pct / 5)) + 1) * 5)


def sitting_run_sec(segs: list[Segment], until: int) -> int:
    """How long they've been sitting since their last real break (an AWAY gap >= 2 min).
    0 if they're away right now."""
    ordered = sorted(segs, key=lambda s: s.start)
    if not ordered or ordered[-1].state == AWAY:
        return 0
    run_start = ordered[0].start
    for s in ordered:
        if s.state == AWAY and s.dur >= LONG_AWAY_MS:
            run_start = s.end
    return max(0, int(round((until - run_start) / 1000)))


def outlook(score: Optional[int]) -> dict[str, Any]:
    status = "no_data" if score is None else ("on_track" if score >= GOOD_THRESHOLD_PCT else "at_risk")
    return {"status": status, "thresholdPct": GOOD_THRESHOLD_PCT}


def date_str(day_idx: int) -> str:
    from datetime import date, timedelta
    return (date(1970, 1, 1) + timedelta(days=day_idx)).isoformat()
