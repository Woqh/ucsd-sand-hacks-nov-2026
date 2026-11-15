"""Weekly pain check-ins and the personal insight built from them.

This is NOT a risk prediction. Research hasn't shown that slouching causes pain (docs/health-claims.md),
so the only thing we compute is whether, in this person's own data, weeks with more slouching lined up
with more pain, and we say plainly that that is a pattern and not a cause."""
from __future__ import annotations

from flask import Blueprint, g

from api import util
from api.auth import dashboard_only
from api.core import insights, scoring
from api.db import get_store
from api.errors import ApiError

bp = Blueprint("checkins", __name__)

AREAS = ("neck", "upper_back", "lower_back", "shoulders", "other")
MAX_LIST = 52  # a year of weekly check-ins


def _public(c: dict) -> dict:
    return {"id": c["id"], "t": c["t"], "pain": c["pain"], "area": c["area"]}


@bp.post("/checkins")
@dashboard_only
def add_checkin():
    body = util.json_body()
    pain = body.get("pain")
    if isinstance(pain, bool) or not isinstance(pain, int) or not 0 <= pain <= 10:
        raise ApiError(400, "invalid_checkin", "pain must be a whole number from 0 to 10")
    area = body.get("area")
    if area is not None and area not in AREAS:
        raise ApiError(400, "invalid_checkin", f"area must be one of {', '.join(AREAS)} (or omitted)")
    c = get_store().add_checkin(g.user["id"], util.now_ms(), pain, area)
    return {"schema": util.SCHEMA, "checkin": _public(c)}


@bp.get("/checkins")
@dashboard_only
def list_checkins():
    rows = get_store().list_checkins(g.user["id"], MAX_LIST)
    return {"schema": util.SCHEMA, "checkins": [_public(c) for c in rows]}


@bp.get("/insights/pain")
@dashboard_only
def pain_insight():
    """Each check-in paired with the share of seated time spent slouching in the 7 days before it,
    plus a hedged rank correlation once there are enough weeks."""
    store = get_store()
    uid = g.user["id"]
    now = util.now_ms()
    checkins = sorted(store.list_checkins(uid, MAX_LIST), key=lambda c: c["t"])
    base = {"schema": util.SCHEMA, "points": [], "lastCheckinAt": None, "nextSuggestedAt": None,
            "correlation": {"enough": False, "n": 0, "needed": insights.MIN_POINTS, "rho": None,
                            "strength": None, "direction": None}}
    if not checkins:
        return base

    since = checkins[0]["t"] - insights.WINDOW_MS
    events = store.list_events(uid, since, now)
    prior = store.last_event_before(uid, since)
    sess = store.latest_session(uid)
    segs = scoring.build_segments(events, prior, since, now, sess["last_t"] if sess else None)

    points = []
    for c in checkins:
        pct, seated = insights.slouch_exposure(segs, c["t"])
        points.append({"t": c["t"], "pain": c["pain"], "area": c["area"], "slouchPct": pct, "seatedSec": seated})
    correlation = insights.pain_vs_slouch(points)   # also sets each point's `used`
    last = checkins[-1]["t"]
    return {**base, "points": points, "correlation": correlation, "lastCheckinAt": last,
            "nextSuggestedAt": last + insights.WINDOW_MS}
