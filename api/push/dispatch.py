"""Fan an alert out to the channels the user enabled. Failures are reported, never raised:
a broken push provider must not break posture ingest."""
from __future__ import annotations

from typing import Any

from api.push import apns, webpush

# Gentle escalation: same tone, a bit more insistent each time, then we stop.
MESSAGES = {
    1: ("Sit up tall", "You've been slouching a little. Roll your shoulders back and reset."),
    2: ("Still slouching", "Quick fix: chin tuck, shoulders down, feet flat."),
    3: ("Take a stretch break?", "Stand up for a minute. Your back will thank you."),
}


def _message(level: int) -> tuple[str, str]:
    return MESSAGES.get(level) or MESSAGES[max(MESSAGES)]


def _send_phone(store: Any, user_id: str, title: str, body: str) -> dict[str, Any]:
    subs = store.list_push_subscriptions(user_id, "apns")
    if not subs:
        return {"sent": 0, "failed": 0, "skipped": "no_device_registered"}
    if not apns.configured():
        return {"sent": 0, "failed": 0, "skipped": "apns_not_configured"}
    sent = failed = 0
    for s in subs:
        ok, status, reason = apns.send(s["endpoint"], title, body, sandbox=(s.get("data") or {}).get("sandbox"))
        if ok:
            sent += 1
        else:
            failed += 1
            if apns.is_dead_token(status, reason):
                store.delete_push_subscription(user_id, "apns", s["endpoint"])
    return {"sent": sent, "failed": failed, "skipped": None}


def _send_desktop(store: Any, user_id: str, title: str, body: str) -> dict[str, Any]:
    subs = store.list_push_subscriptions(user_id, "web")
    if not subs:
        return {"sent": 0, "failed": 0, "skipped": "no_browser_subscribed"}
    if not webpush.configured():
        return {"sent": 0, "failed": 0, "skipped": "vapid_not_configured"}
    sent = failed = 0
    for s in subs:
        sub = {"endpoint": s["endpoint"], "keys": (s.get("data") or {}).get("keys", {})}
        ok, status, _ = webpush.send(sub, title, body)
        if ok:
            sent += 1
        else:
            failed += 1
            if webpush.is_dead_subscription(status):
                store.delete_push_subscription(user_id, "web", s["endpoint"])
    return {"sent": sent, "failed": failed, "skipped": None}


def send_alert(store: Any, user: dict[str, Any], level: int) -> dict[str, Any]:
    """Send the nudge to every channel enabled in the user's settings."""
    channels = ((user.get("settings") or {}).get("alertChannels")) or {"phone": True, "desktop": True}
    title, body = _message(level)
    out: dict[str, Any] = {"level": level, "channels": {}}
    if channels.get("phone", True):
        out["channels"]["phone"] = _send_phone(store, user["id"], title, body)
    if channels.get("desktop", True):
        out["channels"]["desktop"] = _send_desktop(store, user["id"], title, body)
    return out


def send_test(store: Any, user: dict[str, Any], channel: str) -> dict[str, Any]:
    title, body = "Sitwise test notification", "If you can read this, alerts are working."
    if channel == "phone":
        return _send_phone(store, user["id"], title, body)
    return _send_desktop(store, user["id"], title, body)
