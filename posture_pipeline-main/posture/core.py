"""Explicitly masked world features and conservative 2D posture geometry.

World coordinates are estimator outputs, not calibrated physical measurements.
All measurements in this module use aspect-corrected IMAGE pixels only.
"""
from __future__ import annotations

from typing import Any

import numpy as np


LANDMARK_NAMES = (
    "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner",
    "right_eye", "right_eye_outer", "left_ear", "right_ear", "mouth_left",
    "mouth_right", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky", "left_index",
    "right_index", "left_thumb", "right_thumb", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle", "left_heel",
    "right_heel", "left_foot_index", "right_foot_index",
)
LABELS = ("upright", "leaning_forward", "leaning_back", "leaning_side")
TORSO_INDICES = (11, 12, 23, 24)
CONFIDENCE_THRESHOLD = 0.5
MIN_SEGMENT_PIXELS = 2.0


def correct_world_camera_roll(world: Any, camera_roll_deg: float = 0.0) -> np.ndarray:
    """Remove a supplied image-convention camera roll from estimated world x/y.

    This is an explicit approximate camera-axis correction, not a pose-derived
    alignment or a world-to-gravity calibration. Positive roll is the observed
    clockwise image rotation, as in ``measure_pose``. The z column is unchanged.
    Call before ``normalize_world``; a zero roll returns an independent copy.
    """
    coordinates = np.asarray(world, dtype=np.float64)
    if coordinates.shape != (33, 3):
        raise ValueError("world must have shape (33, 3)")
    if not np.isfinite(camera_roll_deg):
        raise ValueError("camera_roll_deg must be finite")
    corrected = coordinates.copy()
    if camera_roll_deg == 0:
        return corrected
    roll = np.radians(camera_roll_deg)
    inverse_rotation = np.array([[np.cos(roll), np.sin(roll)],
                                 [-np.sin(roll), np.cos(roll)]])
    corrected[:, :2] = coordinates[:, :2] @ inverse_rotation.T
    return corrected


def _scores(confidence: Any) -> tuple[np.ndarray, np.ndarray]:
    """Accept combined scores, or visibility/presence columns in either order."""
    if confidence is None:
        return np.zeros(33, dtype=np.float32), np.zeros(33, dtype=np.float32)
    raw = np.asarray(confidence, dtype=np.float64)
    if raw.shape not in ((33,), (33, 2)):
        raise ValueError("confidence must have shape (33,) or (33, 2)")
    if np.any(np.isfinite(raw) & ((raw < 0) | (raw > 1))):
        raise ValueError("finite confidence values must be between zero and one")
    if raw.ndim == 2:
        known = np.all(np.isfinite(raw), axis=1)
        values = np.min(np.where(np.isfinite(raw), raw, 0), axis=1)
    else:
        known = np.isfinite(raw)
        values = np.where(known, raw, 0)
    return values.astype(np.float32), known.astype(np.float32)


def normalize_world(world: Any, confidence: Any = None, threshold: float = 0.5) -> dict:
    """Hip-center and torso-scale 33 estimator world landmarks without rotation.

    A mask of one with confidence_known=0 means coordinates exist; it does not
    assert visibility. Unknown confidence is represented by zero plus its mask.
    Missing/low-confidence coordinates become zero, and retain mask=0.
    """
    coordinates = np.asarray(world, dtype=np.float64)
    if coordinates.shape != (33, 3):
        raise ValueError("world must have shape (33, 3)")
    if not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold must be finite and between zero and one")
    scores, known = _scores(confidence)
    available = np.all(np.isfinite(coordinates), axis=1)
    available &= (known == 0) | (scores >= threshold)
    result = {
        "xyz": np.zeros((33, 3), dtype=np.float32),
        "confidence": scores,
        "mask": available.astype(np.float32),
        "confidence_known": known,
        "valid": False,
        "reason": None,
    }
    if not (available[23] and available[24]):
        result["reason"] = "missing_or_low_confidence_hip_reference"
        return result
    scale_candidates = [
        float(np.linalg.norm(coordinates[s] - coordinates[h]))
        for s, h in ((11, 23), (12, 24))
        if available[s] and available[h]
        and np.linalg.norm(coordinates[s] - coordinates[h]) > 1e-6
    ]
    if not scale_candidates:
        result["reason"] = "missing_or_degenerate_torso_scale"
        return result
    scale = float(np.median(scale_candidates))
    center = (coordinates[23] + coordinates[24]) / 2.0
    normalized = (coordinates[available] - center) / scale
    if not np.all(np.isfinite(normalized)) or np.max(np.abs(normalized), initial=0) > np.finfo(np.float32).max:
        result["reason"] = "nonfinite_normalized_coordinates"
        return result
    result["xyz"][available] = normalized.astype(np.float32)
    result["valid"] = True
    return result


def _inclination(vector: np.ndarray) -> float | None:
    if float(np.linalg.norm(vector)) < MIN_SEGMENT_PIXELS:
        return None
    return float(np.degrees(np.arctan2(vector[0], -vector[1])))


def _bend(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float | None:
    first, second = a - b, c - b
    lengths = np.linalg.norm(first), np.linalg.norm(second)
    if min(lengths) < MIN_SEGMENT_PIXELS:
        return None
    cosine = float(np.clip(np.dot(first, second) / (lengths[0] * lengths[1]), -1, 1))
    return float(180.0 - np.degrees(np.arccos(cosine)))


def _infer_facing(points: np.ndarray, usable: np.ndarray, scores: np.ndarray,
                  torso_length: float) -> tuple[str, str]:
    """Require agreement of the face and BOTH feet; a single cue never suffices."""
    strong = usable & (scores >= 0.8)
    ears = [index for index in (7, 8) if strong[index]]
    if not strong[0] or not ears or not all(strong[i] for i in (29, 30, 31, 32)):
        return "unknown", "insufficient_high_confidence_face_and_both_feet"
    threshold = max(3.0, 0.06 * torso_length)
    cues = [
        float(points[0, 0] - np.mean(points[ears, 0])),
        float(points[31, 0] - points[29, 0]),
        float(points[32, 0] - points[30, 0]),
    ]
    if any(abs(cue) < threshold for cue in cues):
        return "unknown", "facing_cue_projected_separation_too_small"
    signs = np.sign(cues)
    if not np.all(signs == signs[0]):
        return "unknown", "face_and_feet_disagree"
    return ("right" if signs[0] > 0 else "left"), "face_and_both_feet_consensus"


def measure_pose(image_xy: Any, confidence: Any, width: int, height: int,
                 viewpoint: str = "unknown", facing: str = "unknown",
                 camera_roll_deg: float = 0.0) -> dict:
    """Measure projected angles with per-value validity and abstention reasons.

    `image_xy` is normalized x/width, y/height in MediaPipe order. Roll is the
    observed clockwise rotation of an upright scene in image coordinates and
    is undone explicitly; it is never inferred from the person's torso.
    `viewpoint` is supplied camera context, not inferred here. Allowed values
    are front, side, oblique, back, unknown. `facing` is left, right, or unknown
    in the corrected image. Scores may be min(visibility, presence) or Nx2.
    """
    coordinates = np.asarray(image_xy, dtype=np.float64)
    if coordinates.shape != (33, 2):
        raise ValueError("image_xy must have shape (33, 2)")
    if not np.isfinite(width) or not np.isfinite(height) or width <= 0 or height <= 0:
        raise ValueError("width and height must be positive finite pixel dimensions")
    if not np.isfinite(camera_roll_deg):
        raise ValueError("camera_roll_deg must be finite")
    if viewpoint not in {"front", "side", "oblique", "back", "unknown"}:
        raise ValueError("viewpoint must be front, side, oblique, back, or unknown")
    if facing not in {"left", "right", "unknown"}:
        raise ValueError("facing must be left, right, or unknown")
    scores, known = _scores(confidence)
    finite = np.all(np.isfinite(coordinates), axis=1)
    # Extrapolated off-image joints are unsuitable for measurement even when
    # the model reports confidence. This does not change world feature masks.
    in_frame = finite & np.all((coordinates >= 0) & (coordinates <= 1), axis=1)
    usable = in_frame & (known == 1) & (scores >= CONFIDENCE_THRESHOLD)
    pixels = coordinates * np.array([width, height], dtype=np.float64)
    roll = np.radians(camera_roll_deg)
    # Column-vector inverse rotation, applied to row-vector points.
    correction = np.array([[np.cos(roll), np.sin(roll)], [-np.sin(roll), np.cos(roll)]])
    points = (pixels - np.array([width / 2, height / 2])) @ correction.T
    values: dict[str, float | None] = {}
    details: dict[str, dict] = {}
    warnings: list[str] = []
    torso_scores = np.where(finite & (known == 1), scores, 0)[list(TORSO_INDICES)]

    def record(name: str, value: float | None, *, landmarks: list[int] | None = None,
               reason: str | None = None, sign: str = "positive_toward_image_right",
               proxy: str, reference: str = "roll_corrected_image_vertical",
               side: str | None = None) -> None:
        if value is None and reason is None:
            reason = "degenerate_or_too_short_projected_segment"
        values[name] = None if value is None else float(value)
        details[name] = {
            "valid": value is not None,
            "reason": reason,
            "units": "degrees",
            "space": "2d_image_projection",
            "landmarks": [LANDMARK_NAMES[i] for i in (landmarks or [])],
            "sign_convention": sign,
            "reference_axis": reference,
            "proxy": proxy,
            "selected_body_side": side,
        }

    def unavailable_reason(indices: tuple[int, ...] | list[int]) -> str:
        if any(not finite[i] for i in indices):
            return "missing_or_nonfinite_landmark"
        if any(not in_frame[i] for i in indices):
            return "landmark_outside_image"
        if any(known[i] == 0 for i in indices):
            return "unknown_landmark_confidence"
        return "low_landmark_confidence"

    def select_side(candidates: tuple[tuple[int, ...], tuple[int, ...]]) -> tuple[list[int] | None, str | None]:
        options = [(float(min(scores[list(indices)])), position, list(indices))
                   for position, indices in enumerate(candidates)
                   if all(usable[i] for i in indices)]
        if not options:
            return None, None
        # Stable tie-break favors left; choose the most visible complete chain.
        _, position, indices = max(options, key=lambda item: (item[0], -item[1]))
        return indices, ("left" if position == 0 else "right")

    torso_indices: list[int] = list(TORSO_INDICES)
    torso_side = None
    torso_vector = None
    if all(usable[i] for i in TORSO_INDICES):
        torso_vector = np.mean(points[[11, 12]], axis=0) - np.mean(points[[23, 24]], axis=0)
    elif viewpoint == "side":
        selected, torso_side = select_side(((11, 23), (12, 24)))
        if selected:
            torso_indices = selected
            torso_vector = points[selected[0]] - points[selected[1]]
    torso = _inclination(torso_vector) if torso_vector is not None else None
    torso_reason = unavailable_reason(TORSO_INDICES) if torso_vector is None else None
    record("torso_inclination_deg", torso, landmarks=torso_indices, reason=torso_reason,
           proxy="hip_midpoint_to_shoulder_midpoint" if torso_side is None else "ipsilateral_hip_to_shoulder",
           side=torso_side)

    actual_facing = facing
    facing_source = "supplied" if facing != "unknown" else "unknown"
    facing_reason = None
    if facing == "unknown" and viewpoint == "side":
        if torso_vector is not None and torso is not None:
            actual_facing, facing_reason = _infer_facing(points, usable, scores, float(np.linalg.norm(torso_vector)))
            if actual_facing != "unknown":
                facing_source = "face_and_feet_consensus"
        else:
            facing_reason = "torso_reference_unavailable"
    if viewpoint != "side":
        sagittal, sagittal_reason = None, "requires_side_view"
    elif actual_facing == "unknown":
        sagittal, sagittal_reason = None, "anatomical_facing_unknown"
    else:
        sagittal = None if torso is None else torso * (1 if actual_facing == "right" else -1)
        sagittal_reason = details["torso_inclination_deg"]["reason"]
    record("sagittal_torso_inclination_deg", sagittal, landmarks=torso_indices,
           reason=sagittal_reason, sign="positive_anatomical_forward_negative_backward",
           proxy=details["torso_inclination_deg"]["proxy"], side=torso_side)

    neck_indices: list[int] = [7, 8, 11, 12]
    neck_side, neck_vector, neck_reason = None, None, None
    if viewpoint == "front":
        if all(usable[i] for i in neck_indices):
            neck_vector = np.mean(points[[7, 8]], axis=0) - np.mean(points[[11, 12]], axis=0)
        else:
            neck_reason = unavailable_reason(neck_indices)
    elif viewpoint == "side":
        selected, neck_side = select_side(((11, 7), (12, 8)))
        if selected:
            neck_indices = selected
            neck_vector = points[selected[1]] - points[selected[0]]
        else:
            neck_reason = unavailable_reason(neck_indices)
    else:
        neck_reason = "requires_front_or_side_view"
    record("neck_inclination_deg", _inclination(neck_vector) if neck_vector is not None else None,
           landmarks=neck_indices, reason=neck_reason,
           proxy="shoulder_midpoint_to_ear_midpoint" if viewpoint == "front" else "ipsilateral_shoulder_to_ear",
           side=neck_side)

    for name, candidates in (
        ("hip_flexion_deg", ((11, 23, 25), (12, 24, 26))),
        ("knee_flexion_deg", ((23, 25, 27), (24, 26, 28))),
    ):
        selected, side = select_side(candidates)
        if viewpoint != "side":
            value, reason = None, "requires_side_view"
        elif selected is None:
            value, reason = None, unavailable_reason(list(candidates[0] + candidates[1]))
        else:
            value, reason = _bend(*points[selected]), None
        record(name, value, landmarks=selected, reason=reason,
               sign="unsigned_0_straight_to_180_folded",
               proxy="180_minus_projected_included_joint_angle", reference="adjacent_projected_limb_segments", side=side)

    for name, indices in (("shoulder_alignment_deg", [11, 12]), ("hip_alignment_deg", [23, 24])):
        if viewpoint != "front":
            value, reason = None, "requires_front_view"
        elif not all(usable[i] for i in indices):
            value, reason = None, unavailable_reason(indices)
        else:
            ordered = sorted(indices, key=lambda i: points[i, 0])
            vector = points[ordered[1]] - points[ordered[0]]
            if abs(vector[0]) < MIN_SEGMENT_PIXELS:
                value, reason = None, "insufficient_horizontal_landmark_separation"
            else:
                value, reason = float(np.degrees(np.arctan2(-vector[1], vector[0]))), None
        record(name, value, landmarks=indices, reason=reason,
               sign="positive_if_image_right_endpoint_is_higher", reference="roll_corrected_image_horizontal",
               proxy="bilateral_landmark_line_slope")

    if viewpoint != "front":
        lateral, lateral_reason = None, "requires_front_view_bilateral_torso_landmarks"
    elif not all(usable[i] for i in TORSO_INDICES):
        lateral, lateral_reason = None, unavailable_reason(TORSO_INDICES)
    else:
        lateral, lateral_reason = torso, details["torso_inclination_deg"]["reason"]
    record("lateral_trunk_inclination_deg", lateral, landmarks=list(TORSO_INDICES),
           reason=lateral_reason, proxy="hip_midpoint_to_shoulder_midpoint_frontal_projection")

    if camera_roll_deg == 0:
        warnings.append("Camera roll is assumed zero; use an external vertical reference to calibrate it.")
    if viewpoint != "front":
        warnings.append("Lateral trunk inclination is not reliably observable from this view.")
    if viewpoint == "side" and actual_facing == "unknown":
        warnings.append("Anatomical facing is unknown; signed forward/backward inclination is unavailable.")
    if not all(usable[i] for i in TORSO_INDICES):
        warnings.append("Some torso landmarks are missing, outside the image, or below the confidence threshold.")
    if not np.any(known):
        warnings.append("Landmark confidence is unavailable; image measurements abstain.")
    quality = {
        "pose_confidence": float(np.mean(torso_scores)),
        "pose_confidence_definition": "mean_min_visibility_presence_over_shoulders_and_hips_missing_equals_zero",
        "viewpoint": viewpoint,
        "viewpoint_source": "supplied_camera_context",
        "facing": actual_facing,
        "facing_source": facing_source,
        "facing_reason": facing_reason,
        "camera_roll_deg": float(camera_roll_deg),
        "camera_roll_source": "upright_camera_assumption" if camera_roll_deg == 0 else "supplied_calibration",
        "usable_landmark_count": int(np.sum(usable)),
        "landmark_confidence_threshold": CONFIDENCE_THRESHOLD,
        "warnings": warnings,
    }
    return {"measurements": values, "measurement_details": details, "quality": quality}
