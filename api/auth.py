"""Bearer-token auth. Tokens are random secrets stored only as SHA-256 hashes."""
from __future__ import annotations

import hashlib
import secrets
from functools import wraps
from typing import Callable

from flask import g, request

from api.db import get_store
from api.errors import ApiError

PAIRING_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L lookalikes


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_pairing_code(n: int = 6) -> str:
    return "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(n))


def bearer_token() -> str:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer ") or len(header) < 20:
        raise ApiError(401, "unauthorized", "Missing or malformed Authorization: Bearer <token>")
    return header[7:].strip()


def require_auth(*roles: str) -> Callable:
    """roles: 'dashboard' and/or 'device'. Sets g.user (the users row) and g.role."""
    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            h = hash_token(bearer_token())
            store = get_store()
            user, role = None, None
            if "dashboard" in roles:
                user = store.get_user_by_dashboard_hash(h)
                role = "dashboard" if user else None
            if user is None and "device" in roles:
                user = store.get_user_by_device_hash(h)
                role = "device" if user else None
            if user is None:
                raise ApiError(401, "unauthorized", "Invalid token")
            g.user, g.role = user, role
            return fn(*args, **kwargs)
        return wrapper
    return deco


dashboard_only = require_auth("dashboard")
device_only = require_auth("device")
any_client = require_auth("dashboard", "device")


def push_receiver_only(fn: Callable) -> Callable:
    """Authenticate a receiver-only phone token; it can only manage its own push subscription."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token_hash = hash_token(bearer_token())
        user = get_store().get_user_by_push_receiver_hash(token_hash)
        if user is None:
            raise ApiError(401, "unauthorized", "Invalid receiver token")
        g.user, g.role = user, "push_receiver"
        return fn(*args, **kwargs)
    return wrapper
