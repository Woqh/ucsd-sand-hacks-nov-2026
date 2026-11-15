"""APNs over HTTP/2 with token-based (.p8) auth. No FCM.

Env: APNS_KEY_ID, APNS_TEAM_ID, APNS_AUTH_KEY (contents of the .p8), APNS_BUNDLE_ID,
APNS_USE_SANDBOX (1 = api.sandbox.push.apple.com for dev builds, 0 = production host).
Sandbox and production device tokens are NOT interchangeable, so each registered token carries
its own `sandbox` flag (sent by the app from its build config); the env var is only the default.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

SANDBOX_HOST = "https://api.sandbox.push.apple.com"
PROD_HOST = "https://api.push.apple.com"

_client: Any = None
_jwt_cache: dict[str, Any] = {"token": None, "iat": 0}


def configured() -> bool:
    return all(os.environ.get(k) for k in ("APNS_KEY_ID", "APNS_TEAM_ID", "APNS_AUTH_KEY", "APNS_BUNDLE_ID"))


def default_sandbox() -> bool:
    return os.environ.get("APNS_USE_SANDBOX", "1") not in ("0", "false", "False", "")


def _provider_token() -> str:
    import jwt  # PyJWT, lazy
    now = int(time.time())
    if _jwt_cache["token"] and now - _jwt_cache["iat"] < 50 * 60:  # APNs wants a refresh within 1 h
        return _jwt_cache["token"]
    key = os.environ["APNS_AUTH_KEY"].replace("\\n", "\n")
    token = jwt.encode({"iss": os.environ["APNS_TEAM_ID"], "iat": now}, key, algorithm="ES256",
                       headers={"kid": os.environ["APNS_KEY_ID"]})
    _jwt_cache.update(token=token, iat=now)
    return token


def _http():
    global _client
    if _client is None:
        import httpx
        _client = httpx.Client(http2=True, timeout=8.0)
    return _client


def send(device_token: str, title: str, body: str, *, sandbox: Optional[bool] = None,
         thread_id: str = "posture") -> tuple[bool, Optional[int], Optional[str]]:
    """Returns (ok, http_status, apns_reason). `reason` BadDeviceToken / Unregistered (410) means the
    caller should delete the token."""
    if not configured():
        return False, None, "not_configured"
    host = SANDBOX_HOST if (default_sandbox() if sandbox is None else sandbox) else PROD_HOST
    payload = {"aps": {"alert": {"title": title, "body": body}, "sound": "default",
                       "thread-id": thread_id, "interruption-level": "time-sensitive"}}
    try:
        r = _http().post(
            f"{host}/3/device/{device_token}", content=json.dumps(payload),
            headers={"authorization": f"bearer {_provider_token()}",
                     "apns-topic": os.environ["APNS_BUNDLE_ID"],
                     "apns-push-type": "alert", "apns-priority": "10"})
    except Exception as exc:  # network / h2 / key errors must never break ingest
        return False, None, f"error:{type(exc).__name__}"
    if r.status_code == 200:
        return True, 200, None
    try:
        reason = r.json().get("reason")
    except Exception:
        reason = None
    return False, r.status_code, reason


def is_dead_token(status: Optional[int], reason: Optional[str]) -> bool:
    return status == 410 or reason in ("BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic")
