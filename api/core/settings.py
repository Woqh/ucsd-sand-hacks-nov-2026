"""User settings: defaults, validation/merge, and conversion to the state machine's Config. Pure."""
from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Optional

from api.core.state_machine import Config, Sample

SCHEMA = 1

DEFAULT_SETTINGS: dict[str, Any] = {
    "schema": SCHEMA,
    "slouchThresholdSec": 30,
    "sensitivity": 0.5,
    "alertChannels": {"phone": True, "desktop": True},
    "cooldownSec": 120,
    "quietHours": {"enabled": False, "start": "22:00", "end": "07:00"},
    "tzOffsetMin": 0,
    "nudgeTone": "gentle",
    "focus": {"onlyDuringFocus": False, "untilMs": 0},
}

TONES = ("gentle", "neutral", "direct")

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def merge_settings(current: Optional[dict[str, Any]], patch: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Apply a partial update to `current` (None -> defaults). Returns (settings, errors).
    Unknown keys are ignored. On any error the caller should reject the whole patch."""
    out = copy.deepcopy(DEFAULT_SETTINGS)
    if current:
        out = _deep_update(out, current)
    errors: list[str] = []

    def ranged(key: str, lo: float, hi: float, integer: bool = False) -> None:
        if key not in patch:
            return
        n = _num(patch[key])
        if n is None or not (lo <= n <= hi):
            errors.append(f"{key} must be a number between {lo:g} and {hi:g}")
        else:
            out[key] = int(round(n)) if integer else n

    ranged("slouchThresholdSec", 5, 900, integer=True)
    ranged("sensitivity", 0, 1)
    ranged("cooldownSec", 15, 3600, integer=True)
    ranged("tzOffsetMin", -840, 840, integer=True)

    if "alertChannels" in patch:
        ch = patch["alertChannels"]
        if not isinstance(ch, dict):
            errors.append("alertChannels must be an object")
        else:
            for k in ("phone", "desktop"):
                if k in ch:
                    if isinstance(ch[k], bool):
                        out["alertChannels"][k] = ch[k]
                    else:
                        errors.append(f"alertChannels.{k} must be a boolean")

    if "nudgeTone" in patch:
        if patch["nudgeTone"] in TONES:
            out["nudgeTone"] = patch["nudgeTone"]
        else:
            errors.append(f"nudgeTone must be one of {', '.join(TONES)}")

    if "focus" in patch:
        fc = patch["focus"]
        if not isinstance(fc, dict):
            errors.append("focus must be an object")
        else:
            if "onlyDuringFocus" in fc:
                if isinstance(fc["onlyDuringFocus"], bool):
                    out["focus"]["onlyDuringFocus"] = fc["onlyDuringFocus"]
                else:
                    errors.append("focus.onlyDuringFocus must be a boolean")
            if "untilMs" in fc:
                n = _num(fc["untilMs"])
                if n is None or not (0 <= n <= 4_102_444_800_000):
                    errors.append("focus.untilMs must be epoch milliseconds (or 0)")
                else:
                    out["focus"]["untilMs"] = int(n)

    if "quietHours" in patch:
        qh = patch["quietHours"]
        if not isinstance(qh, dict):
            errors.append("quietHours must be an object")
        else:
            if "enabled" in qh:
                if isinstance(qh["enabled"], bool):
                    out["quietHours"]["enabled"] = qh["enabled"]
                else:
                    errors.append("quietHours.enabled must be a boolean")
            for k in ("start", "end"):
                if k in qh:
                    if isinstance(qh[k], str) and _HHMM.match(qh[k]):
                        out["quietHours"][k] = qh[k]
                    else:
                        errors.append(f"quietHours.{k} must be HH:MM (24h)")

    out["schema"] = SCHEMA
    return out, errors


def _deep_update(base: dict[str, Any], upd: dict[str, Any]) -> dict[str, Any]:
    for k, v in upd.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            base[k] = _deep_update(base[k], v)
        elif k in base:
            base[k] = v
    return base


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def config_from_settings(settings: Optional[dict[str, Any]]) -> Config:
    s, _ = merge_settings(settings, {})
    qh = s["quietHours"]
    return Config(
        slouch_threshold_sec=float(s["slouchThresholdSec"]),
        sensitivity=float(s["sensitivity"]),
        cooldown_sec=float(s["cooldownSec"]),
        alert_phone=bool(s["alertChannels"]["phone"]),
        alert_desktop=bool(s["alertChannels"]["desktop"]),
        quiet_hours_enabled=bool(qh["enabled"]),
        quiet_start_min=_minutes(qh["start"]),
        quiet_end_min=_minutes(qh["end"]),
        tz_offset_min=int(s["tzOffsetMin"]),
        focus_only=bool(s["focus"]["onlyDuringFocus"]),
        focus_until_ms=int(s["focus"]["untilMs"]),
    )


# ------------------------------------------------------------------ PostureSample

LABELS = ("GOOD", "SLOUCHING", "AWAY", "UNKNOWN")


class SampleError(ValueError):
    pass


def parse_sample(payload: Any) -> tuple[str, Sample, dict[str, Any]]:
    """Validate a PostureSample. Returns (session_id, Sample, extras) where extras = features dict.
    Raises SampleError with a human-readable message."""
    if not isinstance(payload, dict):
        raise SampleError("body must be a JSON object")
    sid = payload.get("sessionId")
    try:
        sid = str(uuid.UUID(sid)) if isinstance(sid, str) else None   # canonical lowercase
    except ValueError:
        sid = None
    if sid is None:
        raise SampleError("sessionId must be a UUID string")
    t = payload.get("t")
    if isinstance(t, bool) or not isinstance(t, (int, float)) or t <= 0:
        raise SampleError("t must be epoch milliseconds")
    label = payload.get("label")
    if label not in LABELS:
        raise SampleError(f"label must be one of {', '.join(LABELS)}")
    dev = payload.get("deviation")
    if dev is not None:
        if isinstance(dev, bool) or not isinstance(dev, (int, float)) or dev < 0:
            raise SampleError("deviation must be a number >= 0")
        dev = float(dev)
    conf = payload.get("confidence", 1.0)
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not (0 <= conf <= 1):
        raise SampleError("confidence must be between 0 and 1")
    features = payload.get("features") or {}
    if not isinstance(features, dict):
        raise SampleError("features must be an object")
    features = {k: float(v) for k, v in features.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)}
    return sid, Sample(t=int(t), label=label, deviation=dev, confidence=float(conf)), features
