"""Web Push (VAPID) via pywebpush. Env: VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT."""
from __future__ import annotations

import json
import os
from typing import Any, Optional


def configured() -> bool:
    return all(os.environ.get(k) for k in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_SUBJECT"))


def public_key() -> Optional[str]:
    return os.environ.get("VAPID_PUBLIC_KEY") or None


def send(subscription: dict[str, Any], title: str, body: str, *, tag: str = "posture",
         url: str = "/") -> tuple[bool, Optional[int], Optional[str]]:
    """`subscription` is the browser PushSubscription JSON ({endpoint, keys:{p256dh,auth}}).
    Returns (ok, http_status, reason); status 404/410 means the subscription is gone."""
    if not configured():
        return False, None, "not_configured"
    try:
        from pywebpush import WebPushException, webpush
    except Exception as exc:  # pragma: no cover
        return False, None, f"error:{type(exc).__name__}"
    try:
        webpush(subscription_info=subscription,
                data=json.dumps({"title": title, "body": body, "tag": tag, "url": url}),
                vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
                vapid_claims={"sub": os.environ["VAPID_SUBJECT"]}, ttl=120)
        return True, 201, None
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return False, status, "web_push_error"
    except Exception as exc:
        return False, None, f"error:{type(exc).__name__}"


def is_dead_subscription(status: Optional[int]) -> bool:
    return status in (404, 410)
