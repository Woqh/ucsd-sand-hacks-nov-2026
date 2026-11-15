from __future__ import annotations

from flask import Blueprint, g

from api import util
from api.auth import any_client
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
