"""MODEL STUBS (+ the live-feed calibration): the teammate owns the real model, which runs next to the
camera and streams numbers to /posture/ingest (see bridge/ and docs/model-bridge.md). Each route returns
fixed, valid mock data with "stub": true UNLESS a live model feed is present, in which case calibration
is computed from that feed (`stub: false`) and /model/health says so. The contract (shapes below) must
not change without flagging it."""
from __future__ import annotations

from typing import Any, Optional

from flask import Blueprint, g, request

from api import util
from api.auth import any_client
from api.core import calibration_feed
from api.core.calibration_gate import back_angle_issues
from api.db import get_store

bp = Blueprint("model_stubs", __name__)


def _live_feed() -> Optional[tuple[dict[str, Any], list[Any]]]:
    """The user's latest session and its recent readings, if a model has been streaming just now."""
    sess = get_store().latest_session(g.user["id"])
    if not sess:
        return None
    recent = (sess.get("state") or {}).get("recent")
    if not calibration_feed.is_live(recent, sess.get("last_seen_server_ms"), util.now_ms()):
        return None
    return sess, recent

STUB_FEATURES_GOOD = {"neckAngle": 16.0, "torsoAngle": 5.5, "headForwardOffset": 0.19}
STUB_FEATURES_SLOUCH = {"neckAngle": 34.0, "torsoAngle": 18.0, "headForwardOffset": 0.52}


@bp.post("/model/analyze")
@any_client
def analyze():
    """Takes a feature packet (ignored by the stub). `?force=slouch` returns SLOUCHING so alerts
    can be tested end to end."""
    body = request.get_json(silent=True) or {}
    slouch = request.args.get("force") == "slouch"
    return {
        "schema": util.SCHEMA,
        "sessionId": body.get("sessionId", "00000000-0000-4000-8000-000000000000"),
        "t": body.get("t", util.now_ms()),
        "label": "SLOUCHING" if slouch else "GOOD",
        "deviation": 0.72 if slouch else 0.12,
        "confidence": 0.93,
        "features": STUB_FEATURES_SLOUCH if slouch else STUB_FEATURES_GOOD,
        "stub": True,
    }


@bp.post("/model/calibrate/start")
@any_client
def calibrate_start():
    return {"schema": util.SCHEMA, "status": "started", "stub": True}


@bp.post("/model/calibrate/finish")
@any_client
def calibrate_finish():
    """Returns a mock baseline. `?force=bad` simulates the model REJECTING the captured posture
    (`accepted: false` + `issues`) so the calibration gate and its UI can be tested end to end."""
    if request.args.get("force") == "bad":
        goal = dict(STUB_FEATURES_SLOUCH)           # what it "measured": a slouched posture
        issues = back_angle_issues(goal) + ["Your head is too far forward of your shoulders"]
        return {"schema": util.SCHEMA, "goal": goal, "tolerance": 6.0, "capturedAt": util.now_ms(),
                "accepted": False, "issues": issues, "stub": True}
    live = _live_feed()
    if live:
        # A real model is streaming: average what it measured during the countdown. The steadiness and
        # visibility checks live in core/calibration_feed; the back-angle gate is applied here and again by
        # PUT /calibration.
        sess, recent = live
        out = calibration_feed.baseline_from_recent(recent, util.now_ms())
        if out["goal"].get("torsoAngle") is not None:
            out["issues"] += back_angle_issues(out["goal"])
        out["accepted"] = not out["issues"]
        return {"schema": util.SCHEMA, **out, "stub": False, "source": (sess.get("last_sample") or {}).get("source")}
    goal = {"neckAngle": 15.0, "torsoAngle": 5.0, "headForwardOffset": 0.18}
    issues = back_angle_issues(goal)                # the stub judges with the same back-angle gate
    return {"schema": util.SCHEMA, "goal": goal, "tolerance": 6.0, "capturedAt": util.now_ms(),
            "accepted": not issues, "issues": issues, "stub": True}


@bp.get("/model/health")
@any_client
def model_health():
    """`stub` is false while a real model is streaming to this account (`live`), true otherwise."""
    live = _live_feed()
    source = (live[0].get("last_sample") or {}).get("source") if live else None
    return {"schema": util.SCHEMA, "ready": True, "stub": live is None, "live": live is not None, "source": source}
