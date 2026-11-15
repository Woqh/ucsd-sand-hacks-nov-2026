"""GET /status: what the dashboard polls (~2 s). Staleness is computed here, on read, because
nothing runs in the background on Vercel."""
from __future__ import annotations

from flask import Blueprint, g

from api import util
from api.auth import dashboard_only
from api.core.settings import config_from_settings
from api.core.state_machine import AWAY, MachineState, describe
from api.db import get_store
from api.routes.metrics import day_snapshot

bp = Blueprint("status", __name__)


@bp.get("/status")
@dashboard_only
def status():
    user = g.user
    store = get_store()
    now = util.now_ms()
    cfg = config_from_settings(user.get("settings"))
    sess = store.latest_session(user["id"])

    out = {
        "schema": util.SCHEMA,
        "paired": bool(user.get("device_token_hash")),
        "calibrated": bool(user.get("calibration")),
        "serverTime": now,
        "thresholdSec": cfg.slouch_threshold_sec,
        "device": {"lastSeenMs": None, "ageSec": None, "online": False},
        "state": AWAY,
        "rawState": AWAY,
        "stale": True,
        "timeInStateSec": 0,
        "deviatingForSec": None,
        "inCooldown": False,
        "alertsSent": 0,
        "sample": None,
    }

    if sess:
        age_ms = max(0, now - sess["last_seen_server_ms"])
        stale = age_ms > util.STALE_AFTER_SEC * 1000
        machine = MachineState.from_dict(sess["state"])
        # `last_t` and `since` are both phone-clock, so their difference is skew-proof; add the
        # server-clock age since we last heard from the phone.
        info = describe(machine, (machine.last_t or 0) + age_ms, cfg)
        out.update({
            "device": {"lastSeenMs": sess["last_seen_server_ms"], "ageSec": round(age_ms / 1000, 1),
                       "online": not stale},
            "rawState": machine.state,
            "state": AWAY if stale else machine.state,
            "stale": stale,
            "timeInStateSec": round(info["timeInStateSec"], 1),
            "deviatingForSec": None if stale or info["deviatingForSec"] is None
            else round(info["deviatingForSec"], 1),
            "inCooldown": False if stale else info["inCooldown"],
            "alertsSent": info["alertsSent"],
            "sample": sess.get("last_sample"),
        })

    out["today"] = day_snapshot(store, user["id"], cfg.tz_offset_min, now)
    return out
