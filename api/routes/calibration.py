"""GET/PUT /calibration: the interface stores whatever baseline the model produced, but only if it
passes the calibration gate (a good goal posture). The model owns what the angles mean; the gate
(api/core/calibration_gate.py) checks the spine/back angle (`goal.torsoAngle`)."""
from __future__ import annotations

import math
from typing import Any

from flask import Blueprint, g

from api import util
from api.auth import any_client
from api.core.calibration_gate import BACK_ANGLE_KEY, back_angle_issues
from api.db import get_store
from api.errors import ApiError

bp = Blueprint("calibration", __name__)


def _not_good(issues: list[str]) -> ApiError:
    detail = "; ".join(issues) if issues else "sit upright with your back supported and try again"
    return ApiError(422, "posture_not_good", f"That wasn't a good goal posture: {detail}.", {"issues": issues})


def _finite_number(v: Any) -> bool:
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


def _validate(b: dict[str, Any]) -> dict[str, Any]:
    # Gate 1: the model's own verdict (`accepted`, optional, defaults to true for models that don't
    # report one). `accepted`/`issues` are verdict fields and are never stored.
    accepted = b.get("accepted", True)
    if not isinstance(accepted, bool):
        raise ApiError(400, "invalid_baseline", "accepted must be a boolean")
    if accepted is False:
        raw = b.get("issues")
        issues = [i.strip()[:120] for i in raw[:5] if isinstance(i, str) and i.strip()] if isinstance(raw, list) else []
        raise _not_good(issues)

    goal = b.get("goal")
    if not isinstance(goal, dict) or not goal:
        raise ApiError(400, "invalid_baseline", "goal must be a non-empty object of numbers")
    clean_goal: dict[str, float] = {}
    for k, v in goal.items():
        if not _finite_number(v):          # also rejects NaN/Infinity, which json.loads accepts
            raise ApiError(400, "invalid_baseline", f"goal.{k} must be a finite number")
        clean_goal[str(k)] = float(v)
    tol = b.get("tolerance")
    if not _finite_number(tol) or tol <= 0:
        raise ApiError(400, "invalid_baseline", "tolerance must be a positive number")
    captured = b.get("capturedAt")
    if not _finite_number(captured) or captured <= 0:
        raise ApiError(400, "invalid_baseline", "capturedAt must be epoch milliseconds")
    if BACK_ANGLE_KEY not in clean_goal:
        raise ApiError(400, "invalid_baseline",
                       f"goal.{BACK_ANGLE_KEY} (spine/back angle) is required so the posture can be checked")

    # Gate 2: the interface's own check of the spine/back angle, applied to EVERY baseline so a model
    # that forgets to judge can't get a slouched goal saved.
    issues = back_angle_issues(clean_goal)
    if issues:
        raise _not_good(issues)
    return {"schema": util.SCHEMA, "goal": clean_goal, "tolerance": float(tol), "capturedAt": int(captured)}


@bp.get("/calibration")
@any_client
def get_calibration():
    baseline = g.user.get("calibration")
    return {"schema": util.SCHEMA, "calibrated": bool(baseline), "baseline": baseline or None}


@bp.put("/calibration")
@any_client
def put_calibration():
    body = util.json_body()
    baseline = _validate(body.get("baseline", body))
    get_store().update_user(g.user["id"], {"calibration": baseline})
    return {"schema": util.SCHEMA, "calibrated": True, "baseline": baseline}
