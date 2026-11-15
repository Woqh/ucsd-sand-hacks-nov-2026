"""Coach: the personal analysis pack, the optional Gemini layer, and raw segments for local overlays.

The pack (`GET /coach/insights`) is computed from the user's own data with no AI and no identifiers.
Gemini is optional and consent-gated; nothing it returns is stored here, because the profile lives
only in the user's browser. See api/ai/gemini.py for the privacy and terms notes."""
from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, g, request

from api import util
from api.ai import gemini, prompts, schemas
from api.ai.gemini import AIError
from api.auth import dashboard_only
from api.core import coach_pack, scoring
from api.core import posture_profile as pp
from api.core.settings import merge_settings
from api.db import get_store
from api.errors import ApiError

bp = Blueprint("coach", __name__)

WINDOW_DAYS = 42
DAY = scoring.DAY_MS
STATE_CODE = {"GOOD": "G", "DEVIATING": "D", "SLOUCHING": "S", "AWAY": "A"}

DISCLOSURE = [
    "Only the de-identified habit numbers shown in the preview are sent. No name, email, account ID, dates or images.",
    "Your pain check-ins are never sent.",
    "Google processes what you send under the Gemini API terms. Use a key from a paid (billing-enabled) project: Google's terms say the free tier may use inputs to improve its products and have humans review them, and forbid sending personal or sensitive information.",
    "Nothing is stored on the Sitwise server. The result is saved only in this browser, and you can delete it any time.",
    "It's coaching about habits, not medical advice.",
]


def build_user_pack(store: Any, user: dict[str, Any], tz: int, now: int) -> dict[str, Any]:
    """Fetch the user's last WINDOW_DAYS of data and assemble the de-identified pack."""
    uid = user["id"]
    off = tz * 60_000
    today_idx = (now + off) // DAY
    first = today_idx - WINDOW_DAYS + 1
    since = first * DAY - off
    events = store.list_events(uid, since, now)
    prior = store.last_event_before(uid, since)
    sess = store.latest_session(uid)
    segs = scoring.build_segments(events, prior, since, now, sess["last_t"] if sess else None)
    win = scoring.clip(segs, since, now)
    settings, _ = merge_settings(user.get("settings"), {})
    return coach_pack.build_pack(
        now_ms=now, tz_offset_min=tz, window_days=WINDOW_DAYS, segs=segs, events=events,
        daily=scoring.fill_days(scoring.daily_breakdown(win, tz), first, today_idx),
        heat=scoring.heatmap(win, tz), rollups=store.sample_rollup(uid, since, now), settings=settings,
        calibrations=store.list_calibrations(uid, 20))


def _ai_info() -> dict[str, Any]:
    ok = gemini.configured()
    return {"configured": ok, "model": gemini.model_name() if ok else None}


@bp.get("/coach/insights")
@dashboard_only
def insights():
    """The full on-device analysis (no AI involved)."""
    pack = build_user_pack(get_store(), g.user, util.tz_offset_arg(), util.now_ms())
    # the full exercise library (with steps) is for the dashboard only; it is never part of what Gemini receives
    library = [dict(e, safety=pp.SAFETY_NOTE) for e in pp.EXERCISES]
    return {"schema": util.SCHEMA, "pack": pack, "library": library, "ai": _ai_info()}


@bp.get("/coach/preview")
@dashboard_only
def preview():
    """Exactly what would be sent to Gemini, so the user can inspect it before opting in. Sends nothing."""
    payload = coach_pack.compact_for_ai(build_user_pack(get_store(), g.user, util.tz_offset_arg(), util.now_ms()))
    return {"schema": util.SCHEMA, "payload": payload, "bytes": len(json.dumps(payload)),
            "disclosure": DISCLOSURE, "ai": _ai_info()}


# ------------------------------------------------------------------ Gemini (consent-gated, never stored)
def _guard(body: dict[str, Any]) -> None:
    if body.get("consent") is not True:
        raise ApiError(400, "consent_required", "Sending data to Gemini needs your explicit opt-in (consent: true).")
    if not gemini.configured():
        raise ApiError(503, "ai_not_configured", "AI analysis isn't enabled on this server. The on-device analysis still works.")
    try:
        gemini.check_rate(g.user["id"])
    except AIError as e:
        raise ApiError(e.status, e.code, e.message)


def _call(system: str, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    try:
        return gemini.generate_json(system, payload, schema)
    except AIError as e:
        raise ApiError(e.status, e.code, e.message)


@bp.post("/coach/analyze")
@dashboard_only
def analyze():
    """Build the coaching profile with Gemini from the de-identified pack. Returns it (and the exact
    payload that was sent); stores nothing."""
    body = util.json_body()
    _guard(body)
    payload = coach_pack.compact_for_ai(build_user_pack(get_store(), g.user, util.tz_offset_arg(), util.now_ms()))
    analysis = _call(prompts.ANALYSIS_SYSTEM, payload, schemas.ANALYSIS_SCHEMA)
    return {"schema": util.SCHEMA, "analysis": analysis, "model": gemini.model_name(), "sent": payload}


@bp.post("/coach/ask")
@dashboard_only
def ask():
    """Answer a question about the user's own habits (and the cited evidence only)."""
    body = util.json_body()
    q = body.get("question")
    if not isinstance(q, str) or not 3 <= len(q.strip()) <= 300:
        raise ApiError(400, "bad_request", "question must be 3 to 300 characters")
    _guard(body)
    habits = coach_pack.compact_for_ai(build_user_pack(get_store(), g.user, util.tz_offset_arg(), util.now_ms()))
    out = _call(prompts.ASK_SYSTEM, {"question": q.strip(), "habits": habits}, schemas.ASK_SCHEMA)
    return {"schema": util.SCHEMA, **out}


def _patch_from_flat(out: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {k: out[k] for k in ("slouchThresholdSec", "sensitivity", "cooldownSec", "nudgeTone") if k in out}
    chan = {k: out[src] for k, src in (("phone", "phoneAlerts"), ("desktop", "desktopAlerts")) if src in out}
    if chan:
        patch["alertChannels"] = chan
    quiet = {k: out[src] for k, src in (("enabled", "quietHoursEnabled"), ("start", "quietStart"), ("end", "quietEnd")) if src in out}
    if quiet:
        patch["quietHours"] = quiet
    if "onlyDuringFocus" in out:
        patch["focus"] = {"onlyDuringFocus": out["onlyDuringFocus"]}
    return patch


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flatten(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


@bp.post("/coach/settings-from-text")
@dashboard_only
def settings_from_text():
    """Turn 'I work 9-6 and hate interruptions in meetings' into a PROPOSED settings change. Nothing is
    applied: the dashboard shows the diff and the user confirms with a normal PUT /settings."""
    body = util.json_body()
    text = body.get("text")
    if not isinstance(text, str) or not 3 <= len(text.strip()) <= 400:
        raise ApiError(400, "bad_request", "text must be 3 to 400 characters")
    _guard(body)
    current, _ = merge_settings(g.user.get("settings"), {})
    shown = {k: current[k] for k in ("slouchThresholdSec", "sensitivity", "cooldownSec", "alertChannels", "quietHours", "nudgeTone")}
    out = _call(prompts.SETTINGS_SYSTEM, {"text": text.strip(), "current": shown}, schemas.SETTINGS_TEXT_SCHEMA)
    patch = _patch_from_flat(out)
    merged, errors = merge_settings(g.user.get("settings"), patch)    # the same validation the settings API uses
    if errors:
        raise ApiError(502, "ai_bad_output", "The AI service returned settings we couldn't use.")
    before, after = _flatten(current), _flatten(merged)
    changes = [{"field": k, "from": before.get(k), "to": after[k]} for k in after if before.get(k) != after[k]]
    return {"schema": util.SCHEMA, "explanation": out["explanation"], "patch": patch, "changes": changes}


# ------------------------------------------------------------------ segments (for local calendar overlays)
@bp.get("/segments")
@dashboard_only
def segments():
    """Compact posture segments for the last `days` (1-30, default 14) as [startMs, endMs, code] with code
    G=good D=drifting S=slouching A=away. For the dashboard to overlay a calendar file locally."""
    try:
        days = int(request.args.get("days", 14))
    except ValueError:
        raise ApiError(400, "bad_request", "days must be an integer")
    if not 1 <= days <= 30:
        raise ApiError(400, "bad_request", "days must be between 1 and 30")
    store = get_store()
    uid = g.user["id"]
    now = util.now_ms()
    since = now - days * DAY
    events = store.list_events(uid, since, now)
    prior = store.last_event_before(uid, since)
    sess = store.latest_session(uid)
    segs = scoring.build_segments(events, prior, since, now, sess["last_t"] if sess else None)
    return {"schema": util.SCHEMA, "since": since, "until": now,
            "segments": [[s.start, s.end, STATE_CODE[s.state]] for s in segs]}
