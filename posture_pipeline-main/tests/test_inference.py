import json
from pathlib import Path

import numpy as np
import pytest
import torch

from posture.core import LABELS
from posture.inference import Predictor, ProbabilitySmoother
from posture.learning import PostureCNN


@pytest.fixture
def predictor(tmp_path):
    model = PostureCNN()
    # Deterministic high upright score exercises quality gates independently of accuracy.
    for parameter in model.parameters():
        parameter.data.zero_()
    model.classifier[-1].bias.data[0] = 8
    path = tmp_path / "model.pt"
    torch.save({"state_dict": model.state_dict(), "temperature": 1.0, "labels": list(LABELS),
                "config": {"dropout": 0.2, "num_threads": 1}, "architecture": "shared_chain_conv1d_v1",
                "supported_viewpoints": ["front"], "confidence_available": False,
                "preprocessing_version": "world_v1"}, path)
    return Predictor(path, smoothing_window=3)


def pose():
    xy = np.full((33, 2), 0.5, dtype=np.float32)
    xy[11], xy[12], xy[23], xy[24] = (0.4, 0.3), (0.6, 0.3), (0.4, 0.6), (0.6, 0.6)
    world = np.column_stack((xy - (0.5, 0.6), np.zeros(33))).astype(np.float32)
    return {"image_xy": xy, "world": world, "confidence": np.ones(33),
            "width": 640, "height": 480, "person_count": 1, "pose_latency_ms": 0}


def test_supported_front_and_forced_side_abstention(predictor):
    valid = predictor.analyze(pose(), viewpoint="front", timestamp=1)
    assert valid["prediction_valid"] and valid["posture_category"] == "upright"
    result = predictor.analyze(pose(), viewpoint="side", facing="right", timestamp=2)
    assert not result["prediction_valid"] and result["posture_category"] is None
    assert result["raw_prediction"]["posture_category"] == "upright"
    assert result["measurements"]["lateral_trunk_inclination_deg"] is None
    assert any("unsupported" in r for r in result["abstention_reasons"])
    assert result["smoothed_prediction"]["history_frames"] == 0
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("failure", ["missing", "multiple", "occluded", "cropped", "nonfinite"])
def test_quality_abstention(predictor, failure):
    item = pose()
    if failure == "missing":
        item["person_count"] = 0
        item["world"][:] = np.nan
        item["image_xy"][:] = np.nan
        item["confidence"][:] = 0
    elif failure == "multiple":
        item["person_count"] = 2
    elif failure == "occluded":
        item["confidence"][23] = 0.1
    elif failure == "cropped":
        item["image_xy"][23] = (1.5, 0.6)
    else:
        item["image_xy"][23] = np.nan
    result = predictor.analyze(item, viewpoint="front")
    assert not result["prediction_valid"]
    assert result["posture_category"] is None
    json.dumps(result, allow_nan=False)


def test_smoothing_cannot_reuse_before_gap_or_invalid_frame(predictor):
    smoother = ProbabilitySmoother(3, max_age_s=0.5)
    smoother.update([1, 0, 0, 0], 0)
    smoother.update([1, 0, 0, 0], 0.03)
    output, delay = smoother.update([0, 1, 0, 0], 10)
    np.testing.assert_array_equal(output, [0, 1, 0, 0])
    assert delay == 0 and len(smoother.history) == 1
    predictor.analyze(pose(), viewpoint="front", timestamp=1)
    missing = pose()
    missing["person_count"] = 0
    predictor.analyze(missing, viewpoint="front", timestamp=1.1)
    result = predictor.analyze(pose(), viewpoint="front", timestamp=1.2)
    assert result["smoothed_prediction"]["history_frames"] == 1


def test_confidence_channels_remain_unknown_for_csv_checkpoint(predictor):
    captured = []
    hook = predictor.model.register_forward_pre_hook(lambda model, args: captured.append(args[0].clone()))
    predictor.analyze(pose(), viewpoint="front")
    hook.remove()
    assert torch.all(captured[0][:, :, 3, :] == 0)
    assert torch.all(captured[0][:, :, 5, :] == 0)


def test_threshold_and_invalid_smoothing():
    with pytest.raises(ValueError):
        ProbabilitySmoother(0)
    with pytest.raises(ValueError):
        ProbabilitySmoother(3, max_age_s=0)
