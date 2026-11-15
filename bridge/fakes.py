"""Test doubles for the bridge: a fake camera, pose extractor, angle predictor and API (no MediaPipe, no network)."""
import json


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeCapture:
    def __init__(self, frames):
        self.frames, self.i, self.rewinds = frames, 0, 0

    def read(self):
        if self.i >= len(self.frames):
            return False, None
        self.i += 1
        return True, self.frames[self.i - 1]

    def rewind(self):
        self.i = 0
        self.rewinds += 1


class FakeExtractor:
    def extract(self, frame):
        # `frame` is just a marker here; a real frame would be pixels and must never be forwarded
        return {"image_xy": None, "confidence": [0.9, 0.9, 0.5, 0.9, 0.5], "person_count": frame["people"], "angle": frame["angle"]}


class FakePredictor:
    """Mimics SideAnglePredictor: upright within 10 degrees of the neutral reference."""

    def __init__(self):
        self.neutral = 0.0
        self.calls = []

    def set_neutral(self, a):
        self.neutral = a

    def analyze(self, pose, viewpoint, facing, roll):
        self.calls.append((viewpoint, facing, roll))
        a, n = pose["angle"], self.neutral
        known = facing in ("left", "right")
        valid = pose["person_count"] == 1 and known
        reasons = []
        if pose["person_count"] != 1:
            reasons.append("Exactly one visible person is required.")
        elif not known:
            reasons.append("Sagittal angle unavailable: anatomical_facing_unknown")
        cat = "upright" if abs(a - n) <= 10 else ("leaning_forward" if a > n else "leaning_back")
        return {"prediction_valid": valid, "abstention_reasons": reasons,
                "smoothed_prediction": {"posture_category": cat if valid else None, "sagittal_angle_deg": a if valid else None},
                "angle_rule": {"neutral_angle_deg": n}, "measurements": {"neck_inclination_deg": 5.0},
                "measurement_details": {"sagittal_torso_inclination_deg": {"landmarks": ["left_shoulder", "left_hip"]}},
                "quality": {"person_count": pose["person_count"], "facing": facing}}


class FakeApi:
    def __init__(self, goal=None, fail=None):
        self.sent, self.goal, self.fail = [], goal, fail

    def ingest(self, sample):
        if self.fail:
            raise self.fail
        json.dumps(sample, allow_nan=False)
        self.sent.append(sample)
        return {"state": "GOOD", "alert": None}

    def goal_torso_angle(self):
        return self.goal


NAMES = ["nose", "left_shoulder", "right_shoulder", "left_hip", "right_hip"]


def frame(angle=3.0, people=1):
    return {"angle": angle, "people": people}
