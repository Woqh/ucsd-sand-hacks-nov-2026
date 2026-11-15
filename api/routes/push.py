from __future__ import annotations

import re

from flask import Blueprint, g

from api import util
from api.auth import dashboard_only, device_only
from api.db import get_store
from api.errors import ApiError
from api.push import dispatch, webpush

bp = Blueprint("push", __name__)


@bp.get("/push/web/public-key")
def web_public_key():
    """Public by design (it's the VAPID *public* key the browser needs to subscribe)."""
    return {"schema": util.SCHEMA, "publicKey": webpush.public_key()}


@bp.post("/push/web/subscribe")
@dashboard_only
def web_subscribe():
    body = util.json_body()
    sub = body.get("subscription", body)
    endpoint = sub.get("endpoint") if isinstance(sub, dict) else None
    keys = sub.get("keys") if isinstance(sub, dict) else None
    if (not isinstance(endpoint, str) or not endpoint.startswith("https://")
            or not isinstance(keys, dict) or not keys.get("p256dh") or not keys.get("auth")):
        raise ApiError(400, "invalid_subscription", "Expected a PushSubscription: {endpoint, keys:{p256dh, auth}}")
    get_store().save_push_subscription(
        g.user["id"], "web", endpoint, {"keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}})
    return {"schema": util.SCHEMA, "ok": True}


@bp.post("/push/apns/register")
@device_only
def apns_register():
    body = util.json_body()
    token = str(body.get("token", "")).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32,200}", token):
        raise ApiError(400, "invalid_token", "token must be the hex APNs device token")
    data = {}
    if isinstance(body.get("sandbox"), bool):
        data["sandbox"] = body["sandbox"]  # dev builds register sandbox tokens; TestFlight/prod don't
    get_store().save_push_subscription(g.user["id"], "apns", token, data)
    return {"schema": util.SCHEMA, "ok": True}


@bp.post("/push/test")
@dashboard_only
def push_test():
    """Send a test notification so the user can check the channel works."""
    channel = util.json_body().get("channel")
    if channel not in ("phone", "desktop"):
        raise ApiError(400, "bad_request", "channel must be 'phone' or 'desktop'")
    return {"schema": util.SCHEMA, "channel": channel, "result": dispatch.send_test(get_store(), g.user, channel)}
