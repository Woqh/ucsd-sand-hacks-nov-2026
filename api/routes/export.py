"""GET /export: the user's own data as a de-identified, weekly-aggregate file they can inspect and
download. Nothing here is sent anywhere. It is the shape a future, explicitly opt-in research
contribution would use: no user id, tokens, device details, or timestamps finer than a day."""
from __future__ import annotations

from flask import Blueprint, g

from api import util
from api.auth import dashboard_only
from api.core import scoring
from api.db import get_store

bp = Blueprint("export", __name__)

WEEKS = 12
DAY = scoring.DAY_MS


@bp.get("/export")
@dashboard_only
def export():
    store = get_store()
    uid = g.user["id"]
    now = util.now_ms()
    tz = util.tz_offset_arg()
    off = tz * 60_000
    today_idx = (now + off) // DAY

    # trailing 7-day windows ending at the end of today, oldest first
    windows = []
    for k in range(WEEKS - 1, -1, -1):
        end = (today_idx + 1 - 7 * k) * DAY - off
        windows.append((end - 7 * DAY, min(end, now)))
    since = windows[0][0]

    events = store.list_events(uid, since, now)
    prior = store.last_event_before(uid, since)
    sess = store.latest_session(uid)
    segs = scoring.build_segments(events, prior, since, now, sess["last_t"] if sess else None)

    weeks = []
    for a, b in windows:
        s = scoring.summarize(scoring.clip(segs, a, b), events, a, b)
        weeks.append({
            "weekStart": scoring.date_str((a + off) // DAY),
            "seatedMinutes": round(s["seatedSec"] / 60),
            "goodPct": s["goodPct"],
            "slouchPct": None if s["seatedSec"] == 0 else round(100 * s["slouchSec"] / s["seatedSec"], 1),
            "slouchEpisodes": s["slouchEvents"],
        })

    def week_start_of(t: int) -> str | None:
        for a, b in windows:
            if a <= t < b + 1:
                return scoring.date_str((a + off) // DAY)
        return None

    checkins = [{"weekStart": week_start_of(c["t"]), "pain": c["pain"], "area": c["area"]}
                for c in sorted(store.list_checkins(uid, 52), key=lambda c: c["t"])]
    return {
        "schema": util.SCHEMA,
        "kind": "sitwise-weekly-export",
        "generated": scoring.date_str(today_idx),
        "weeks": weeks,
        "checkins": [c for c in checkins if c["weekStart"] is not None],
        "note": ("De-identified weekly aggregates. No user id, tokens, device details or timestamps finer "
                 "than a day. This file stays on your device unless you choose to share it."),
    }
