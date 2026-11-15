"""GET /metrics + the shared aggregation helpers (the status route reuses day_snapshot)."""
from __future__ import annotations

from typing import Any, Optional

from flask import Blueprint, g, request

from api import util
from api.auth import dashboard_only
from api.core import scoring
from api.db import get_store
from api.errors import ApiError

bp = Blueprint("metrics", __name__)

RANGE_DAYS = {"day": 1, "week": 7, "month": 30}
DAY = scoring.DAY_MS


def _last_seen(store: Any, user_id: str) -> Optional[int]:
    sess = store.latest_session(user_id)
    return sess["last_t"] if sess else None


def day_snapshot(store: Any, user_id: str, tz_offset_min: int, now: int) -> dict[str, Any]:
    """Light query (today only): used on every /status poll."""
    off = tz_offset_min * 60_000
    since = ((now + off) // DAY) * DAY - off
    events = store.list_events(user_id, since, now)
    prior = store.last_event_before(user_id, since)
    segs = scoring.build_segments(events, prior, since, now, _last_seen(store, user_id))
    summary = scoring.summarize(segs, events, since, now)
    summary["sittingSec"] = scoring.sitting_run_sec(segs, now)
    return summary


def build_metrics(store: Any, user_id: str, range_: str, tz_offset_min: int, now: int) -> dict[str, Any]:
    days = RANGE_DAYS[range_]
    off = tz_offset_min * 60_000
    today_idx = (now + off) // DAY
    first_idx = today_idx - days + 1
    since = first_idx * DAY - off
    prev_since = since - days * DAY
    fetch_since = min(prev_since, (today_idx - 30) * DAY - off)  # previous period + 30 days for streaks

    events = store.list_events(user_id, fetch_since, now)
    prior = store.last_event_before(user_id, fetch_since)
    segs = scoring.build_segments(events, prior, fetch_since, now, _last_seen(store, user_id))

    cur = scoring.clip(segs, since, now)
    prev = scoring.clip(segs, prev_since, since)
    summary = scoring.summarize(cur, events, since, now)
    prev_summary = scoring.summarize(prev, events, prev_since, since)

    daily_all = scoring.daily_breakdown(scoring.clip(segs, (today_idx - 29) * DAY - off, now), tz_offset_min)
    daily = scoring.fill_days(daily_all, first_idx, today_idx)

    heat_since = (today_idx - max(days, 7) + 1) * DAY - off
    today_segs = scoring.clip(segs, today_idx * DAY - off, now)

    return {
        "schema": util.SCHEMA,
        "range": range_,
        "since": since,
        "until": now,
        "tzOffsetMin": tz_offset_min,
        "summary": summary,
        "previous": {"score": prev_summary["score"], "goodPct": prev_summary["goodPct"],
                     "seatedSec": prev_summary["seatedSec"]},
        "daily": daily,
        "heatmap": scoring.heatmap(scoring.clip(segs, heat_since, now), tz_offset_min),
        "timeline": ([{"state": s.state, "start": s.start, "end": s.end} for s in cur]
                     if range_ == "day" else []),
        "dayStreak": scoring.day_streak(daily_all, today_idx),
        "goal": {"previousPct": prev_summary["goodPct"], "currentPct": summary["goodPct"],
                 "targetPct": scoring.next_goal_pct(prev_summary["goodPct"])},
        "outlook": scoring.outlook(summary["score"]),
        "sittingSec": scoring.sitting_run_sec(today_segs, now),
    }


@bp.get("/metrics")
@dashboard_only
def metrics():
    range_ = request.args.get("range", "day")
    if range_ not in RANGE_DAYS:
        raise ApiError(400, "bad_request", "range must be day, week or month")
    return build_metrics(get_store(), g.user["id"], range_, util.tz_offset_arg(), util.now_ms())
