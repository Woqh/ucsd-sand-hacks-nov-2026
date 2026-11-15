"""Pairing: dashboard creates an anonymous user + a short code; the phone claims it.
These are the only routes that don't require a token (create may take one to re-issue a code)."""
from __future__ import annotations

import re

from flask import Blueprint, request

from api import util
from api.auth import bearer_token, hash_token, new_pairing_code, new_token
from api.core.settings import DEFAULT_SETTINGS
from api.db import get_store
from api.errors import ApiError

bp = Blueprint("pair", __name__)

PAIRING_TTL_MS = 10 * 60 * 1000


@bp.post("/pair/create")
def create():
    """No Authorization header: make a new anonymous user (returns dashboardToken + code).
    With a dashboard token: keep the user, just issue a fresh code (e.g. to pair a new phone)."""
    store = get_store()
    code = new_pairing_code()
    expires = util.now_ms() + PAIRING_TTL_MS
    if request.headers.get("Authorization"):
        user = store.get_user_by_dashboard_hash(hash_token(bearer_token()))
        if not user:
            raise ApiError(401, "unauthorized", "Invalid token")
        store.update_user(user["id"], {"pairing_code": code, "pairing_expires_at": expires})
        return {"schema": util.SCHEMA, "pairingCode": code, "expiresAt": expires}
    token = new_token()
    store.create_user(hash_token(token), code, expires, DEFAULT_SETTINGS)
    return {"schema": util.SCHEMA, "dashboardToken": token, "pairingCode": code, "expiresAt": expires}


@bp.post("/pair/claim")
def claim():
    body = util.json_body()
    code = re.sub(r"[\s-]", "", str(body.get("code", ""))).upper()
    if not code:
        raise ApiError(400, "bad_request", "code is required")
    store = get_store()
    user = store.get_user_by_pairing_code(code)
    if not user or (user.get("pairing_expires_at") or 0) < util.now_ms():
        raise ApiError(404, "invalid_code", "That pairing code is invalid or has expired")
    token = new_token()
    # One phone per user for the MVP: a new claim replaces the previous device token.
    store.update_user(user["id"], {"device_token_hash": hash_token(token), "pairing_code": None,
                                   "pairing_expires_at": None})
    return {"schema": util.SCHEMA, "deviceToken": token}
