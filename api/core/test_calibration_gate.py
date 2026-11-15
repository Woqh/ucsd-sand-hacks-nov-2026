import pytest

from api.core.calibration_gate import (ALLOWED_RANGE_DEG, MAX_BACKWARD_LEAN_DEG, MAX_FORWARD_LEAN_DEG,
                                       back_angle_issues)


def goal(angle):
    return {"neckAngle": 15.0, "torsoAngle": angle, "headForwardOffset": 0.18}


@pytest.mark.parametrize("angle", [0, 5.0, 5.5, -5, -9.9, MAX_FORWARD_LEAN_DEG, -MAX_BACKWARD_LEAN_DEG])
def test_good_back_angles_pass(angle):
    # upright, the documented example goal (5 degrees), a slight lean back, and the exact limits
    assert back_angle_issues(goal(angle)) == []


@pytest.mark.parametrize("angle", [10.1, 18.0, 35, 80])
def test_leaning_too_far_forward_is_refused_with_a_reason(angle):
    issues = back_angle_issues(goal(angle))
    assert len(issues) == 1 and "leaning forward" in issues[0] and f"within {MAX_FORWARD_LEAN_DEG:.0f}° of upright" in issues[0]


@pytest.mark.parametrize("angle", [-10.1, -15, -25, -40, -90])
def test_leaning_too_far_back_is_refused_too(angle):
    issues = back_angle_issues(goal(angle))
    assert len(issues) == 1 and "leaning back" in issues[0] and f"within {MAX_BACKWARD_LEAN_DEG:.0f}° of upright" in issues[0]


def test_allowed_range_is_two_sided_and_brackets_upright():
    lo, hi = ALLOWED_RANGE_DEG
    assert lo < 0 < hi                                   # a limit on BOTH sides of upright
    assert back_angle_issues(goal(0)) == []              # upright itself is always fine
    assert back_angle_issues(goal(hi + 0.01)) and back_angle_issues(goal(lo - 0.01))


def test_stub_values_land_on_the_right_sides():
    # the model stub's "good" (5) and "slouched" (18) postures must be separated by the gate
    assert back_angle_issues(goal(5.0)) == []
    assert back_angle_issues(goal(18.0)) != []


def test_missing_or_non_finite_angle_is_refused_not_accepted():
    assert "No spine/back angle" in back_angle_issues({"neckAngle": 15.0})[0]
    # NaN fails every comparison, so without an explicit check it would sail through as "good"
    for bad in (float("nan"), float("inf"), float("-inf")):
        assert "invalid" in back_angle_issues(goal(bad))[0]
