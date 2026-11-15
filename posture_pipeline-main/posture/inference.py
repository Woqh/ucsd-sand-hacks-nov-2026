"""Quality-gated live inference with independently valid projected angles."""
from __future__ import annotations

from collections import deque
import json
from pathlib import Path
import platform
import textwrap
import time

import numpy as np
import torch

from .core import LABELS, measure_pose, normalize_world, correct_world_camera_roll
from .data import write_json
from .learning import CHAIN_INDICES, load_model, make_features
from .pose import CONNECTIONS, PoseExtractor


class ProbabilitySmoother:
    def __init__(self, window=1, max_age_s=0.5):
        if not 1 <= window <= 60:
            raise ValueError("Smoothing window must be 1..60 frames.")
        self.window = window
        if not np.isfinite(max_age_s) or max_age_s <= 0:
            raise ValueError("Smoothing maximum age must be finite and positive.")
        self.max_age_s = max_age_s
        self.history = deque(maxlen=window)

    def reset(self):
        self.history.clear()

    def update(self, probabilities, timestamp):
        if self.history and timestamp <= self.history[-1][0]:
            self.reset()
        while self.history and timestamp - self.history[0][0] > self.max_age_s:
            self.history.popleft()
        self.history.append((timestamp, np.array(probabilities)))
        return np.mean([p for _, p in self.history], axis=0), (timestamp - self.history[0][0]) / 2


class Predictor:
    def __init__(self, checkpoint_path, threshold=0.6, smoothing_window=1, device="cpu", smoothing_max_age_s=0.5):
        if not 0 <= threshold <= 1:
            raise ValueError("Probability threshold must be in [0,1].")
        self.model, self.checkpoint = load_model(checkpoint_path, device=device)
        self.device = torch.device(device)
        self.threshold = threshold
        self.smoother = ProbabilitySmoother(smoothing_window, smoothing_max_age_s)
        if list(self.checkpoint["labels"]) != list(LABELS):
            raise ValueError("Checkpoint label order mismatch.")
        if self.checkpoint.get("preprocessing_version") != "world_v1":
            raise ValueError("Unsupported preprocessing version.")
        torch.set_num_threads(int(self.checkpoint.get("config", {}).get("num_threads", 2)))

    def analyze(self, pose, viewpoint="unknown", facing="unknown", camera_roll_deg=0.0, timestamp=None):
        start = time.perf_counter()
        timestamp = time.monotonic() if timestamp is None else timestamp
        geometry = measure_pose(pose["image_xy"], pose["confidence"], pose["width"], pose["height"],
                                viewpoint=viewpoint, facing=facing, camera_roll_deg=camera_roll_deg)
        quality = geometry["quality"]
        warnings = list(quality.get("warnings", []))
        reasons = []
        count = int(pose.get("person_count", 0))
        if count == 0:
            reasons.append("No person detected.")
        elif count > 1:
            reasons.append("Multiple people detected; single-person identity is ambiguous.")
        image_xy = np.asarray(pose["image_xy"])
        in_frame = np.isfinite(image_xy).all(axis=1) & ((image_xy >= 0) & (image_xy <= 1)).all(axis=1)
        # World hallucinations with high scores do not prove that a joint is in view.
        usable_confidence = np.where(in_frame, pose["confidence"], 0.0)
        corrected_world = correct_world_camera_roll(pose["world"], camera_roll_deg)
        normalized = normalize_world(corrected_world, usable_confidence)
        if not normalized["valid"]:
            reasons.append(normalized.get("reason") or "Insufficient world landmarks.")
        selected = np.unique(np.array(CHAIN_INDICES).ravel())
        visible_fraction = float(normalized["mask"][selected].mean())
        if visible_fraction < 0.7 or not all(normalized["mask"][i] for i in (11, 12, 23, 24)):
            reasons.append("Severe occlusion or missing required torso landmarks.")
        if quality.get("pose_confidence", 0) < 0.5:
            reasons.append("Low torso landmark confidence.")
        if viewpoint not in self.checkpoint.get("supported_viewpoints", []):
            reasons.append(f"Viewpoint '{viewpoint}' is unsupported by this front-view training dataset.")
        probabilities = None
        if count == 1 and normalized["valid"]:
            conf = normalized["confidence"]
            known = normalized["confidence_known"]
            if not self.checkpoint.get("confidence_available", False):
                # Confidence is used above for quality and masks, but unseen feature
                # values must not enter channels that were always zero in training.
                conf, known = np.zeros_like(conf), np.zeros_like(known)
            features = make_features(normalized["xyz"][None], conf[None], normalized["mask"][None], known[None])
            with torch.inference_mode():
                logits = self.model(torch.as_tensor(features, dtype=torch.float32, device=self.device))
                probabilities = torch.softmax(logits / float(self.checkpoint["temperature"]), dim=-1)[0].cpu().numpy()
            if float(probabilities.max()) < self.threshold:
                reasons.append("Classifier probability is below the configured threshold.")
        raw_category = LABELS[int(probabilities.argmax())] if probabilities is not None else None
        raw_dict = {label: float(p) for label, p in zip(LABELS, probabilities)} if probabilities is not None else None
        raw_valid = probabilities is not None and not reasons
        smooth_prob, delay = None, 0.0
        if raw_valid:
            smooth_prob, delay = self.smoother.update(probabilities, timestamp)
            if float(smooth_prob.max()) < self.threshold:
                reasons.append("Smoothed classifier probability is below the configured threshold.")
        else:
            self.smoother.reset()
        smooth_dict = {label: float(p) for label, p in zip(LABELS, smooth_prob)} if smooth_prob is not None else None
        smooth_category = LABELS[int(smooth_prob.argmax())] if smooth_prob is not None else None
        valid = raw_valid and not reasons
        warnings += reasons
        if viewpoint == "side":
            warnings.append("A single side camera cannot rule out lateral leaning toward or away from the camera.")
        quality.update({"viewpoint": viewpoint, "viewpoint_source": "operator-supplied; not inferred",
                        "application_domain": "Seated people only; sitting is an operator-checked precondition",
                        "person_count": count, "valid_joint_fraction": visible_fraction,
                        "warnings": list(dict.fromkeys(warnings)),
                        "probability_calibration": "Temperature fitted on held-out MultiPosture participants; deployment calibration unverified",
                        "coordinate_spaces": {"classifier": "uncalibrated estimated world landmarks", "measurements": "2D image projections"}})
        return {"posture_category": smooth_category if valid else None,
                "class_probabilities": smooth_dict if valid else raw_dict,
                "prediction_valid": bool(valid), "abstention_reasons": reasons,
                "raw_prediction": {"posture_category": raw_category, "class_probabilities": raw_dict, "prediction_valid": bool(raw_valid)},
                "smoothed_prediction": {"posture_category": smooth_category, "class_probabilities": smooth_dict,
                                        "prediction_valid": bool(valid), "window_frames": self.smoother.window,
                                        "maximum_history_age_ms": self.smoother.max_age_s * 1000,
                                        "history_frames": len(self.smoother.history), "estimated_delay_ms": delay * 1000},
                "measurements": geometry["measurements"], "measurement_details": geometry["measurement_details"],
                "quality": quality, "timestamp_monotonic_s": float(timestamp),
                "latency_ms": {"pose": float(pose.get("pose_latency_ms", 0)),
                               "geometry_classifier_smoothing": (time.perf_counter() - start) * 1000}}


def draw_overlay(frame, pose, result):
    import cv2
    image = frame.copy()
    h, w = image.shape[:2]
    pixels = pose["image_xy"] * np.array([w, h])
    valid = np.isfinite(pixels).all(axis=1) & (pose["confidence"] >= 0.5)
    for a, b in CONNECTIONS:
        if valid[a] and valid[b]:
            cv2.line(image, tuple(pixels[a].astype(int)), tuple(pixels[b].astype(int)), (80, 215, 80), 2)
    for p in pixels[valid]:
        cv2.circle(image, tuple(p.astype(int)), 3, (30, 220, 255), -1)
    lines = ["Posture: " + (result["posture_category"] or "ABSTAIN")]
    if result.get("classification_method") == "side_angle_rule":
        rule = result["angle_rule"]
        lines += ["Sideways lean: UNOBSERVABLE",
                  f"Side angle rule: neutral {rule['neutral_angle_deg']:.1f}, band +/-{rule['lean_threshold_deg']:.1f} deg",
                  "C: set neutral | R: reset | L: face left | F: face right"]
    for name, value in result["measurements"].items():
        if value is not None:
            lines.append(f"{name.replace('_deg', '')}: {value:.1f} deg")
    for warning in result["quality"]["warnings"]:
        lines.extend(textwrap.wrap(warning, width=max(30, int(w / 9))))
    for i, line in enumerate(lines):
        y = 24 + i * 20
        if y > h - 10:
            break
        cv2.putText(image, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 3, cv2.LINE_AA)
        color = (255, 255, 255)
        if i == 0 and result["prediction_valid"]:
            color = (70, 230, 70) if result["posture_category"] == "upright" else (0, 190, 255)
        cv2.putText(image, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1, cv2.LINE_AA)
    return image


def run_camera(checkpoint, pose_model, source="0", viewpoint="side", facing="unknown", camera_roll_deg=0.0,
               threshold=0.6, smoothing_window=1, jsonl=None, max_frames=0, display=True, report=None,
               smoothing_max_age_s=0.5, method="auto", lean_threshold_deg=10.0, neutral_angle_deg=0.0):
    import cv2
    if method not in ("auto", "cnn", "side-angle"):
        raise ValueError("Unknown classification method.")
    selected_method = "side-angle" if method == "auto" and viewpoint == "side" else ("cnn" if method == "auto" else method)
    if selected_method == "side-angle":
        if viewpoint != "side":
            raise ValueError("Side-angle classification requires --viewpoint side.")
        from .side_angle import SideAnglePredictor
        predictor = SideAnglePredictor(lean_threshold_deg, neutral_angle_deg, smoothing_window, smoothing_max_age_s)
    else:
        predictor = Predictor(checkpoint, threshold, smoothing_window, smoothing_max_age_s=smoothing_max_age_s)
    cap = cv2.VideoCapture(int(source) if str(source).isdigit() else str(source))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera/video source {source}")
    sink = None
    if jsonl:
        Path(jsonl).parent.mkdir(parents=True, exist_ok=True)
        sink = Path(jsonl).open("w", encoding="utf-8")
    if max_frames < 0:
        cap.release()
        if sink:
            sink.close()
        raise ValueError("max_frames must be nonnegative.")
    durations, pose_times = [], []
    count = 0
    started = time.perf_counter()
    try:
        with PoseExtractor(pose_model) as extractor:
            while not max_frames or count < max_frames:
                t = time.perf_counter()
                ok, frame = cap.read()
                if not ok:
                    break
                pose = extractor.extract(frame)
                result = predictor.analyze(pose, viewpoint, facing, camera_roll_deg)
                if display:
                    cv2.imshow("Posture baseline - Q/Esc to exit", draw_overlay(frame, pose, result))
                duration = (time.perf_counter() - t) * 1000
                result["latency_ms"]["capture_pose_inference_overlay"] = duration
                if sink:
                    sink.write(json.dumps(result, allow_nan=False) + "\n")
                durations.append(duration)
                pose_times.append(pose["pose_latency_ms"])
                count += 1
                if display:
                    key = cv2.waitKeyEx(1)
                    if key in (ord("q"), 27):
                        break
                    if selected_method == "side-angle":
                        if key == ord("c") and result["prediction_valid"]:
                            predictor.set_neutral(result["smoothed_prediction"]["sagittal_angle_deg"])
                        elif key == ord("r"):
                            predictor.set_neutral(0.0)
                        elif key == ord("l"):
                            facing = "left"
                        elif key in (ord("f"), 2555904, 65363):
                            facing = "right"
    finally:
        cap.release()
        if sink:
            sink.close()
        if display:
            cv2.destroyAllWindows()
    elapsed = time.perf_counter() - started
    summary = {"frames": count, "wall_seconds": elapsed, "throughput_fps": count / elapsed,
               "latency_ms_p50": float(np.median(durations)) if durations else None,
               "latency_ms_p95": float(np.percentile(durations, 95)) if durations else None,
               "pose_ms_p50": float(np.median(pose_times)) if pose_times else None,
               "includes": "capture, pose, geometry, classifier, optional overlay; throughput also includes initialization/display/JSON I/O",
               "warmup_excluded": False, "hardware": {"platform": platform.platform(), "processor": platform.processor()},
               "viewpoint": viewpoint, "smoothing_window": smoothing_window, "classification_method": selected_method}
    if report:
        write_json(report, summary)
    return summary
