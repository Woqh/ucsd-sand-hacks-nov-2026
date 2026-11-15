"""Calibration gate, the interface-owned part: is the captured spine/back angle a good one?

A goal posture is only worth saving if it is a posture worth aiming for, so a baseline whose back
angle is outside a healthy RANGE AROUND UPRIGHT (0 degrees) is refused. Leaning too far forward
(slouching) is bad, and so is leaning too far back, so the range has a limit on BOTH sides of 0.
The model may also reject a posture for its own reasons (`accepted: false`); this check runs on
every baseline regardless, so a model that forgets to judge can't get a bad baseline saved.

CONVENTION (confirm with the model teammate, since it defines the payload):
    goal.torsoAngle = trunk (spine/back) inclination from vertical, in DEGREES.
      0   = upright
      +n  = leaning FORWARD n degrees (slouching / trunk flexion)
      -n  = leaning BACK n degrees (reclined against the backrest)
(The example payloads in CLAUDE.md fit this: good about 5, slouched about 18.)

ALLOWED RANGE: from -MAX_BACKWARD_LEAN_DEG to +MAX_FORWARD_LEAN_DEG, always bracketing 0.

The limits are PRODUCT PARAMETERS, not medical thresholds. Start: 10 degrees each way. 10 forward
separates the example good (5) and slouched (18) values. NOTE the tension on the backward side:
ergonomics course notes and handouts (docs/health-claims.md, S5/S6) describe a supported, slightly
reclined back (roughly 10-20 degrees, backrest about 100-110 degrees) as comfortable, so a 10-degree
backward limit will refuse some comfortable reclined postures. Widen MAX_BACKWARD_LEAN_DEG (one
constant) if real users get refused for sitting back. Tune both against real model output.
"""
from __future__ import annotations

import math
from typing import Any

BACK_ANGLE_KEY = "torsoAngle"
MAX_FORWARD_LEAN_DEG = 10.0    # leaning forward more than this = slouching, refuse
MAX_BACKWARD_LEAN_DEG = 10.0   # leaning back more than this = too far from upright, refuse

# The range must bracket 0 (upright); a limit of 0 or less would reject upright itself.
if not (MAX_FORWARD_LEAN_DEG > 0 and MAX_BACKWARD_LEAN_DEG > 0):
    raise ValueError("calibration back-angle limits must be positive so the allowed range brackets 0")

ALLOWED_RANGE_DEG = (-MAX_BACKWARD_LEAN_DEG, MAX_FORWARD_LEAN_DEG)


def back_angle_issues(goal: dict[str, Any]) -> list[str]:
    """User-facing reasons the captured back angle is not a good goal posture ([] = fine).
    Assumes `goal` has already been validated as numbers; a non-finite angle is refused."""
    angle = goal.get(BACK_ANGLE_KEY)
    if angle is None:
        return [f"No spine/back angle ({BACK_ANGLE_KEY}) was measured, so the posture can't be checked"]
    if not math.isfinite(angle):
        return ["The spine/back angle measurement was invalid"]
    if angle > MAX_FORWARD_LEAN_DEG:
        return [f"Your back is leaning forward about {angle:.0f}° (aim for within {MAX_FORWARD_LEAN_DEG:.0f}° of upright)"]
    if angle < -MAX_BACKWARD_LEAN_DEG:
        return [f"Your back is leaning back about {-angle:.0f}° (aim for within {MAX_BACKWARD_LEAN_DEG:.0f}° of upright)"]
    return []
