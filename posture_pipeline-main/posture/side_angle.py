"""Three sagittal categories from projected angles, not a trained classifier."""
from collections import deque
import time
import numpy as np
from .core import measure_pose


class SideAnglePredictor:
    def __init__(self, lean_threshold_deg=10.0, neutral_angle_deg=0.0,
                 smoothing_window=1, smoothing_max_age_s=0.5):
        if not np.isfinite(lean_threshold_deg) or not 0 < lean_threshold_deg < 90:
            raise ValueError("Lean threshold must be finite and between 0 and 90 degrees.")
        if not np.isfinite(neutral_angle_deg) or abs(neutral_angle_deg) >= 90:
            raise ValueError("Neutral angle must be finite and between -90 and 90 degrees.")
        if not 1 <= smoothing_window <= 60 or not np.isfinite(smoothing_max_age_s) or smoothing_max_age_s <= 0:
            raise ValueError("Invalid smoothing window or maximum age.")
        self.threshold = float(lean_threshold_deg)
        self.neutral = float(neutral_angle_deg)
        self.window = smoothing_window
        self.max_age = smoothing_max_age_s
        self.history = deque(maxlen=smoothing_window)
        self.context = None

    def set_neutral(self, angle):
        if not np.isfinite(angle) or abs(angle) >= 90:
            raise ValueError("Neutral reference must be between -90 and 90 degrees.")
        self.neutral = float(angle)
        self.history.clear()

    def category(self, angle):
        delta = angle - self.neutral
        if delta > self.threshold:
            return "leaning_forward"
        if delta < -self.threshold:
            return "leaning_back"
        return "upright"

    def analyze(self, pose, viewpoint="side", facing="unknown", camera_roll_deg=0.0, timestamp=None):
        started = time.perf_counter()
        timestamp = time.monotonic() if timestamp is None else float(timestamp)
        geometry = measure_pose(pose["image_xy"], pose["confidence"], pose["width"], pose["height"],
                                viewpoint, facing, camera_roll_deg)
        angle = geometry["measurements"]["sagittal_torso_inclination_deg"]
        detail = geometry["measurement_details"]["sagittal_torso_inclination_deg"]
        reasons = []
        if pose.get("person_count", 0) != 1:
            reasons.append("Exactly one visible person is required.")
        if viewpoint != "side":
            reasons.append("Side-angle mode requires an actual side camera view.")
        if angle is None:
            reasons.append("Sagittal angle unavailable: " + str(detail["reason"]))
        elif abs(angle) >= 90:
            reasons.append("Torso is horizontal or inverted; outside the upright seated operating range.")
        valid = not reasons
        quality = geometry["quality"]
        context = (quality["facing"], camera_roll_deg, viewpoint, detail["selected_body_side"])
        if context != self.context or (self.history and timestamp <= self.history[-1][0]):
            self.history.clear()
        self.context = context
        while self.history and timestamp - self.history[0][0] > self.max_age:
            self.history.popleft()
        smooth = None
        delay = 0.0
        if valid:
            self.history.append((timestamp, angle))
            smooth = float(np.mean([a for _, a in self.history]))
            delay = (timestamp - self.history[0][0]) * 500
        else:
            self.history.clear()
        quality.update({"person_count": int(pose.get("person_count", 0)),
                        "probability_calibration": "Not applicable: deterministic angle rule, no probabilities",
                        "lateral_lean_observable": False,
                        "warnings": ["Sideways lean: UNOBSERVABLE; upright describes only the visible sagittal projection.",
                                     "Angle thresholds are configurable heuristics, not validated health criteria.",
                                     *reasons, *quality["warnings"]]})
        raw = self.category(angle) if valid else None
        category = self.category(smooth) if valid else None
        return {"posture_category": category, "class_probabilities": None,
                "prediction_valid": valid, "abstention_reasons": reasons,
                "classification_method": "side_angle_rule", "classification_scope": "sagittal_only",
                "lateral_posture": "unobservable",
                "raw_prediction": {"posture_category": raw, "class_probabilities": None,
                                   "prediction_valid": valid, "sagittal_angle_deg": angle},
                "smoothed_prediction": {"posture_category": category, "class_probabilities": None,
                                        "prediction_valid": valid, "sagittal_angle_deg": smooth,
                                        "window_frames": self.window, "history_frames": len(self.history),
                                        "maximum_history_age_ms": self.max_age * 1000, "estimated_delay_ms": delay},
                "angle_rule": {"neutral_angle_deg": self.neutral, "lean_threshold_deg": self.threshold,
                               "deviation_from_neutral_deg": smooth - self.neutral if valid else None,
                               "upright_definition": "absolute deviation <= threshold; no lateral assessment"},
                "measurements": geometry["measurements"], "measurement_details": geometry["measurement_details"],
                "quality": quality, "timestamp_monotonic_s": timestamp,
                "latency_ms": {"pose": float(pose.get("pose_latency_ms", 0)),
                               "geometry_classifier_smoothing": (time.perf_counter() - started) * 1000}}
