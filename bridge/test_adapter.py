import json
import math

import pytest

from api.core.state_machine import BAD, GOOD, NEUTRAL, Config, Sample, classify
from bridge import adapter

SID = "11111111-1111-4111-8111-111111111111"
T = 1_731_672_000_000
SOURCE = "posture-pipeline/side-angle-rule@0.1.0"
NAMES = ["nose", "left_shoulder", "right_shoulder", "left_hip", "right_hip"]


def result(category="upright", angle=3.0, neutral=0.0, valid=True, count=1, facing="right", neck=None):
    """The parts of SideAnglePredictor.analyze() output the adapter reads."""
    return {
        "posture_category": category if valid else None, "prediction_valid": valid, "abstention_reasons": [] if valid else ["x"],
        "smoothed_prediction": {"posture_category": category if valid else None, "sagittal_angle_deg": angle if valid else None},
        "angle_rule": {"neutral_angle_deg": neutral, "lean_threshold_deg": 10.0},
        "measurements": {"sagittal_torso_inclination_deg": angle, "neck_inclination_deg": neck},
        "quality": {"person_count": count, "facing": facing},
    }


def make(res, confidence=0.9):
    return adapter.sample_from_result(res, session_id=SID, t_ms=T, confidence=confidence, source=SOURCE)


def test_upright_is_good_with_a_small_deviation():
    s = make(result("upright", 3.0))
    assert (s["label"], s["deviation"], s["confidence"]) == ("GOOD", 0.12, 0.9)
    assert s["features"] == {"torsoAngle": 3.0}
    assert (s["schema"], s["sessionId"], s["t"], s["source"]) == (1, SID, T, SOURCE)


def test_leaning_forward_and_back_are_both_slouching_with_a_proportional_deviation():
    fwd = make(result("leaning_forward", 15.0))
    back = make(result("leaning_back", -15.0, facing="right"))
    assert fwd["label"] == back["label"] == "SLOUCHING"
    assert fwd["deviation"] == back["deviation"] == 0.6


def test_deviation_is_measured_from_the_users_goal_not_from_vertical():
    # calibrated at 18 deg: sitting at 20 deg is almost on goal
    assert make(result("upright", 20.0, neutral=18.0))["deviation"] == 0.08
    assert make(result("leaning_forward", 30.0, neutral=18.0))["deviation"] == 0.48


def test_deviation_is_clamped_to_one():
    assert make(result("leaning_forward", 80.0))["deviation"] == 1.0


def test_nobody_in_view_is_away_and_the_server_will_act_on_it():
    s = make(result(valid=False, count=0))
    assert (s["label"], s["confidence"], s["deviation"], s["features"]) == ("AWAY", 1.0, None, {})


def test_anything_the_model_cannot_judge_is_unknown_and_ignored_by_the_server():
    for res in (result(valid=False, count=2), result(valid=False, count=1)):
        s = make(res, confidence=0.9)
        assert (s["label"], s["confidence"], s["deviation"], s["features"]) == ("UNKNOWN", 0.0, None, {})


@pytest.mark.parametrize("facing,raw_neck,expected", [("right", 14.0, 14.0), ("left", -14.0, 14.0), ("left", 14.0, -14.0)])
def test_neck_angle_is_signed_forward_using_the_facing_direction(facing, raw_neck, expected):
    s = make(result("upright", 3.0, facing=facing, neck=raw_neck))
    assert s["features"]["neckAngle"] == expected


def test_neck_angle_is_omitted_when_unavailable_or_the_facing_is_unknown():
    assert "neckAngle" not in make(result(neck=None))["features"]
    assert "neckAngle" not in make(result(neck=10.0, facing="unknown"))["features"]
    assert "neckAngle" not in make(result(neck=float("nan")))["features"]


def test_confidence_is_clamped_and_rounded():
    assert make(result(), confidence=1.7)["confidence"] == 1.0
    assert make(result(), confidence=0.876)["confidence"] == 0.88


def test_chain_confidence_is_the_weakest_landmark_actually_used():
    scores = [0.99, 0.9, 0.4, 0.95, 0.8]
    assert adapter.chain_confidence(["left_shoulder", "left_hip"], NAMES, scores) == 0.9
    assert adapter.chain_confidence(["right_shoulder", "right_hip"], NAMES, scores) == 0.4
    assert adapter.chain_confidence([], NAMES, scores) == 0.0
    assert adapter.chain_confidence(["nope"], NAMES, scores) == 0.0
    assert adapter.chain_confidence(["nose"], NAMES, [float("nan")] + scores[1:]) == 0.0


def test_the_deviation_scale_matches_the_servers_sensitivity_bands():
    """At balanced sensitivity a reading just past the model's own +/-10 deg band is BAD and one just inside is not."""
    cfg = Config(sensitivity=0.5)

    def verdict(angle):
        s = make(result("leaning_forward" if angle > 10 else "upright", angle))
        return classify(Sample(t=T, label=s["label"], deviation=s["deviation"], confidence=1.0), cfg)

    assert verdict(10.5) == BAD
    assert verdict(9.0) in (NEUTRAL, GOOD) and verdict(9.0) != BAD
    assert verdict(2.0) == GOOD
    # strict users are nudged for smaller lean, forgiving users for bigger
    assert classify(Sample(t=T, label="SLOUCHING", deviation=6 / 25, confidence=1.0), Config(sensitivity=1.0)) == BAD
    assert classify(Sample(t=T, label="SLOUCHING", deviation=12 / 25, confidence=1.0), Config(sensitivity=0.0)) != BAD


def test_every_sample_is_valid_json_with_only_the_contract_fields():
    for res in (result(), result("leaning_forward", 20.0, neck=5.0), result(valid=False, count=0), result(valid=False)):
        s = make(res)
        json.dumps(s, allow_nan=False)
        assert set(s) <= adapter.ALLOWED_KEYS
        assert adapter.validate_outgoing(s) is s


def test_nothing_but_numbers_and_labels_may_leave_the_machine():
    ok = make(result())
    for mutate in (
        lambda s: s.update(landmarks=[[0.1, 0.2]]),
        lambda s: s.update(frame=b"\x00"),
        lambda s: s["features"].update(rawLandmarks=[1, 2]),
        lambda s: s.update(label="LEANING"),
        lambda s: s.update(deviation=float("nan")),
        lambda s: s["features"].update(torsoAngle=math.inf),
        lambda s: s["features"].update(neckAngle="3"),
        lambda s: s.update(confidence=True),
    ):
        bad = {**ok, "features": dict(ok["features"])}
        mutate(bad)
        with pytest.raises(ValueError):
            adapter.validate_outgoing(bad)
