"""Personal coaching analytics: how THIS person sits, and how THEY respond to being coached. Pure.

Everything here is derived from the person's own events/segments, so it is personalized by
construction. Conventions: a "run" is one seated stretch (broken by an away gap of 2+ minutes);
times are epoch ms; `tz_offset_min` is minutes east of UTC (local = UTC + offset). Functions return
plain dicts of numbers and short labels, with None wherever there isn't enough data to say
anything, because the honest answer to a thin history is "not enough data yet", not a guess.
None of it is a medical statement: it describes habits, not health.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from api.core import scoring
from api.core.scoring import GOOD_THRESHOLD_PCT, LONG_AWAY_MS, Segment
from api.core.state_machine import AWAY, DEVIATING, GOOD, SLOUCHING

DAY_MS = scoring.DAY_MS
HOUR_MS = scoring.HOUR_MS
MICRO_BREAK_MIN_MS = 20_000          # an away gap this long (but under LONG_AWAY_MS) is a micro-break
SIT_TARGET_MIN = 45                  # a common suggestion; see docs/health-claims.md (a prompt, not a rule)
BUCKET_MIN = 10                      # fatigue-curve bucket width
CURVE_MAX_MIN = 120                  # the last bucket is "120+"
MIN_BUCKET_SEATED_SEC = 300          # don't report a bucket with less than 5 minutes behind it
MIN_NUDGES = 3                       # don't report a rate from fewer nudges than this
PARTS_OF_DAY = ("morning", "afternoon", "evening")


# ----------------------------------------------------------------------------- time helpers

def local_hour(t_ms: int, tz_offset_min: int) -> int:
    return int(((t_ms + tz_offset_min * 60_000) // HOUR_MS) % 24)


def part_of_day(hour: int) -> str:
    return "morning" if hour < 12 else ("afternoon" if hour < 17 else "evening")


def _median(xs: Sequence[float]) -> Optional[float]:
    return round(float(statistics.median(xs)), 1) if xs else None


def _pct(num: float, den: float) -> Optional[float]:
    return None if den <= 0 else round(100 * num / den, 1)


# ----------------------------------------------------------------------------- seated runs

@dataclass
class Run:
    start: int
    end: int
    segs: list[Segment] = field(default_factory=list)   # non-AWAY segments only

    @property
    def seated_sec(self) -> float:
        return sum(s.dur for s in self.segs) / 1000

    @property
    def minutes(self) -> float:
        return (self.end - self.start) / 60_000


def seated_runs(segs: Sequence[Segment]) -> list[Run]:
    """Split segments into seated runs. An AWAY gap of 2+ minutes ends a run; shorter ones are absorbed."""
    runs: list[Run] = []
    cur: Optional[Run] = None
    for s in sorted(segs, key=lambda s: s.start):
        if s.state == AWAY:
            if cur is not None and s.dur >= LONG_AWAY_MS:
                runs.append(cur)
                cur = None
            continue
        if cur is None:
            cur = Run(start=s.start, end=s.end)
        cur.segs.append(s)
        cur.end = s.end
    if cur is not None:
        runs.append(cur)
    return runs


# ----------------------------------------------------------------------------- fatigue / onset

def fatigue_curve(runs: Sequence[Run]) -> dict[str, Any]:
    """Slouch share by minutes since sitting down, pooled over all runs: when does THIS person's posture
    start to slip? `onsetMin` is the first bucket (after the first 30 minutes) whose slouch share is
    clearly above their own early-sit share."""
    nb = CURVE_MAX_MIN // BUCKET_MIN + 1
    bucket_ms = BUCKET_MIN * 60_000
    seated = [0.0] * nb
    slouch = [0.0] * nb
    reach = [0] * nb
    for run in runs:
        for b in range(nb):
            if run.end - run.start > b * bucket_ms:
                reach[b] += 1
        for s in run.segs:
            cur = s.start
            while cur < s.end:
                idx = min((cur - run.start) // bucket_ms, nb - 1)
                nxt = s.end if idx == nb - 1 else min(s.end, run.start + (idx + 1) * bucket_ms)
                dur = (nxt - cur) / 1000
                seated[idx] += dur
                if s.state == SLOUCHING:
                    slouch[idx] += dur
                cur = nxt
    buckets = []
    for b in range(nb):
        buckets.append({"minFrom": b * BUCKET_MIN, "minTo": None if b == nb - 1 else (b + 1) * BUCKET_MIN,
                        "slouchPct": _pct(slouch[b], seated[b]) if seated[b] >= MIN_BUCKET_SEATED_SEC else None,
                        "seatedMin": round(seated[b] / 60), "runs": reach[b]})
    early_seated = sum(seated[:3])
    baseline = _pct(sum(slouch[:3]), early_seated) if early_seated >= 600 else None
    onset = None
    if baseline is not None:
        for b in range(3, nb):
            p = buckets[b]["slouchPct"]
            if seated[b] >= 600 and p is not None and p >= max(baseline * 1.5, baseline + 10):
                onset = b * BUCKET_MIN
                break
    return {"buckets": buckets, "baselinePct": baseline, "onsetMin": onset}


def onset_latency(runs: Sequence[Run]) -> dict[str, Any]:
    """How long after sitting down the first slouch happens (median over runs that had one)."""
    lat = []
    for run in runs:
        first = next((s for s in run.segs if s.state == SLOUCHING), None)
        if first is not None:
            lat.append((first.start - run.start) / 1000)
    n = len(runs)
    return {"medianSec": _median(lat) if len(lat) >= 5 else None, "runs": n,
            "runsWithSlouchPct": _pct(len(lat), n) if n >= 5 else None}


# ----------------------------------------------------------------------------- when (hours / days)

def danger_hours(cells: Sequence[dict[str, Any]], overall_slouch_pct: Optional[float], limit: int = 3) -> list[dict[str, Any]]:
    """The weekday-hours where slouching is worst relative to the person's own average (>= 30 min of data)."""
    if overall_slouch_pct is None:
        return []
    ranked = []
    for c in cells:
        if c.get("goodPct") is None or c.get("seatedSec", 0) < 1800:
            continue
        sl = round(100 - c["goodPct"], 1)
        if sl >= overall_slouch_pct + 5:
            ranked.append({"day": c["day"], "hour": c["hour"], "slouchPct": sl, "seatedMin": round(c["seatedSec"] / 60)})
    ranked.sort(key=lambda r: -r["slouchPct"])
    return ranked[:limit]


def weekday_slouch(cells: Sequence[dict[str, Any]]) -> dict[int, dict[str, float]]:
    """{weekday: {slouchPct, seatedMin}} from heatmap cells (weighted by seated time)."""
    acc: dict[int, list[float]] = {}
    for c in cells:
        if c.get("goodPct") is None:
            continue
        a = acc.setdefault(c["day"], [0.0, 0.0])
        a[0] += c["seatedSec"]
        a[1] += c["seatedSec"] * (100 - c["goodPct"]) / 100
    return {d: {"slouchPct": round(100 * v[1] / v[0], 1), "seatedMin": round(v[0] / 60)} for d, v in acc.items() if v[0] > 0}


def triggers(fatigue: dict[str, Any], hours: Sequence[dict[str, Any]], by_weekday: dict[int, dict[str, float]],
             overall_slouch_pct: Optional[float]) -> list[dict[str, str]]:
    """Plain-language 'what tends to precede your slouching', each backed by a number from the data."""
    out: list[dict[str, str]] = []
    if fatigue.get("onsetMin") is not None:
        out.append({"kind": "sit_length", "label": f"Long stretches of sitting: your posture slips after about {fatigue['onsetMin']} minutes."})
    if hours:
        h = hours[0]
        out.append({"kind": "time_of_day", "label": f"{_DAYS[h['day']]} around {_hour12(h['hour'])}: {h['slouchPct']:.0f}% slouching, well above your average."})
    if overall_slouch_pct is not None:
        worst = sorted(((d, v) for d, v in by_weekday.items() if v["seatedMin"] >= 180 and v["slouchPct"] >= overall_slouch_pct + 8),
                       key=lambda kv: -kv[1]["slouchPct"])
        if worst:
            d, v = worst[0]
            out.append({"kind": "weekday", "label": f"{_DAYS[d]}s are your hardest day ({v['slouchPct']:.0f}% slouching)."})
    return out


_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _hour12(h: int) -> str:
    return f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"


# ----------------------------------------------------------------------------- how you respond to nudges

def resolve_nudges(events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pair every alert (the first nudge, or an escalation) with what happened next:
    `recovered` (back to GOOD) with the seconds it took, or `left` (walked away). Unresolved alerts
    at the end of the data are dropped."""
    evs = sorted(events, key=lambda e: (e["t"], e.get("id", 0)))
    out = []
    for i, e in enumerate(evs):
        if not e.get("alert"):
            continue
        nxt = next((x for x in evs[i + 1:] if x.get("kind", "transition") == "transition"), None)
        if nxt is None:
            continue
        outcome = "recovered" if nxt["to_state"] == GOOD else ("left" if nxt["to_state"] == AWAY else None)
        if outcome is None:
            continue
        out.append({"t": e["t"], "level": int(e.get("level") or 1), "outcome": outcome,
                    "sec": round((nxt["t"] - e["t"]) / 1000, 1) if outcome == "recovered" else None})
    return out


def _rate_within(rows: Sequence[dict[str, Any]], secs: float) -> Optional[float]:
    rec = [r for r in rows if r["outcome"] == "recovered"]
    return _pct(sum(1 for r in rec if r["sec"] <= secs), len(rec)) if len(rec) >= MIN_NUDGES else None


def nudge_response(resolved: Sequence[dict[str, Any]], tz_offset_min: int) -> dict[str, Any]:
    """How the person responds to nudges: the share followed by sitting back up within 15/30/60 s, by
    nudge level and by part of the day. Only nudges that ended in recovery count in the rates; the ones
    followed by walking away are reported separately."""
    rec = [r for r in resolved if r["outcome"] == "recovered"]
    left = sum(1 for r in resolved if r["outcome"] == "left")

    def group(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
        r_ = [x for x in rows if x["outcome"] == "recovered"]
        return {"n": len(r_), "within30Pct": _rate_within(rows, 30), "medianSec": _median([x["sec"] for x in r_]) if len(r_) >= MIN_NUDGES else None}

    by_level = [{"level": lv, **group([r for r in resolved if r["level"] == lv])} for lv in (1, 2, 3)]
    by_part = [{"part": p, **group([r for r in resolved if part_of_day(local_hour(r["t"], tz_offset_min)) == p])} for p in PARTS_OF_DAY]
    return {"nudges": len(resolved), "recovered": len(rec), "leftAfterNudge": left,
            "within15Pct": _rate_within(resolved, 15), "within30Pct": _rate_within(resolved, 30),
            "within60Pct": _rate_within(resolved, 60),
            "medianRecoverySec": _median([r["sec"] for r in rec]) if len(rec) >= MIN_NUDGES else None,
            "byLevel": by_level, "byPartOfDay": by_part}


def recovery_trend(resolved: Sequence[dict[str, Any]], now_ms: int) -> list[dict[str, Any]]:
    """Average seconds to sit back up after a nudge, per 7-day window (weeksAgo 0 = the latest 7 days),
    oldest first. Dates are deliberately not included."""
    weeks: dict[int, list[float]] = {}
    for r in resolved:
        if r["outcome"] == "recovered":
            weeks.setdefault(max(0, int((now_ms - r["t"]) // (7 * DAY_MS))), []).append(r["sec"])
    return [{"weeksAgo": w, "avgRecoverySec": round(sum(v) / len(v), 1), "n": len(v)}
            for w, v in sorted(weeks.items(), reverse=True) if len(v) >= MIN_NUDGES]


def alert_fatigue(resolved: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Is the person responding less to nudges over time? Compares the quick-response rate of the
    older half of their nudges with the newer half (needs 20+)."""
    rec_or_left = sorted(resolved, key=lambda r: r["t"])
    if len(rec_or_left) < 20:
        return {"status": "insufficient", "firstHalfPct": None, "secondHalfPct": None, "n": len(rec_or_left)}
    half = len(rec_or_left) // 2

    def quick(rows: Sequence[dict[str, Any]]) -> float:
        return 100 * sum(1 for r in rows if r["outcome"] == "recovered" and r["sec"] <= 30) / len(rows)

    a, b = quick(rec_or_left[:half]), quick(rec_or_left[half:])
    drop = a - b
    status = "fatigued" if drop >= 15 else ("watch" if drop >= 8 else "ok")
    return {"status": status, "firstHalfPct": round(a, 1), "secondHalfPct": round(b, 1), "n": len(rec_or_left)}


def setting_suggestions(response: dict[str, Any], fatigue: dict[str, Any], settings: dict[str, Any],
                        seated_hours: float, slouch_pct: Optional[float]) -> list[dict[str, Any]]:
    """Concrete, one-click setting changes the data supports (user-applied, never automatic).
    Each carries a `patch` that is a valid partial settings update."""
    out: list[dict[str, Any]] = []
    thr = int(settings.get("slouchThresholdSec", 30))
    cooldown = int(settings.get("cooldownSec", 120))
    sens = float(settings.get("sensitivity", 0.5))
    level1 = next((x for x in response["byLevel"] if x["level"] == 1), {"n": 0, "within30Pct": None})
    per_hour = response["nudges"] / seated_hours if seated_hours >= 1 else 0

    if level1["n"] >= 10 and (level1["within30Pct"] or 0) >= 75 and thr >= 25:
        new = max(15, int(round(thr * 2 / 3 / 5) * 5))
        out.append({"id": "shorter-threshold", "title": f"Nudge sooner: {new}s instead of {thr}s",
                    "why": f"You sit back up within 30 seconds after {level1['within30Pct']:.0f}% of first nudges, so you respond well. An earlier nudge would catch slouches sooner.",
                    "patch": {"slouchThresholdSec": new}})
    if per_hour > 6 and (response["within30Pct"] if response["within30Pct"] is not None else 100) < 50:
        new = min(120, int(round(thr * 1.5 / 5) * 5))
        out.append({"id": "longer-threshold", "title": f"Nudge less often: {new}s instead of {thr}s",
                    "why": f"You're getting about {per_hour:.0f} nudges per seated hour and fixing posture quickly after fewer than half of them. A longer grace period may feel less naggy.",
                    "patch": {"slouchThresholdSec": new}})
    if fatigue["status"] == "fatigued":
        new = min(600, cooldown + 60)
        out.append({"id": "fatigue-cooldown", "title": f"Space nudges out: {new}s cooldown",
                    "why": f"You respond to fewer nudges lately ({fatigue['secondHalfPct']:.0f}% quickly, down from {fatigue['firstHalfPct']:.0f}%). More space between nudges can keep them meaningful.",
                    "patch": {"cooldownSec": new}})
    if seated_hours >= 10 and response["nudges"] == 0 and (slouch_pct or 0) >= 15 and sens < 1:
        new = round(min(1.0, sens + 0.2), 2)
        out.append({"id": "more-sensitive", "title": "Make nudges more sensitive",
                    "why": f"You've slouched about {slouch_pct:.0f}% of your seated time but never got a nudge. A stricter sensitivity would catch it.",
                    "patch": {"sensitivity": new}})
    return out[:4]


# ----------------------------------------------------------------------------- habits

def _data_days(daily: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted((d for d in daily if d.get("goodPct") is not None), key=lambda d: d["dayIndex"])


def habit_strength(daily: Sequence[dict[str, Any]], today_idx: int, target: float = GOOD_THRESHOLD_PCT) -> dict[str, Any]:
    """Consistency (not just the average): the share of the last 14 days at or above target, plus a
    forgiving streak that tolerates one off day per 7 days. Today is in progress and never counts against."""
    days = [d for d in _data_days(daily) if today_idx - 13 <= d["dayIndex"] <= today_idx]
    at = sum(1 for d in days if d["goodPct"] >= target)
    streak = 0
    last_forgiven: Optional[int] = None
    for d in sorted(_data_days(daily), key=lambda d: -d["dayIndex"]):
        if d["dayIndex"] > today_idx:
            continue
        if d["goodPct"] >= target:
            streak += 1
        elif d["dayIndex"] == today_idx:
            continue                                   # today isn't over
        elif last_forgiven is None or last_forgiven - d["dayIndex"] >= 7:
            last_forgiven = d["dayIndex"]              # spend the weekly freeze
        else:
            break
    return {"targetPct": target, "daysWithData": len(days), "daysAtTarget": at,
            "consistencyPct": _pct(at, len(days)) if len(days) >= 5 else None,
            "forgivingStreak": streak, "strictStreak": scoring.day_streak(list(daily), today_idx)}


def bests(daily: Sequence[dict[str, Any]], segs: Sequence[Segment], target: float = GOOD_THRESHOLD_PCT) -> dict[str, Any]:
    days = _data_days(daily)
    best_day = max((d["score"] for d in days if d.get("score") is not None), default=None)
    longest = run = 0
    for d in days:
        run = run + 1 if d["goodPct"] >= target else 0
        longest = max(longest, run)
    best_week = None
    by_idx = {d["dayIndex"]: d for d in days}
    for i in by_idx:
        window = [by_idx[j] for j in range(i, i + 7) if j in by_idx]
        if len(window) >= 4:
            seated = sum(d["seatedSec"] for d in window)
            val = sum(d["goodPct"] * d["seatedSec"] for d in window) / seated if seated else None
            if val is not None and (best_week is None or val > best_week):
                best_week = round(val, 1)
    return {"bestDayScore": best_day, "bestWeekScore": best_week, "longestDayStreak": longest,
            "longestGoodStretchMin": round(scoring.longest_good_streak(segs) / 60)}


def relapse(daily: Sequence[dict[str, Any]], today_idx: int, target: float = GOOD_THRESHOLD_PCT) -> dict[str, Any]:
    """After three finished days below target that follow a good stretch: a gentle rescue and a smaller goal."""
    done = [d for d in _data_days(daily) if d["dayIndex"] < today_idx]
    if len(done) < 6:
        return {"active": False}
    last3, before = done[-3:], done[-10:-3]
    if all(d["goodPct"] < target for d in last3) and before and sum(d["goodPct"] for d in before) / len(before) >= target:
        avg = sum(d["goodPct"] for d in last3) / 3
        return {"active": True, "smallerGoalPct": int(min(target, round(avg + 5))),
                "message": "A few tougher days happen to everyone. Aim for a smaller win today and get back on track."}
    return {"active": False}


def challenge(hours: Sequence[dict[str, Any]], overall_slouch_pct: Optional[float], next_goal_pct: int) -> dict[str, str]:
    """A weekly challenge sized from the person's own data."""
    if hours:
        h = hours[0]
        return {"title": f"Cut your {_DAYS[h['day']]} {_hour12(h['hour'])} slouch by 5 points",
                "detail": f"It's currently {h['slouchPct']:.0f}%, your weakest hour."}
    return {"title": f"Reach {next_goal_pct}% good posture this week",
            "detail": "A small step up from last week, sized from your own results."}


# ----------------------------------------------------------------------------- breaks and the workday

def break_quality(runs: Sequence[Run], segs: Sequence[Segment], active_days: int) -> dict[str, Any]:
    """Longest unbroken sit, how often sits run past the target length, and breaks per day."""
    mins = [r.minutes for r in runs]
    breaks = sum(1 for s in segs if s.state == AWAY and s.dur >= LONG_AWAY_MS)
    micro = sum(1 for s in segs if s.state == AWAY and MICRO_BREAK_MIN_MS <= s.dur < LONG_AWAY_MS)
    d = max(1, active_days)
    return {"targetMin": SIT_TARGET_MIN, "runs": len(runs),
            "longestSitMin": round(max(mins)) if mins else None,
            "avgSitMin": round(sum(mins) / len(mins)) if mins else None,
            "runsOverTargetPct": _pct(sum(1 for m in mins if m > SIT_TARGET_MIN), len(mins)) if len(mins) >= 5 else None,
            "breaksPerDay": round(breaks / d, 1), "microBreaksPerDay": round(micro / d, 1)}


def work_hours(segs: Sequence[Segment], tz_offset_min: int) -> Optional[dict[str, Any]]:
    """The person's typical weekday start and end (median over weekdays with 2+ hours seated), inferred
    from data instead of asking. Needs 5+ weekdays."""
    off = tz_offset_min * 60_000
    per_day: dict[int, list[float]] = {}
    for s in segs:
        if s.state == AWAY:
            continue
        for idx, part in scoring.split_at([s], DAY_MS, off):
            if (idx + 3) % 7 >= 5:
                continue
            a = per_day.setdefault(idx, [float("inf"), float("-inf"), 0.0])
            a[0] = min(a[0], (part.start + off) - idx * DAY_MS)
            a[1] = max(a[1], (part.end + off) - idx * DAY_MS)
            a[2] += part.dur / 1000
    days = [v for v in per_day.values() if v[2] >= 2 * 3600]
    if len(days) < 5:
        return None
    start = statistics.median(v[0] for v in days) / HOUR_MS
    end = statistics.median(v[1] for v in days) / HOUR_MS
    return {"startHour": round(start * 2) / 2, "endHour": round(end * 2) / 2, "days": len(days)}
