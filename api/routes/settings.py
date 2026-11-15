from __future__ import annotations

from flask import Blueprint, g

from api import util
from api.auth import any_client, dashboard_only
from api.core.settings import merge_settings
from api.db import get_store
from api.errors import ApiError

bp = Blueprint("settings", __name__)


@bp.get("/settings")
@any_client
def get_settings():
    settings, _ = merge_settings(g.user.get("settings"), {})
    return {"schema": util.SCHEMA, "settings": settings}


@bp.put("/settings")
@any_client
def put_settings():
    """Partial update: send only the fields you want to change."""
    body = util.json_body()
    patch = body.get("settings", body)
    if not isinstance(patch, dict):
        raise ApiError(400, "bad_request", "settings must be an object")
    settings, errors = merge_settings(g.user.get("settings"), patch)
    if errors:
        raise ApiError(400, "invalid_settings", "; ".join(errors))
    get_store().update_user(g.user["id"], {"settings": settings})
    return {"schema": util.SCHEMA, "settings": settings}


@bp.post("/focus")
@dashboard_only
def start_focus():
    """Start (minutes 1-240) or stop (0) a focus session. With `focus.onlyDuringFocus` on, nudges only fire
    while a session is running. The end time is set from server time."""
    minutes = util.json_body().get("minutes")
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 0 <= minutes <= 240:
        raise ApiError(400, "invalid_focus", "minutes must be a whole number from 0 to 240 (0 stops the session)")
    until = 0 if minutes == 0 else util.now_ms() + minutes * 60_000
    settings, errors = merge_settings(g.user.get("settings"), {"focus": {"untilMs": until}})
    if errors:  # pragma: no cover (the value is always valid here)
        raise ApiError(400, "invalid_settings", "; ".join(errors))
    get_store().update_user(g.user["id"], {"settings": settings})
    return {"schema": util.SCHEMA, "settings": settings, "focusUntilMs": until}
