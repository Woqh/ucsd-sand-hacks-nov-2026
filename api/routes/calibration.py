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
    # The calibration gate: the model decides whether the captured posture is a good goal posture
    # (`accepted`, optional, defaults to true for models that don't report it) and we refuse to store
    # one it rejected, so a slouched "goal" can never become the baseline. `accepted`/`issues` are
    # verdict fields, not part of the stored baseline.
    accepted = b.get("accepted", True)
    if not isinstance(accepted, bool):
        raise ApiError(400, "invalid_baseline", "accepted must be a boolean")
    if accepted is False:
        raw = b.get("issues")
        issues = [i.strip()[:120] for i in raw[:5] if isinstance(i, str) and i.strip()] if isinstance(raw, list) else []
        detail = "; ".join(issues) if issues else "sit upright with your back supported and try again"
        raise ApiError(422, "posture_not_good", f"That wasn't a good goal posture: {detail}.")
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
