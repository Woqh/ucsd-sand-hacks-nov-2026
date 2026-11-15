"""Dev-only helpers. Every route 404s unless ENABLE_DEV_ROUTES=1."""
from __future__ import annotations

from flask import Blueprint, request

from api import util
from api.auth import bearer_token, hash_token, new_pairing_code, new_token
from api.core import seedgen
from api.core.settings import DEFAULT_SETTINGS
from api.db import get_store
from api.errors import ApiError
from api.routes.pair import PAIRING_TTL_MS

bp = Blueprint("dev", __name__)


@bp.post("/dev/seed")
def seed():
    """Fill `days` (default 14, max 90) of fake posture history: two weeks so that week-over-week
    comparisons and the goal card have a "previous week" to compare against.
    With a dashboard token: seeds that user (replacing their history unless reset=false).
    Without one: creates a brand-new demo user and returns its dashboardToken + pairingCode."""
    if not util.dev_routes_enabled():
        raise ApiError(404, "not_found", "Not found")
    body = util.json_body(required=False)
    days = body.get("days", 14)
    tz = body.get("tzOffsetMin", 0)
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 90:
        raise ApiError(400, "bad_request", "days must be an integer 1-90")
    if not isinstance(tz, int) or isinstance(tz, bool) or not -840 <= tz <= 840:
        raise ApiError(400, "bad_request", "tzOffsetMin must be an integer")

    store = get_store()
    extra: dict = {}
    if request.headers.get("Authorization"):
        user = store.get_user_by_dashboard_hash(hash_token(bearer_token()))
        if not user:
            raise ApiError(401, "unauthorized", "Invalid token")
    else:
        token, code = new_token(), new_pairing_code()
        user = store.create_user(hash_token(token), code, util.now_ms() + PAIRING_TTL_MS,
                                 {**DEFAULT_SETTINGS, "tzOffsetMin": tz})
        extra = {"dashboardToken": token, "pairingCode": code}

    if body.get("reset", True):
        store.clear_history(user["id"])
    events = seedgen.generate(days, util.now_ms(), tz, seed=int(body.get("seed", 7)))
    rows = [{**e, "user_id": user["id"]} for e in events]
    store.insert_events(rows)
    # demo pain check-ins (one per week of history) so the "pain vs slouching" view has something to show
    checkins = seedgen.checkins_from_events(events, util.now_ms(), seed=int(body.get("seed", 7)))
    for c in checkins:
        store.add_checkin(user["id"], c["t"], c["pain"], c["area"])
    return {"schema": util.SCHEMA, "events": len(rows), "days": days, "checkins": len(checkins), **extra}
