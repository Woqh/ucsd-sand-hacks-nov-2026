"""Assemble the personal analysis pack from already-fetched data. Pure.

The pack is the single de-identified summary of how a person sits and how they respond to coaching.
The dashboard shows it, and it is the ONLY thing ever offered to Gemini (after the user opts in and
has previewed it). By construction it contains: no user id, no tokens, no timestamps (relative
"weeksAgo" instead of dates), no pain check-ins (health data stays out), and no images. It is a
description of habits, not a medical statement.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from api.core import coach_stats as cs
from api.core import posture_profile as pp
from api.core import scoring
from api.core.scoring import Segment

PACK_SCHEMA = 1


def build_pack(*, now_ms: int, tz_offset_min: int, window_days: int, segs: Sequence[Segment],
               events: Sequence[dict[str, Any]], daily: Sequence[dict[str, Any]], heat: Sequence[dict[str, Any]],
               rollups: Sequence[dict[str, Any]], settings: dict[str, Any],
               calibrations: Sequence[dict[str, Any]]) -> dict[str, Any]:
    off = tz_offset_min * 60_000
    today_idx = (now_ms + off) // scoring.DAY_MS
    since = (today_idx - window_days + 1) * scoring.DAY_MS - off
    summary = scoring.summarize(scoring.clip(segs, since, now_ms), [], since, now_ms)
    seated_h = summary["seatedSec"] / 3600
    slouch_pct = None if summary["seatedSec"] == 0 else round(100 * summary["slouchSec"] / summary["seatedSec"], 1)

    runs = cs.seated_runs(segs)
    fatigue = cs.fatigue_curve(runs)
    onset = cs.onset_latency(runs)
    hours = cs.danger_hours(heat, slouch_pct)
    by_day = cs.weekday_slouch(heat)
    resolved = cs.resolve_nudges(events)
    response = cs.nudge_response(resolved, tz_offset_min)
    fatigue_alert = cs.alert_fatigue(resolved)
    active_days = sum(1 for d in daily if d.get("seatedSec", 0) > 0)
    breaks = cs.break_quality(runs, segs, active_days)
    finger = pp.fingerprint(rollups)
    signature = finger["signature"] if finger else None
    prev_pct = None  # the previous period isn't part of this window; the goal falls back to "next 5 points"
    last_week = [d for d in daily if d["dayIndex"] > today_idx - 7 and d.get("goodPct") is not None]
    if last_week:
        tot = sum(d["seatedSec"] for d in last_week)
        prev_pct = round(sum(d["goodPct"] * d["seatedSec"] for d in last_week) / tot, 1) if tot else None
    next_goal = scoring.next_goal_pct(prev_pct)
    exercises = pp.recommend_exercises(signature, fatigue["onsetMin"], (breaks["longestSitMin"] or 0) > 90)

    return {
        "schema": PACK_SCHEMA,
        "window": {"days": window_days, "seatedHours": round(seated_h, 1), "slouchPct": slouch_pct},
        "habits": {
            "strength": cs.habit_strength(daily, today_idx),
            "bests": cs.bests(daily, segs),
            "relapse": cs.relapse(daily, today_idx),
            "challenge": cs.challenge(hours, slouch_pct, next_goal),
        },
        "patterns": {
            "fatigue": fatigue,
            "onsetLatency": onset,
            "dangerHours": hours,
            "weekdays": [{"day": d, **v} for d, v in sorted(by_day.items())],
            "triggers": cs.triggers(fatigue, hours, by_day, slouch_pct),
            "fingerprint": finger,
            "drift": pp.posture_drift(rollups, calibrations, now_ms),
            "setupHints": pp.setup_hints(signature, fatigue["onsetMin"], breaks["longestSitMin"]),
        },
        "coaching": {
            "response": response,
            "recoveryTrend": cs.recovery_trend(resolved, now_ms),
            "alertFatigue": fatigue_alert,
            "suggestions": cs.setting_suggestions(response, fatigue_alert, settings, seated_h, slouch_pct),
            "currentSettings": {k: settings.get(k) for k in ("slouchThresholdSec", "sensitivity", "cooldownSec", "nudgeTone")},
        },
        "breaks": breaks,
        "workHours": cs.work_hours(segs, tz_offset_min),
        "exercises": [dict(pp.exercise_by_id(i), safety=pp.SAFETY_NOTE) for i in exercises],
    }


def compact_for_ai(pack: dict[str, Any]) -> dict[str, Any]:
    """The smaller view that is sent to Gemini: the numbers and the library of exercise ids it may choose
    from, without step-by-step instructions. (Nothing in the pack is identifying to begin with.)"""
    slim = {k: v for k, v in pack.items() if k != "exercises"}
    slim["exerciseLibrary"] = [{"id": e["id"], "title": e["title"], "for": e["for"]} for e in pp.EXERCISES]
    slim["recommendedByRules"] = [e["id"] for e in pack["exercises"]]
    return slim
