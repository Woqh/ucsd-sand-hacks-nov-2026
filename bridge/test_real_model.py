"""The adapter against the teammate's REAL SideAnglePredictor output (not hand-built dicts).

Needs numpy and the pipeline's pure-Python modules, so it is skipped in the API's Python and runs in the model's
environment:   posture_pipeline-main\\.venv\\Scripts\\python.exe -m pytest bridge/test_real_model.py
"""
import json
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "posture_pipeline-main"))
from posture.core import LANDMARK_NAMES  # noqa: E402
from posture.side_angle import SideAnglePredictor  # noqa: E402

from bridge import adapter  # noqa: E402

SID = "11111111-1111-4111-8111-111111111111"


def pose(torso_deg, neck_deg=None, count=1):
    """A side view: near hip at the image centre, near shoulder `torso_deg` clockwise of vertical (image right +),
    optionally the near ear `neck_deg` clockwise of vertical above the shoulder. Nothing else is visible."""
    xy = np.full((33, 2), np.nan)
    conf = np.zeros(33)
    t = np.radians(torso_deg)
    xy[23] = (0.5, 0.7)
    xy[11] = (0.5 + 0.2 * np.sin(t) * 480 / 640, 0.7 - 0.2 * np.cos(t))
    conf[[11, 23]] = 0.95
    if neck_deg is not None:
        n = np.radians(neck_deg)
        xy[7] = (xy[11][0] + 0.1 * np.sin(n) * 480 / 640, xy[11][1] - 0.1 * np.cos(n))
        conf[7] = 0.9
    return dict(image_xy=xy, confidence=conf, width=640, height=480, person_count=count)


def sample(predictor, p, facing="right", t=1.0):
    result = predictor.analyze(p, "side", facing, 0.0, timestamp=t)
    details = result["measurement_details"]["sagittal_torso_inclination_deg"]
    conf = adapter.chain_confidence(details.get("landmarks") or [], LANDMARK_NAMES, p["confidence"])
    return adapter.sample_from_result(result, session_id=SID, t_ms=1_731_672_000_000, confidence=conf, source="test")


def test_upright_leaning_forward_and_leaning_back_facing_right():
    p = SideAnglePredictor()
    up, fwd, back = sample(p, pose(2.0), t=1), sample(p, pose(22.0), t=5), sample(p, pose(-22.0), t=9)
    assert (up["label"], fwd["label"], back["label"]) == ("GOOD", "SLOUCHING", "SLOUCHING")
    assert up["features"]["torsoAngle"] == pytest.approx(2.0, abs=0.1)
    assert fwd["features"]["torsoAngle"] == pytest.approx(22.0, abs=0.1) and back["features"]["torsoAngle"] == pytest.approx(-22.0, abs=0.1)
    assert fwd["deviation"] == pytest.approx(0.88, abs=0.01)
    assert up["confidence"] == 0.95


def test_facing_left_flips_the_sign_so_forward_is_always_positive():
    # leaning toward image LEFT while facing left is leaning forward
    s = sample(SideAnglePredictor(), pose(-22.0), facing="left")
    assert s["label"] == "SLOUCHING" and s["features"]["torsoAngle"] == pytest.approx(22.0, abs=0.1)


def test_the_goal_posture_is_the_reference_for_label_and_deviation():
    p = SideAnglePredictor()
    p.set_neutral(18.0)                                    # the user's calibrated torso angle
    s = sample(p, pose(20.0))
    assert s["label"] == "GOOD" and s["deviation"] == pytest.approx(0.08, abs=0.01)


def test_neck_angle_is_signed_forward_and_goes_up_when_the_head_juts_forward():
    p = SideAnglePredictor()
    neutral, jutting = sample(p, pose(2.0, neck_deg=5.0), t=1), sample(p, pose(2.0, neck_deg=30.0), t=5)
    assert neutral["features"]["neckAngle"] == pytest.approx(5.0, abs=0.2)
    assert jutting["features"]["neckAngle"] == pytest.approx(30.0, abs=0.2)
    left = sample(SideAnglePredictor(), pose(-2.0, neck_deg=-30.0), facing="left")
    assert left["features"]["neckAngle"] == pytest.approx(30.0, abs=0.2)


@pytest.mark.parametrize("make,label", [
    (lambda: pose(2.0, count=0), "AWAY"),
    (lambda: pose(2.0, count=2), "UNKNOWN"),
    (lambda: {**pose(2.0), "confidence": np.full(33, 0.1)}, "UNKNOWN"),
])
def test_abstentions_map_to_away_or_unknown(make, label):
    s = sample(SideAnglePredictor(), make())
    assert s["label"] == label and s["features"] == {}
    assert s["confidence"] == (1.0 if label == "AWAY" else 0.0)


def test_unknown_facing_abstains_instead_of_guessing_the_sign():
    s = sample(SideAnglePredictor(), pose(22.0), facing="unknown")
    assert s["label"] == "UNKNOWN"


def test_a_real_result_serialises_and_passes_the_privacy_check():
    s = sample(SideAnglePredictor(), pose(12.0, neck_deg=10.0))
    json.dumps(s, allow_nan=False)
    adapter.validate_outgoing(s)
