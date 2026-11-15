"""POST /posture/ingest: the phone's ~1 Hz feed. Loads the session, runs the pure state machine,
persists new state + events, fires alerts, returns the current state."""
from __future__ import annotations

from typing import Any

from flask import Blueprint, g

from api import util
from api.auth import device_only
from api.core import calibration_feed
from api.core.settings import SampleError, config_from_settings, parse_sample
from api.core.state_machine import AWAY, MIN_CONFIDENCE, MachineState, step
from api.db import get_store
from api.errors import ApiError
from api.push import dispatch

bp = Blueprint("posture", __name__)

SAMPLE_EVERY_MS = 5_000  # downsample the ~1 Hz feed to one stored reading per 5 s
MAX_SOURCE_LEN = 80


def _event_row(user_id: str, session_id: str, e: dict[str, Any]) -> dict[str, Any]:
    return {"user_id": user_id, "session_id": session_id, "t": e["t"], "kind": e["kind"],
            "from_state": e["from_state"], "to_state": e["to_state"], "alert": e["alert"],
            "level": e["level"], "reason": e["reason"], "deviation": e["deviation"]}


@bp.post("/posture/ingest")
@device_only
def ingest():
    user = g.user
    if (user.get("settings") or {}).get("dataCollectionConsent") is not True:
        raise ApiError(403, "collection_consent_required", "Allow posture data collection in Settings before sending readings.")
    store = get_store()
    body = util.json_body()
    try:
        sid, sample, features = parse_sample(body)
    except SampleError as exc:
        raise ApiError(400, "bad_sample", str(exc))

    now = util.now_ms()
    if abs(sample.t - now) > util.MAX_CLOCK_SKEW_MS:
        raise ApiError(400, "clock_skew", "Sample timestamp is more than 1 hour from server time; "
                                          "check the phone's clock")

    cfg = config_from_settings(user.get("settings"))
    sess = store.get_session(sid)
    rows: list[dict[str, Any]] = []

    if sess is None:
        # New session (app restarted, new sessionId). Close the previous one at the last time we
        # saw it, otherwise its open state would stretch across the gap in analytics.
        prev = store.latest_session(user["id"])
        if prev:
            pm = MachineState.from_dict(prev["state"])
            if pm.state != AWAY:
                end_t = pm.last_t or prev["last_t"]
                rows.append({"user_id": user["id"], "session_id": prev["id"], "t": end_t,
                             "kind": "transition", "from_state": pm.state, "to_state": AWAY,
                             "alert": False, "level": 0, "reason": "session_replaced",
                             "deviation": None})
                prev["state"] = MachineState(state=AWAY, since=end_t, last_t=end_t).to_dict()
                store.save_session(prev)
        machine = MachineState()
        started_at = sample.t
        last_t = sample.t
    else:
        if sess["user_id"] != user["id"]:
            raise ApiError(403, "forbidden", "sessionId belongs to another user")
        machine = MachineState.from_dict(sess["state"])
        started_at = sess["started_at"]
        last_t = max(sess["last_t"], sample.t)

    new_machine, events = step(machine, sample, cfg)
    rows += [_event_row(user["id"], sid, e.to_dict()) for e in events]
    if rows:
        store.insert_events(rows)

    # Keep at most one posture reading per SAMPLE_EVERY_MS (the `samples` hypertable). The time of the
    # last stored one rides along in the session's state JSON (the state machine ignores unknown keys).
    state_dict = new_machine.to_dict()
    last_stored = int((sess or {}).get("state", {}).get("stored_sample_t") or 0)
    usable = sample.confidence >= MIN_CONFIDENCE and sample.label != "UNKNOWN"
    if usable and sample.t - last_stored >= SAMPLE_EVERY_MS:
        store.insert_samples([{
            "user_id": user["id"], "session_id": sid, "t": sample.t, "state": new_machine.state,
            "label": sample.label, "deviation": sample.deviation, "confidence": sample.confidence,
            "neck": features.get("neckAngle"), "torso": features.get("torsoAngle"),
            "head_fwd": features.get("headForwardOffset")}])
        last_stored = sample.t
    if last_stored:
        state_dict["stored_sample_t"] = last_stored
    # The last ~30 s of readings, so the dashboard's guided calibration can use the live model feed.
    seen_well = sample.confidence >= MIN_CONFIDENCE and sample.label in ("GOOD", "SLOUCHING")
    state_dict["recent"] = calibration_feed.push_recent((sess or {}).get("state", {}).get("recent"), sample.t, seen_well, features)

    last_sample: dict[str, Any] = {"t": sample.t, "label": sample.label, "deviation": sample.deviation,
                                   "confidence": sample.confidence, "features": features}
    source = body.get("source")                       # optional: which model produced this ("posture-pipeline/...")
    if isinstance(source, str) and source.strip() and len(source) <= MAX_SOURCE_LEN and source.isprintable():
        last_sample["source"] = source.strip()

    store.save_session({
        "id": sid, "user_id": user["id"], "started_at": started_at, "last_t": last_t,
        "last_seen_server_ms": now, "state": state_dict,
        "last_sample": last_sample,
    })

    alert = None
    for e in events:
        if e.alert:
            alert = dispatch.send_alert(store, user, e.level)  # push failures are reported, never raised

    return {
        "schema": util.SCHEMA,
        "state": new_machine.state,
        "stateSince": new_machine.since,
        "serverTime": now,
        "alert": alert,
    }
