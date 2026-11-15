"""Tests for leakage barriers, feature semantics and the complete learning path."""
import json

import joblib
import numpy as np
import pytest
import torch

from posture.learning import (
    CHAIN_INDICES, PostureCNN, _augment, _fit_temperature, _load_data,
    evaluate, load_model, make_features, train,
)


def test_chain_feature_order_and_missing_confidence():
    xyz = np.arange(2 * 33 * 3, dtype=np.float32).reshape(2, 33, 3)
    confidence = np.full((2, 33), 0.9, dtype=np.float32)
    mask = np.ones((2, 33), dtype=np.float32)
    known = np.zeros((2, 33), dtype=np.float32)
    features = make_features(xyz, confidence, mask, known)
    assert features.shape == (2, 4, 6, 5)
    assert features.dtype == np.float32
    np.testing.assert_array_equal(features[1, 2, :3].T, xyz[1, CHAIN_INDICES[2]])
    assert np.all(features[:, :, 3] == 0)  # Unknown is not fabricated certainty.
    assert np.all(features[:, :, 4] == 1)
    assert np.all(features[:, :, 5] == 0)


def test_missing_joint_has_no_residual_coordinates_or_confidence():
    xyz = np.ones((1, 33, 3), dtype=np.float32)
    xyz[0, 13, 0] = np.nan
    confidence = mask = known = np.ones((1, 33), dtype=np.float32)
    features = make_features(xyz, confidence, mask, known)
    assert np.isfinite(features).all()
    np.testing.assert_array_equal(features[0, 2, :, 2], np.zeros(6))
    with pytest.raises(ValueError, match="shape"):
        make_features(xyz[0], confidence, mask, known)


def test_shared_convolution_does_not_cross_chain_boundary():
    torch.manual_seed(2)
    model = PostureCNN().eval()
    original = torch.randn(1, 4, 6, 5)
    perturbed = original.clone()
    perturbed[:, 1] += 100
    with torch.inference_mode():
        encoded_original = model.chain_encoder(original.reshape(4, 6, 5))
        encoded_perturbed = model.chain_encoder(perturbed.reshape(4, 6, 5))
        assert torch.equal(encoded_original[[0, 2, 3]], encoded_perturbed[[0, 2, 3]])
        assert not torch.equal(encoded_original[1], encoded_perturbed[1])
        assert model(original).shape == (1, 4)
    with pytest.raises(ValueError, match="CNN input"):
        model(torch.zeros(1, 6, 20))


def test_augmentation_preserves_torso_and_clears_missing_joint_channels():
    features = torch.ones(2, 4, 6, 5)
    dropped = _augment(features, scale_jitter=0, joint_dropout=1)
    for chain_number, chain in enumerate(CHAIN_INDICES):
        for position, landmark in enumerate(chain):
            expected = 1 if landmark in (11, 12, 23, 24) else 0
            assert torch.all(dropped[:, chain_number, :, position] == expected)
    assert torch.all(features == 1)  # Augmentation never mutates the cache tensor.
    scaled = _augment(features, scale_jitter=0.03, joint_dropout=0)
    assert torch.all(scaled[:, :, :3] >= 0.97) and torch.all(scaled[:, :, :3] <= 1.03)
    assert torch.equal(scaled[:, :, 3:], features[:, :, 3:])


def test_temperature_reduces_nll_for_overconfident_errors():
    logits = np.tile([[9.0, 0.0, 0.0, 0.0]], (40, 1))
    targets = np.tile(np.arange(4), 10)
    temperature, report = _fit_temperature(logits, targets, bins=10)
    assert temperature > 1
    assert report["after"]["nll"] < report["before"]["nll"]
    assert report["before"]["brier_multiclass_sum"] >= 0
    assert sum(row["count"] for row in report["after"]["reliability_bins"]) == len(targets)


@pytest.fixture
def synthetic_cache(tmp_path):
    rng = np.random.default_rng(11)
    y = np.tile(np.arange(4, dtype=np.int64), 16)
    subjects = np.repeat(np.array(["A", "B", "C", "D"]), 16)
    xyz = rng.normal(0, 0.02, (64, 33, 3)).astype(np.float32)
    # Artificial class information plus subject offsets, useful for detecting
    # train-only scaler fitting. These are software checks, not accuracy claims.
    for i, label in enumerate(y):
        xyz[i, :, 0] += label * 0.4 + (i // 16) * 0.1
    zeros = np.zeros((64, 33), dtype=np.float32)
    ones = np.ones((64, 33), dtype=np.float32)
    cache = tmp_path / "cache.npz"
    np.savez_compressed(cache, xyz=xyz, confidence=zeros, mask=ones, confidence_known=zeros, y=y, subject=subjects, ids=np.array([f"row_{i}" for i in range(64)]), valid=np.ones(64, dtype=bool))
    split_path = tmp_path / "split.json"
    split_path.write_text(json.dumps({key: list(range(i * 16, (i + 1) * 16)) for i, key in enumerate(["train", "val", "calibration", "test"])}), encoding="utf-8")
    return cache, split_path


def test_reject_subject_leakage_even_without_row_overlap(synthetic_cache):
    cache, split_path = synthetic_cache
    splits = json.loads(split_path.read_text())
    splits["train"].remove(15)
    splits["val"].append(15)
    split_path.write_text(json.dumps(splits), encoding="utf-8")
    with pytest.raises(ValueError, match="Subject leakage"):
        _load_data(cache, split_path)


def test_train_calibrate_evaluate_and_restricted_checkpoint(synthetic_cache, tmp_path):
    cache, split_path = synthetic_cache
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"epochs": 3, "patience": 2, "batch_size": 8, "device": "cpu", "num_threads": 1, "latency_warmup": 1, "latency_repeats": 3}), encoding="utf-8")
    output = tmp_path / "trained"
    result = train(cache, split_path, config_path, output)
    assert 1 <= result["best_epoch"] <= 3
    model, checkpoint = load_model(output / "best_model.pt")
    assert checkpoint["confidence_available"] is False
    assert checkpoint["supported_viewpoints"] == ["front"]
    assert checkpoint["temperature"] > 0
    assert model.training is False
    bundle = joblib.load(output / "baseline.joblib")
    data, splits = _load_data(cache, split_path)
    expected_mean = data["features"][splits["train"]].reshape(16, -1).mean(axis=0)
    np.testing.assert_allclose(bundle["pipeline"].named_steps["standardscaler"].mean_, expected_mean, atol=1e-6)
    report = evaluate(cache, split_path, output / "best_model.pt", output)
    assert report["held_out_test"] is True
    assert report["subjects"] == ["D"]
    assert report["cnn"]["n"] == 16
    assert len(report["cnn"]["per_class"]) == 4
    assert report["cnn_probability_threshold_coverage"][0]["coverage"] == 1.0
    assert "logistic_regression" in report
    assert "angle_accuracy" in report["unsupported_evaluations"]
    assert (output / "confusion_matrix_test.csv").exists()
    # Even a whitespace-only split edit is detected by recorded provenance.
    split_path.write_text(split_path.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="provenance"):
        evaluate(cache, split_path, output / "best_model.pt", output)
