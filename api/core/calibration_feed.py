"""Calibration from the live model feed (pure, no I/O).

The real model runs next to the camera (see bridge/) and streams numbers to /posture/ingest. The server
keeps the last ~30 s of those readings in the session (`recent`) so that the dashboard's guided
calibration ("sit comfortably, hold still for 10 s") can turn them into a goal posture without any
command channel to the camera machine. The model still owns the *measurements* (angles, whether it could
see you); this module only averages them and judges steadiness, then the interface's own back-angle gate
(`calibration_gate`, applied again by PUT /calibration) decides whether it is a good posture.

A `recent` entry is `[t, torsoAngle, neckAngle, headForwardOffset, ok]` (None for a missing feature),
JSON-safe so it rides in the session state for both stores.
"""
from __future__ import annotations

import statistics
from typing import Any, Optional, Sequence

RECENT_KEEP_MS = 30_000
RECENT_MAX = 40
WINDOW_MS = 10_000             # the countdown the dashboard shows
MIN_USABLE = 5                 # at ~1 Hz a 10 s window holds ~10
MIN_USABLE_SHARE = 0.6
MAX_TORSO_STD_DEG = 3.0        # "hold still": product parameter, not a medical threshold
LIVE_MAX_AGE_MS = 15_000       # same as the dashboard's "device is online" window


def push_recent(recent: Optional[Sequence[Sequence[Any]]], t: int, ok: bool, features: dict[str, float]) -> list[list[Any]]:
    """Append one reading and drop what is older than RECENT_KEEP_MS (relative to this reading) or beyond
    RECENT_MAX. `ok` = the model saw the person clearly (confident, not AWAY/UNKNOWN)."""
    out = [list(e) for e in (recent or []) if e and e[0] >= t - RECENT_KEEP_MS]
    out.append([int(t), features.get("torsoAngle"), features.get("neckAngle"), features.get("headForwardOffset"), bool(ok)])
    return out[-RECENT_MAX:]


def is_live(recent: Optional[Sequence[Sequence[Any]]], last_seen_server_ms: Optional[int], now_ms: int) -> bool:
    """A feed counts as live only if it has readings AND the device was heard from recently."""
    return bool(recent) and last_seen_server_ms is not None and now_ms - last_seen_server_ms <= LIVE_MAX_AGE_MS


def _mean(values: list[float], digits: int) -> float:
    return round(sum(values) / len(values), digits)


def baseline_from_recent(recent: Sequence[Sequence[Any]], now_ms: int) -> dict[str, Any]:
    """Judge the last WINDOW_MS of the feed. Always returns a CalibrationBaseline-shaped dict with `accepted`
    and `issues`; `goal` is the mean of the usable readings (empty if there were none)."""
    newest = max(e[0] for e in recent)
    window = [e for e in recent if e[0] >= newest - WINDOW_MS]
    usable = [e for e in window if e[4] and e[1] is not None]
    issues: list[str] = []
    if len(usable) < MIN_USABLE or len(usable) < MIN_USABLE_SHARE * len(window):
        issues.append("We couldn't see you clearly for most of the countdown. Sit fully in view of the side camera and try again")
    torso = [float(e[1]) for e in usable]
    spread = statistics.pstdev(torso) if len(torso) >= 2 else 0.0
    if len(usable) >= MIN_USABLE and spread > MAX_TORSO_STD_DEG:
        issues.append("You moved around during the countdown. Sit still in your comfortable position and try again")
    goal: dict[str, float] = {}
    if torso:
        goal["torsoAngle"] = _mean(torso, 1)
        for index, key, digits in ((2, "neckAngle", 1), (3, "headForwardOffset", 3)):
            vals = [float(e[index]) for e in usable if e[index] is not None]
            if len(vals) >= len(usable) / 2:
                goal[key] = _mean(vals, digits)
    return {"goal": goal, "tolerance": round(max(4.0, min(10.0, 2 * spread)), 1), "capturedAt": int(now_ms),
            "accepted": not issues, "issues": issues}
