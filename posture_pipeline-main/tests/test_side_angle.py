import json
import numpy as np
import pytest
from posture.side_angle import SideAnglePredictor


def side_pose(angle):
    # Only the near shoulder/hip are visible. No world estimate is needed.
    xy = np.full((33, 2), np.nan)
    conf = np.zeros(33)
    r = np.radians(angle)
    xy[23] = (320 / 640, 320 / 480)
    xy[11] = ((320 + 100 * np.sin(r)) / 640, (320 - 100 * np.cos(r)) / 480)
    conf[[11, 23]] = 0.95
    return dict(image_xy=xy, confidence=conf, width=640, height=480, person_count=1)


@pytest.mark.parametrize('angle,category', [(0,'upright'),(9.9,'upright'),(10.1,'leaning_forward'),(-10.1,'leaning_back')])
def test_three_categories_with_visible_side_only(angle, category):
    result = SideAnglePredictor().analyze(side_pose(angle), facing='right')
    assert result['prediction_valid'] and result['posture_category'] == category
    assert result['class_probabilities'] is None
    assert result['lateral_posture'] == 'unobservable'
    assert result['measurements']['lateral_trunk_inclination_deg'] is None
    json.dumps(result, allow_nan=False)


def test_left_facing_reverses_anatomical_sign():
    result = SideAnglePredictor().analyze(side_pose(20), facing='left')
    assert result['posture_category'] == 'leaning_back'
    assert result['measurements']['sagittal_torso_inclination_deg'] == pytest.approx(-20)


@pytest.mark.parametrize('failure',['no_person','multiple','occluded','cropped','unknown_facing','wrong_view'])
def test_abstention(failure):
    pose = side_pose(20)
    kwargs = dict(facing='right', viewpoint='side')
    if failure == 'no_person': pose['person_count'] = 0
    if failure == 'multiple': pose['person_count'] = 2
    if failure == 'occluded': pose['confidence'][23] = 0.1
    if failure == 'cropped': pose['image_xy'][23,0] = 1.1
    if failure == 'unknown_facing': kwargs['facing'] = 'unknown'
    if failure == 'wrong_view': kwargs['viewpoint'] = 'front'
    result = SideAnglePredictor().analyze(pose, **kwargs)
    assert not result['prediction_valid'] and result['posture_category'] is None
    assert result['abstention_reasons']


def test_reference_and_smoothing_keep_physical_measurements():
    predictor = SideAnglePredictor(smoothing_window=3)
    predictor.analyze(side_pose(20), facing='right', timestamp=1)
    predictor.set_neutral(20)
    assert not predictor.history
    result = predictor.analyze(side_pose(20), facing='right', timestamp=1.1)
    assert result['posture_category'] == 'upright'
    assert result['measurements']['sagittal_torso_inclination_deg'] == pytest.approx(20)
    result = predictor.analyze(side_pose(40), facing='right', timestamp=2)
    assert result['smoothed_prediction']['history_frames'] == 1
    assert result['posture_category'] == 'leaning_forward'
    predictor.set_neutral(0)
    assert predictor.category(10) == 'upright'
    assert predictor.category(-10) == 'upright'


def test_smoothing_resets_on_bad_frame_and_direction_change():
    predictor = SideAnglePredictor(smoothing_window=3)
    predictor.analyze(side_pose(20), facing='right', timestamp=1)
    result = predictor.analyze(side_pose(20), facing='left', timestamp=1.1)
    assert result['smoothed_prediction']['history_frames'] == 1
    assert result['posture_category'] == 'leaning_back'
    bad = side_pose(0)
    bad['person_count'] = 0
    predictor.analyze(bad, facing='left', timestamp=1.2)
    result = predictor.analyze(side_pose(0), facing='left', timestamp=1.3)
    assert result['smoothed_prediction']['history_frames'] == 1


def test_invalid_config():
    for kwargs in ({'lean_threshold_deg':0},{'neutral_angle_deg':float('nan')},{'smoothing_window':0}):
        with pytest.raises(ValueError): SideAnglePredictor(**kwargs)
