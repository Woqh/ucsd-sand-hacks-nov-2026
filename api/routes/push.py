from __future__ import annotations

import re

from flask import Blueprint, g

from api import util
from api.auth import (bearer_token, dashboard_only, device_only, hash_token, new_pairing_code, new_token,
                      push_receiver_only)
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


@bp.post("/push/web/receiver/pairing")
@dashboard_only
def create_receiver_pairing():
    """Issue a short-lived code for a second phone with access limited to push registration."""
    code = new_pairing_code(8)
    expires = util.now_ms() + 10 * 60 * 1000
    get_store().create_push_receiver_pairing(g.user["id"], code, expires)
    return {"schema": util.SCHEMA, "code": code, "expiresAt": expires}


@bp.post("/push/web/receiver/claim")
def claim_receiver_pairing():
    code = re.sub(r"[\s-]", "", str(util.json_body().get("code", ""))).upper()
    if not code:
        raise ApiError(400, "bad_request", "code is required")
    store = get_store()
    user_id = store.claim_push_receiver_pairing(code, util.now_ms())
    if not user_id:
        raise ApiError(404, "invalid_code", "That receiver code is invalid or has expired")
    token = new_token()
    store.save_push_receiver_token(user_id, hash_token(token))
    return {"schema": util.SCHEMA, "receiverToken": token}


@bp.post("/push/web/receiver/subscribe")
@push_receiver_only
def receiver_subscribe():
    body = util.json_body()
    sub = body.get("subscription", body)
    endpoint = sub.get("endpoint") if isinstance(sub, dict) else None
    keys = sub.get("keys") if isinstance(sub, dict) else None
    if (not isinstance(endpoint, str) or not endpoint.startswith("https://")
            or not isinstance(keys, dict) or not isinstance(keys.get("p256dh"), str)
            or not isinstance(keys.get("auth"), str) or not keys["p256dh"] or not keys["auth"]):
        raise ApiError(400, "invalid_subscription", "Expected a PushSubscription: {endpoint, keys:{p256dh, auth}}")
    get_store().save_push_subscription(
        g.user["id"], "web_phone", endpoint, {"keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}})
    return {"schema": util.SCHEMA, "ok": True}


@bp.post("/push/web/receiver/unsubscribe")
@push_receiver_only
def receiver_unsubscribe():
    endpoint = util.json_body().get("endpoint")
    if endpoint is not None and (not isinstance(endpoint, str) or not endpoint.startswith("https://")):
        raise ApiError(400, "invalid_subscription", "endpoint must be an HTTPS URL")
    store = get_store()
    if endpoint:
        store.delete_push_subscription(g.user["id"], "web_phone", endpoint)
    store.delete_push_receiver_token(hash_token(bearer_token()))
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
