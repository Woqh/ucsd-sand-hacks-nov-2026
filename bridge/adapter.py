"""Turn the teammate's posture pipeline output into a Sitwise PostureSample (pure, no I/O, no numpy).

The pipeline (posture_pipeline-main/) is the MODEL: it finds the person, measures projected angles and,
for a side camera, labels upright / leaning_forward / leaning_back with a deterministic angle rule. This
module is only the translation into the contract in docs/api.md. Nothing here looks at an image.

Mapping (side camera, `SideAnglePredictor` result):

  person_count == 0                          -> label AWAY,    confidence 1.0 (nobody detected), no deviation
  prediction_valid == False (anything else)  -> label UNKNOWN, confidence 0.0 (the server ignores it)
  upright                                    -> label GOOD
  leaning_forward / leaning_back             -> label SLOUCHING (the server's `deviation` decides, see below)
  features.torsoAngle  = smoothed sagittal torso inclination, degrees from vertical, + anatomical forward
                         (the model's own convention, and the one the calibration gate uses)
  features.neckAngle   = ear-to-shoulder inclination, degrees from vertical, signed + forward with the
                         camera-facing direction (the model reports it + toward image right)
  deviation            = |torsoAngle - goal torsoAngle| / FULL_SCALE_DEG, clamped to 0..1, where the goal is
                         the user's calibrated torso angle (the predictor's neutral reference)
  confidence           = the lowest visibility/presence score among the landmarks the model measured with

`headForwardOffset` is NOT produced by the model, so it is omitted (the contract allows any subset).
"""
from __future__ import annotations

import math
from typing import Any, Optional, Sequence

SCHEMA = 1

# A deviation of 1.0 is this many degrees away from the goal. The server turns `deviation` into good/bad
# with the user's sensitivity: bad >= 0.6 - 0.4 * sensitivity. At 25 degrees full scale that is 15 deg when
# forgiving, 10 deg when balanced (the model's own default band) and 5 deg when strict. Product parameter.
FULL_SCALE_DEG = 25.0

ALLOWED_KEYS = {"schema", "sessionId", "t", "label", "deviation", "confidence", "features", "source"}
ALLOWED_FEATURES = {"torsoAngle", "neckAngle"}
LABELS = {"GOOD", "SLOUCHING", "AWAY", "UNKNOWN"}


def facing_sign(facing: Optional[str]) -> Optional[float]:
    """+1 when the person's anatomical forward points to image right, -1 to image left, None if unknown."""
    return {"right": 1.0, "left": -1.0}.get(facing or "")


def chain_confidence(landmark_names: Sequence[str], names_in_order: Sequence[str], scores: Sequence[float]) -> float:
    """Lowest score among the named landmarks (the ones the angle was actually measured with)."""
    values = []
    for name in landmark_names:
        if name in names_in_order:
            v = float(scores[list(names_in_order).index(name)])
            values.append(v if math.isfinite(v) else 0.0)
    return min(values) if values else 0.0


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def sample_from_result(result: dict[str, Any], *, session_id: str, t_ms: int, confidence: float, source: str) -> dict[str, Any]:
    """One analyzed frame -> one PostureSample dict. Never raises on a well-formed result."""
    base: dict[str, Any] = {"schema": SCHEMA, "sessionId": session_id, "t": int(t_ms), "source": source}
    quality = result.get("quality") or {}
    if int(quality.get("person_count") or 0) == 0:
        return {**base, "label": "AWAY", "confidence": 1.0, "deviation": None, "features": {}}
    if not result.get("prediction_valid"):
        return {**base, "label": "UNKNOWN", "confidence": 0.0, "deviation": None, "features": {}}

    smoothed = result["smoothed_prediction"]
    angle = float(smoothed["sagittal_angle_deg"])
    neutral = float(result["angle_rule"]["neutral_angle_deg"])
    features: dict[str, float] = {"torsoAngle": round(angle, 1)}
    neck = (result.get("measurements") or {}).get("neck_inclination_deg")
    sign = facing_sign(quality.get("facing"))
    if neck is not None and sign is not None and math.isfinite(neck):
        features["neckAngle"] = round(float(neck) * sign, 1)
    return {**base,
            "label": "GOOD" if smoothed["posture_category"] == "upright" else "SLOUCHING",
            "confidence": round(_clamp01(confidence), 2),
            "deviation": round(_clamp01(abs(angle - neutral) / FULL_SCALE_DEG), 3),
            "features": features}


def validate_outgoing(sample: dict[str, Any]) -> dict[str, Any]:
    """The privacy promise as code: only these numbers and labels may leave the machine, never a frame,
    landmark array or anything else. Raises ValueError (and so refuses to send) on anything unexpected."""
    extra = set(sample) - ALLOWED_KEYS
    if extra:
        raise ValueError(f"refusing to send unexpected field(s): {sorted(extra)}")
    if sample.get("label") not in LABELS:
        raise ValueError("label must be GOOD, SLOUCHING, AWAY or UNKNOWN")
    feats = sample.get("features") or {}
    if set(feats) - ALLOWED_FEATURES:
        raise ValueError(f"refusing to send unexpected feature(s): {sorted(set(feats) - ALLOWED_FEATURES)}")
    numbers = [sample.get("deviation"), sample.get("confidence"), sample.get("t"), *feats.values()]
    for v in numbers:
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)):
            raise ValueError("every value must be a finite number")
    return sample
