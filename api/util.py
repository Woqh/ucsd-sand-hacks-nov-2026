from __future__ import annotations

import os
import time
from typing import Any

from flask import request

from api.errors import ApiError

SCHEMA = 1

# A phone with a wildly wrong clock would corrupt analytics, so refuse it with a clear error.
MAX_CLOCK_SKEW_MS = 60 * 60 * 1000
# No sample for this long => /status reports the session as stale / AWAY (computed on read).
STALE_AFTER_SEC = 15


def now_ms() -> int:
    """Wall clock, in one place so tests can patch it. The state machine never calls this: it only
    sees sample timestamps."""
    return int(time.time() * 1000)


def json_body(required: bool = True) -> dict[str, Any]:
    body = request.get_json(silent=True)
    if body is None and not required:
        return {}
    if not isinstance(body, dict):
        raise ApiError(400, "bad_request", "Body must be a JSON object")
    return body


def dev_routes_enabled() -> bool:
    return os.environ.get("ENABLE_DEV_ROUTES", "") in ("1", "true", "True")


def tz_offset_arg() -> int:
    """?tzOffsetMin= (minutes east of UTC, i.e. -new Date().getTimezoneOffset()) for local-day bucketing."""
    raw = request.args.get("tzOffsetMin", "0")
    try:
        v = int(raw)
    except ValueError:
        raise ApiError(400, "bad_request", "tzOffsetMin must be an integer")
    if not -840 <= v <= 840:
        raise ApiError(400, "bad_request", "tzOffsetMin out of range")
    return v
