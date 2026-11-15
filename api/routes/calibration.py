"""GET/PUT /calibration: the interface stores whatever baseline the model produced.
It doesn't interpret the angles; the model owns their meaning (see docs/api.md)."""
from __future__ import annotations

from typing import Any

from flask import Blueprint, g

from api import util
from api.auth import any_client
from api.db import get_store
from api.errors import ApiError

bp = Blueprint("calibration", __name__)


def _validate(b: dict[str, Any]) -> dict[str, Any]:
    goal = b.get("goal")
    if not isinstance(goal, dict) or not goal:
        raise ApiError(400, "invalid_baseline", "goal must be a non-empty object of numbers")
    clean_goal = {}
    for k, v in goal.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ApiError(400, "invalid_baseline", f"goal.{k} must be a number")
        clean_goal[str(k)] = float(v)
    tol = b.get("tolerance")
    if isinstance(tol, bool) or not isinstance(tol, (int, float)) or tol <= 0:
        raise ApiError(400, "invalid_baseline", "tolerance must be a positive number")
    captured = b.get("capturedAt")
    if isinstance(captured, bool) or not isinstance(captured, (int, float)) or captured <= 0:
        raise ApiError(400, "invalid_baseline", "capturedAt must be epoch milliseconds")
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
