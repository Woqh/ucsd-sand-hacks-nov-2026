"""MODEL STUBS: the teammate owns the real internals. Each route returns fixed, valid mock data
with "stub": true, and the contract (shapes below) must not change without flagging it.
Everything the model does is meant to run on the phone; these exist so the UI can be built and
demoed, and as a server-side fallback if the model can't run fully on-device."""
from __future__ import annotations

from flask import Blueprint, request

from api import util
from api.auth import any_client

bp = Blueprint("model_stubs", __name__)

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
        return {
            "schema": util.SCHEMA,
            "goal": STUB_FEATURES_SLOUCH,           # what it measured: a slouched posture
            "tolerance": 6.0,
            "capturedAt": util.now_ms(),
            "accepted": False,
            "issues": ["Your head is too far forward of your shoulders", "Your upper back is rounded"],
            "stub": True,
        }
    return {
        "schema": util.SCHEMA,
        "goal": {"neckAngle": 15.0, "torsoAngle": 5.0, "headForwardOffset": 0.18},
        "tolerance": 6.0,
        "capturedAt": util.now_ms(),
        "accepted": True,
        "issues": [],
        "stub": True,
    }


@bp.get("/model/health")
@any_client
def model_health():
    return {"schema": util.SCHEMA, "ready": True, "stub": True}
