"""Subject-disjoint training, calibration and evaluation of normalized world poses.

The cache is already normalized by data.py. This module never fits preprocessing
on evaluation samples. The optional joblib baseline is a trusted local artifact:
never load joblib/pickle files obtained from an untrusted source.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import platform
import random
import time
from pathlib import Path

import joblib
import numpy as np
import scipy.optimize
import sklearn
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from .core import LABELS


CHAIN_INDICES = [
    [0, 11, 23, 25, 27],
    [0, 12, 24, 26, 28],
    [23, 11, 13, 15, 19],
    [24, 12, 14, 16, 20],
]
DEFAULT_CONFIG = {
    "seed": 42,
    "epochs": 80,
    "batch_size": 128,
    "learning_rate": 0.001,
    "weight_decay": 0.0001,
    "patience": 12,
    "min_delta": 0.0001,
    "class_weighting": True,
    "scale_jitter": 0.03,
    "joint_dropout": 0.02,
    "dropout": 0.2,
    "device": "auto",
    "num_threads": 2,
    "ece_bins": 10,
    "latency_warmup": 20,
    "latency_repeats": 100,
    "probability_thresholds": [0.0, 0.5, 0.6, 0.7, 0.8, 0.9],
}


def make_features(xyz, confidence, mask, confidence_known):
    """Convert normalized arrays to [N, 4 chains, 6 channels, 5 landmarks].

    Channels are x, y, z, detector confidence, finite/available mask and
    confidence-known flag. Unknown confidence is explicitly zero. Availability
    is not evidence of visibility. No convolution joins separate chains.
    """
    xyz = np.asarray(xyz, dtype=np.float32)
    if xyz.ndim != 3 or xyz.shape[1:] != (33, 3):
        raise ValueError("xyz must have shape [N,33,3]")
    n = xyz.shape[0]
    confidence, mask, confidence_known = [
        np.asarray(a, dtype=np.float32) for a in (confidence, mask, confidence_known)
    ]
    if any(a.shape != (n, 33) for a in (confidence, mask, confidence_known)):
        raise ValueError("confidence, mask and confidence_known must be [N,33]")
    available = (np.isfinite(mask) & (mask > 0.5) & np.isfinite(xyz).all(axis=-1))
    known = available & np.isfinite(confidence_known) & (confidence_known > 0.5)
    known &= np.isfinite(confidence)
    clean_xyz = np.where(available[..., None], xyz, 0.0)
    conf = np.where(known, np.clip(confidence, 0.0, 1.0), 0.0)
    all_features = np.concatenate(
        [clean_xyz, conf[..., None], available[..., None], known[..., None]], axis=-1
    )
    return np.ascontiguousarray(all_features[:, CHAIN_INDICES, :].transpose(0, 1, 3, 2), dtype=np.float32)


class PostureCNN(nn.Module):
    """Shared 1-D convolutions within four chains, followed by joint reasoning."""

    def __init__(self, dropout=0.2, num_classes=len(LABELS)):
        super().__init__()
        self.chain_encoder = nn.Sequential(
            nn.Conv1d(6, 24, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv1d(24, 32, kernel_size=3, padding=1),
            nn.ReLU(),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(), nn.Linear(4 * 32 * 5, 96), nn.ReLU(),
            nn.Dropout(dropout), nn.Linear(96, num_classes),
        )

    def forward(self, x):
        if x.ndim != 4 or tuple(x.shape[1:]) != (4, 6, 5):
            raise ValueError("CNN input must have shape [B,4,6,5]")
        batch_size = x.shape[0]
        encoded = self.chain_encoder(x.reshape(batch_size * 4, 6, 5))
        # Keep each anatomical chain in a distinct position in the dense input.
        return self.classifier(encoded.reshape(batch_size, 4, 32, 5))


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_config(path):
    supplied = json.loads(Path(path).read_text(encoding="utf-8"))
    unknown = sorted(set(supplied) - set(DEFAULT_CONFIG))
    if unknown:
        raise ValueError(f"Unknown training configuration keys: {unknown}")
    config = {**copy.deepcopy(DEFAULT_CONFIG), **supplied}
    for key in ("epochs", "batch_size", "patience", "num_threads", "ece_bins", "latency_repeats"):
        if isinstance(config[key], bool) or not isinstance(config[key], int) or config[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    if not isinstance(config["seed"], int) or not 0 <= config["seed"] < 2**32:
        raise ValueError("seed must be an integer in [0,2**32)")
    if not isinstance(config["latency_warmup"], int) or config["latency_warmup"] < 0:
        raise ValueError("latency_warmup must be a nonnegative integer")
    for key in ("learning_rate", "weight_decay", "min_delta", "scale_jitter", "joint_dropout", "dropout"):
        if not isinstance(config[key], (int, float)) or not math.isfinite(config[key]):
            raise ValueError(f"{key} must be finite")
    if config["learning_rate"] <= 0 or config["weight_decay"] < 0 or config["min_delta"] < 0:
        raise ValueError("learning_rate must be positive; weight_decay and min_delta nonnegative")
    if not 0 <= config["dropout"] < 1 or not 0 <= config["scale_jitter"] <= 0.1:
        raise ValueError("dropout must be in [0,1); scale_jitter must be in [0,0.1]")
    if not 0 <= config["joint_dropout"] <= 0.2:
        raise ValueError("joint_dropout must be in [0,0.2]")
    if not isinstance(config["class_weighting"], bool):
        raise ValueError("class_weighting must be boolean")
    if not config["probability_thresholds"] or any(not 0 <= t <= 1 for t in config["probability_thresholds"]):
        raise ValueError("probability_thresholds must be a nonempty list in [0,1]")
    return config


def _device(name):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu") if name == "auto" else torch.device(name)
    if device.type not in ("cpu", "cuda"):
        raise ValueError("This implementation supports cpu or cuda devices")
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA requested but is unavailable")
    return device


def _load_data(cache_path, splits_path):
    with np.load(cache_path, allow_pickle=False) as archive:
        data = {key: archive[key] for key in ("xyz", "confidence", "mask", "confidence_known", "y", "subject", "ids", "valid")}
    n = len(data["y"])
    for key in ("y", "subject", "ids", "valid"):
        if data[key].shape != (n,):
            raise ValueError(f"Cache {key} must be a vector of length N")
    data["subject"] = data["subject"].astype(str)
    data["features"] = make_features(data["xyz"], data["confidence"], data["mask"], data["confidence_known"])
    if len(data["features"]) != n:
        raise ValueError("Feature and target counts do not match")
    if not np.issubdtype(data["y"].dtype, np.integer):
        raise ValueError("Cache labels must have integer dtype")
    raw_splits = json.loads(Path(splits_path).read_text(encoding="utf-8"))
    splits = {}
    seen_rows, seen_subjects = set(), set()
    for name in ("train", "val", "calibration", "test"):
        raw = raw_splits.get(name)
        if not isinstance(raw, list) or not raw or any(isinstance(i, bool) or not isinstance(i, int) for i in raw):
            raise ValueError(f"Split {name} must be a nonempty list of integer row indices")
        indices = np.asarray(raw, dtype=np.int64)
        rows = set(raw)
        if len(rows) != len(raw) or seen_rows.intersection(rows):
            raise ValueError("Split rows are duplicated or overlap")
        if indices.min() < 0 or indices.max() >= n:
            raise ValueError("Split index is out of bounds")
        if not np.all(data["valid"][indices]) or not np.all((data["y"][indices] >= 0) & (data["y"][indices] < len(LABELS))):
            raise ValueError("Splits must reference only valid samples with canonical labels")
        subjects = set(data["subject"][indices].tolist())
        if seen_subjects.intersection(subjects):
            raise ValueError("Subject leakage: a participant occurs in more than one split")
        seen_rows.update(rows)
        seen_subjects.update(subjects)
        splits[name] = indices
    if len(np.unique(data["y"][splits["train"]])) != len(LABELS):
        raise ValueError("Training split must include every canonical class")
    return data, splits


def _probabilities(logits, temperature=1.0):
    values = np.asarray(logits, dtype=np.float64) / float(temperature)
    values -= values.max(axis=1, keepdims=True)
    exponentials = np.exp(values)
    return exponentials / exponentials.sum(axis=1, keepdims=True)


def _probability_metrics(y, probabilities, bins=10):
    probabilities = np.asarray(probabilities, dtype=np.float64)
    y = np.asarray(y, dtype=np.int64)
    chosen = probabilities.argmax(axis=1)
    confidences = probabilities.max(axis=1)
    correctness = chosen == y
    nll = -np.log(np.clip(probabilities[np.arange(len(y)), y], 1e-15, 1.0)).mean()
    brier = np.square(probabilities - np.eye(len(LABELS))[y]).sum(axis=1).mean()
    ece = 0.0
    reliability = []
    for i in range(bins):
        low, high = i / bins, (i + 1) / bins
        member = (confidences >= low) & ((confidences < high) if i < bins - 1 else (confidences <= high))
        count = int(member.sum())
        confidence = float(confidences[member].mean()) if count else None
        accuracy = float(correctness[member].mean()) if count else None
        if count:
            ece += count / len(y) * abs(confidence - accuracy)
        reliability.append({"lower": low, "upper": high, "count": count, "mean_confidence": confidence, "accuracy": accuracy})
    return {"nll": float(nll), "brier_multiclass_sum": float(brier), "ece": float(ece), "ece_bins": bins, "reliability_bins": reliability}


def _fit_temperature(logits, y, bins):
    # Optimize the one scalar using held-out calibration labels only.
    objective = lambda log_t: _probability_metrics(y, _probabilities(logits, np.exp(log_t)), bins)["nll"]
    result = scipy.optimize.minimize_scalar(objective, method="bounded", bounds=(math.log(0.05), math.log(20.0)), options={"xatol": 1e-6})
    before = _probability_metrics(y, _probabilities(logits), bins)
    temperature = float(np.exp(result.x)) if result.success else 1.0
    after = _probability_metrics(y, _probabilities(logits, temperature), bins)
    if after["nll"] > before["nll"]:
        temperature, after = 1.0, before
    return temperature, {"n": int(len(y)), "temperature": temperature, "optimizer_success": bool(result.success), "bounds": [0.05, 20.0], "before": before, "after": after}


def _classification_metrics(y, probabilities, bins):
    prediction = probabilities.argmax(axis=1)
    labels = np.arange(len(LABELS))
    precision, recall, f1, support = precision_recall_fscore_support(y, prediction, labels=labels, zero_division=0)
    per_class = {name: {"precision": float(precision[i]), "recall": float(recall[i]), "f1": float(f1[i]), "support": int(support[i])} for i, name in enumerate(LABELS)}
    return {
        "n": int(len(y)), "accuracy": float(np.mean(prediction == y)),
        "balanced_accuracy_present_classes": float(recall[support > 0].mean()),
        "macro_f1_all_four_classes": float(f1.mean()),
        "weighted_f1": float(np.average(f1, weights=support)),
        "per_class": per_class,
        "confusion_matrix_true_rows_predicted_columns": confusion_matrix(y, prediction, labels=labels).tolist(),
        **_probability_metrics(y, probabilities, bins),
    }


def _coverage(y, probabilities, thresholds):
    confidence, prediction = probabilities.max(axis=1), probabilities.argmax(axis=1)
    result = []
    for threshold in thresholds:
        accepted = confidence >= threshold
        count = int(accepted.sum())
        result.append({"probability_threshold": float(threshold), "accepted": count, "total": len(y), "coverage": float(accepted.mean()), "accuracy_when_accepted": float((prediction[accepted] == y[accepted]).mean()) if count else None})
    return result


def _predict_logits(model, features, device, batch_size=256):
    model.eval()
    parts = []
    with torch.inference_mode():
        for start in range(0, len(features), batch_size):
            parts.append(model(torch.from_numpy(features[start:start + batch_size]).to(device)).cpu().numpy())
    return np.concatenate(parts)


def _augment(features, scale_jitter, joint_dropout):
    """Mild scale jitter and consistent missing-joint masks; preserve torso."""
    result = features.clone()
    if scale_jitter:
        scale = 1 + (torch.rand((len(result), 1, 1, 1), device=result.device) * 2 - 1) * scale_jitter
        result[:, :, :3, :] *= scale
    if joint_dropout:
        dropped = torch.rand((len(result), 33), device=result.device) < joint_dropout
        dropped[:, [11, 12, 23, 24]] = False
        # Repeated landmarks get the same dropout decision in every chain.
        chain_dropped = dropped[:, torch.tensor(CHAIN_INDICES, device=result.device)]
        result.masked_fill_(chain_dropped[:, :, None, :], 0.0)
    return result


def train(cache_path, splits_path, config_path, output_dir):
    """Train CNN/baseline, fit scalar temperatures, and save best validation model."""
    config = _read_config(config_path)
    torch.set_num_threads(config["num_threads"])
    random.seed(config["seed"])
    np.random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config["seed"])
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)
    device = _device(config["device"])
    data, splits = _load_data(cache_path, splits_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    features, y = data["features"], data["y"]
    tr, val, cal = (splits[key] for key in ("train", "val", "calibration"))
    class_counts = np.bincount(y[tr], minlength=len(LABELS))
    weights = len(tr) / (len(LABELS) * class_counts)
    criterion = nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32, device=device) if config["class_weighting"] else None)
    model = PostureCNN(dropout=config["dropout"]).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config["learning_rate"], weight_decay=config["weight_decay"])
    generator = torch.Generator().manual_seed(config["seed"])
    loader = DataLoader(TensorDataset(torch.from_numpy(features[tr]), torch.from_numpy(y[tr].astype(np.int64))), batch_size=config["batch_size"], shuffle=True, generator=generator, num_workers=0)
    history, best_state, best_score, best_epoch, stale = [], None, -1.0, 0, 0
    started = time.perf_counter()
    for epoch in range(1, config["epochs"] + 1):
        model.train()
        loss_total, count = 0.0, 0
        for x_batch, y_batch in loader:
            x_batch, y_batch = x_batch.to(device), y_batch.to(device)
            x_batch = _augment(x_batch, config["scale_jitter"], config["joint_dropout"])
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(x_batch), y_batch)
            loss.backward()
            optimizer.step()
            loss_total += float(loss.detach().cpu()) * len(y_batch)
            count += len(y_batch)
        val_probabilities = _probabilities(_predict_logits(model, features[val], device))
        val_metrics = _classification_metrics(y[val], val_probabilities, config["ece_bins"])
        score = val_metrics["macro_f1_all_four_classes"]
        history.append({"epoch": epoch, "training_weighted_batch_mean_loss": loss_total / count, "val_macro_f1": score, "val_accuracy": val_metrics["accuracy"], "val_nll": val_metrics["nll"]})
        if score > best_score + config["min_delta"]:
            best_score, best_epoch, stale = score, epoch, 0
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        else:
            stale += 1
        if stale >= config["patience"]:
            break
    model.load_state_dict(best_state)
    cal_logits = _predict_logits(model, features[cal], device)
    temperature, cnn_calibration = _fit_temperature(cal_logits, y[cal], config["ece_bins"])
    baseline = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=1.0, class_weight="balanced" if config["class_weighting"] else None, random_state=config["seed"]))
    baseline.fit(features[tr].reshape(len(tr), -1), y[tr])
    baseline_cal_logits = baseline.decision_function(features[cal].reshape(len(cal), -1))
    baseline_temperature, baseline_calibration = _fit_temperature(baseline_cal_logits, y[cal], config["ece_bins"])
    common = {
        "labels": list(LABELS), "config": config, "supported_viewpoints": ["front"],
        "confidence_available": False, "preprocessing_version": "world_v1",
        "cache_sha256": _sha256(cache_path), "splits_sha256": _sha256(splits_path),
        "split_subjects": {key: sorted(set(data["subject"][indices].tolist())) for key, indices in splits.items()},
    }
    checkpoint = {**common, "state_dict": best_state, "temperature": temperature, "architecture": "shared_chain_conv1d_v1", "best_epoch": best_epoch, "best_validation_macro_f1": best_score}
    torch.save(checkpoint, output_dir / "best_model.pt")
    joblib.dump({**common, "pipeline": baseline, "temperature": baseline_temperature}, output_dir / "baseline.joblib")
    calibration = {"split": "calibration", "subjects": common["split_subjects"]["calibration"], "cnn": cnn_calibration, "logistic_regression": baseline_calibration, "note": "Calibration metrics are fit-split diagnostics. Final calibration quality must be assessed on untouched test subjects."}
    summary = {
        "best_epoch": best_epoch, "epochs_run": len(history), "best_validation_macro_f1": best_score,
        "training_class_counts": {label: int(class_counts[i]) for i, label in enumerate(LABELS)},
        "training_class_weights": {label: float(weights[i]) if config["class_weighting"] else 1.0 for i, label in enumerate(LABELS)},
        "split_counts": {key: len(indices) for key, indices in splits.items()}, "split_subjects": common["split_subjects"],
        "training_and_calibration_seconds": time.perf_counter() - started,
        "device": str(device), "parameter_count": sum(p.numel() for p in model.parameters()),
        "checkpoint": str(output_dir / "best_model.pt"), "baseline": str(output_dir / "baseline.joblib"),
        "calibration": calibration, "config": config,
    }
    _write_json(output_dir / "training_history.json", history)
    _write_json(output_dir / "calibration.json", calibration)
    _write_json(output_dir / "train_summary.json", summary)
    return summary


def load_model(checkpoint_path, device="cpu"):
    """Load a state-dict checkpoint using PyTorch's restricted weights-only loader."""
    device = _device(device)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if checkpoint.get("labels") != list(LABELS) or checkpoint.get("preprocessing_version") != "world_v1":
        raise ValueError("Checkpoint label order or preprocessing version is incompatible")
    if checkpoint.get("architecture") != "shared_chain_conv1d_v1":
        raise ValueError("Checkpoint architecture is unsupported")
    temperature = checkpoint.get("temperature", 1.0)
    if not isinstance(temperature, (int, float)) or not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("Checkpoint temperature must be finite and positive")
    model = PostureCNN(dropout=checkpoint["config"]["dropout"])
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.to(device).eval()
    return model, checkpoint


def _latency(model, feature, device, config, baseline=None):
    tensor = torch.from_numpy(feature).to(device)
    def synchronize():
        if device.type == "cuda":
            torch.cuda.synchronize(device)
    def summarize(durations):
        return {"mean_ms": float(np.mean(durations)), "p50_ms": float(np.percentile(durations, 50)), "p95_ms": float(np.percentile(durations, 95)), "repeats": len(durations), "batch_size": 1}
    with torch.inference_mode():
        for _ in range(config["latency_warmup"]):
            model(tensor)
        synchronize()
        durations = []
        for _ in range(config["latency_repeats"]):
            synchronize()
            before = time.perf_counter_ns()
            model(tensor)
            synchronize()
            durations.append((time.perf_counter_ns() - before) / 1e6)
    result = {"cnn": summarize(durations), "scope": "Classifier forward pass only, batch 1; input prepared and transferred before timing. Excludes camera, MediaPipe, normalization, feature building, softmax, smoothing and rendering."}
    if baseline is not None:
        vector = feature.reshape(1, -1)
        for _ in range(config["latency_warmup"]):
            baseline.decision_function(vector)
        durations = []
        for _ in range(config["latency_repeats"]):
            before = time.perf_counter_ns()
            baseline.decision_function(vector)
            durations.append((time.perf_counter_ns() - before) / 1e6)
        result["logistic_regression_including_standard_scaler"] = summarize(durations)
    result["hardware"] = {"platform": platform.platform(), "processor": platform.processor() or "unavailable", "machine": platform.machine(), "python": platform.python_version(), "torch": str(torch.__version__), "numpy": np.__version__, "sklearn": sklearn.__version__, "device": str(device), "cuda_device": torch.cuda.get_device_name(device) if device.type == "cuda" else None, "torch_cpu_threads": torch.get_num_threads()}
    return result


def evaluate(cache_path, splits_path, checkpoint_path, output_dir, split="test"):
    """Evaluate one predeclared split; never refit weights, scaler or temperature."""
    if split not in ("train", "val", "calibration", "test"):
        raise ValueError("Unknown evaluation split")
    model, checkpoint = load_model(checkpoint_path)
    config = checkpoint["config"]
    torch.set_num_threads(config["num_threads"])
    device = _device(config["device"])
    model.to(device)
    if _sha256(cache_path) != checkpoint["cache_sha256"] or _sha256(splits_path) != checkpoint["splits_sha256"]:
        raise ValueError("Cache or split definition changed since training; evaluation provenance does not match")
    data, splits = _load_data(cache_path, splits_path)
    indices = splits[split]
    features, y, subjects = data["features"][indices], data["y"][indices], data["subject"][indices]
    logits = _predict_logits(model, features, device)
    probabilities = _probabilities(logits, checkpoint["temperature"])
    report = {
        "split": split, "held_out_test": split == "test", "labels": list(LABELS),
        "cache_sha256": checkpoint["cache_sha256"], "splits_sha256": checkpoint["splits_sha256"],
        "subjects": sorted(set(subjects.tolist())), "temperature": checkpoint["temperature"],
        "cnn": _classification_metrics(y, probabilities, config["ece_bins"]),
        "cnn_before_calibration": _classification_metrics(y, _probabilities(logits), config["ece_bins"]),
        "cnn_per_subject": {subject: _classification_metrics(y[subjects == subject], probabilities[subjects == subject], config["ece_bins"]) for subject in sorted(set(subjects.tolist()))},
        "cnn_probability_threshold_coverage": _coverage(y, probabilities, config["probability_thresholds"]),
        "unsupported_evaluations": {
            "viewpoint_stratification": "No per-row viewpoint annotation; source describes an approximately frontal fixed camera. Side and oblique validation unavailable.",
            "occlusion_stratification": "No occlusion or detector-confidence annotations. Finite coordinates do not establish visibility.",
            "angle_accuracy": "No ground-truth angles. Numerical image-angle validation requires a separate labeled test set.",
            "pose_confidence_coverage": "No per-landmark confidence in the source CSV; thresholds here use classifier probability only.",
            "end_to_end_latency": "Classifier-only timing; camera capture and pose detection were not benchmarked.",
        },
        "metric_definitions": {"macro_f1": "Arithmetic mean over all four canonical classes, with zero for undefined class F1.", "brier": "Mean per-row sum of squared differences between four probabilities and one-hot labels; range 0 to 2.", "ece": "Equal-width bins of maximum class probability; bin-size-weighted absolute confidence-minus-accuracy.", "coverage": "Fraction retained by maximum calibrated probability >= threshold; accuracy uses retained rows only.", "per_subject": "Same four-class macro-F1 convention; inspect support when a class is absent."},
    }
    baseline_path = Path(checkpoint_path).parent / "baseline.joblib"
    baseline = None
    if baseline_path.exists():
        # Only load a locally produced, trusted artifact. Joblib uses pickle.
        bundle = joblib.load(baseline_path)
        if bundle["cache_sha256"] != checkpoint["cache_sha256"] or bundle["splits_sha256"] != checkpoint["splits_sha256"] or bundle["labels"] != list(LABELS):
            raise ValueError("Baseline provenance or labels do not match checkpoint")
        baseline = bundle["pipeline"]
        baseline_logits = baseline.decision_function(features.reshape(len(features), -1))
        baseline_probabilities = _probabilities(baseline_logits, bundle["temperature"])
        report["logistic_regression"] = _classification_metrics(y, baseline_probabilities, config["ece_bins"])
        report["logistic_regression_before_calibration"] = _classification_metrics(y, _probabilities(baseline_logits), config["ece_bins"])
        report["logistic_regression_temperature"] = bundle["temperature"]
        report["logistic_regression_per_subject"] = {subject: _classification_metrics(y[subjects == subject], baseline_probabilities[subjects == subject], config["ece_bins"]) for subject in sorted(set(subjects.tolist()))}
        report["logistic_regression_probability_threshold_coverage"] = _coverage(y, baseline_probabilities, config["probability_thresholds"])
        report["cnn_minus_baseline"] = {key: report["cnn"][key] - report["logistic_regression"][key] for key in ("accuracy", "macro_f1_all_four_classes", "nll", "brier_multiclass_sum", "ece")}
    else:
        report["baseline_status"] = "baseline.joblib absent; comparison unavailable"
    report["latency"] = _latency(model, features[:1], device, config, baseline)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / f"evaluation_{split}.json", report)
    with (output_dir / f"confusion_matrix_{split}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["true_label / predicted_label", *LABELS])
        for label, row in zip(LABELS, report["cnn"]["confusion_matrix_true_rows_predicted_columns"]):
            writer.writerow([label, *row])
    return report
