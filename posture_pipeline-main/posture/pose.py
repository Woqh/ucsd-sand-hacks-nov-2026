"""Frozen MediaPipe Tasks extraction. Image and estimated world spaces stay distinct."""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import time
import urllib.request
from pathlib import Path

import numpy as np

from .core import LABELS, normalize_world, correct_world_camera_roll
from .data import write_json

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task"
MODEL_SHA256 = "64437af838a65d18e5ba7a0d39b465540069bc8aae8308de3e318aad31fcbc7b"
CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8),
               (9, 10), (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21),
               (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (11, 23), (12, 24),
               (23, 24), (23, 25), (25, 27), (27, 29), (29, 31), (27, 31),
               (24, 26), (26, 28), (28, 30), (30, 32), (28, 32)]


def download_model(destination):
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = urllib.request.urlopen(MODEL_URL, timeout=120).read()
    if hashlib.sha256(payload).hexdigest() != MODEL_SHA256:
        raise ValueError("Unexpected pose model checksum.")
    path.write_bytes(payload)
    return {"path": str(path), "sha256": MODEL_SHA256}


class PoseExtractor:
    def __init__(self, model_path):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode
        self.mp = mp
        self.model_sha256 = hashlib.sha256(Path(model_path).read_bytes()).hexdigest()
        self.landmarker = PoseLandmarker.create_from_options(PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)), running_mode=RunningMode.IMAGE,
            num_poses=2, min_pose_detection_confidence=0.5, min_pose_presence_confidence=0.5,
            output_segmentation_masks=False))

    def extract(self, bgr):
        import cv2
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        start = time.perf_counter()
        result = self.landmarker.detect(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb))
        elapsed = (time.perf_counter() - start) * 1000
        count = len(result.pose_landmarks)
        image_xy = np.full((33, 2), np.nan, dtype=np.float32)
        world = np.full((33, 3), np.nan, dtype=np.float32)
        confidence = np.zeros(33, dtype=np.float32)
        if count:
            image_xy = np.array([[p.x, p.y] for p in result.pose_landmarks[0]], dtype=np.float32)
            confidence = np.array([min(p.visibility, p.presence) for p in result.pose_landmarks[0]], dtype=np.float32)
            if result.pose_world_landmarks:
                world = np.array([[p.x, p.y, p.z] for p in result.pose_world_landmarks[0]], dtype=np.float32)
        return {"image_xy": image_xy, "world": world, "confidence": confidence,
                "person_count": count, "pose_latency_ms": elapsed,
                "width": bgr.shape[1], "height": bgr.shape[0]}

    def close(self):
        self.landmarker.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def extract_manifest(manifest_path, model_path, output_dir):
    """Each row explicitly identifies an image, or a video + decoded frame_index.

    This collects features only: new datasets need their own reviewed group split
    and domain validation, not the MultiPosture fixed-file preparation command.
    """
    import cv2
    manifest_path, out = Path(manifest_path), Path(output_dir)
    with manifest_path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or any(not r.get("id") or not r.get("path") or not r.get("subject") for r in rows):
        raise ValueError("Manifest requires nonempty id,path,subject columns for every row.")
    if len(set(r["id"] for r in rows)) != len(rows):
        raise ValueError("Manifest IDs must be unique.")
    features, extra, sources = [], [], {}
    with PoseExtractor(model_path) as extractor:
        for row in rows:
            label = row.get("label", "")
            if label and label not in LABELS:
                raise ValueError(f"Unknown label {label}; labels must be manually supplied canonical names.")
            path = (manifest_path.parent / row["path"]).resolve()
            if str(path) not in sources:
                sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            if row.get("frame_index", "").strip():
                frame_index = int(row["frame_index"])
                if frame_index < 0 or not row.get("video_id"):
                    raise ValueError("Video frames need nonnegative frame_index and video_id.")
                cap = cv2.VideoCapture(str(path))
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = cap.read()
                cap.release()
                if not ok:
                    raise ValueError(f"Cannot decode {path} frame {frame_index}")
            else:
                frame = cv2.imread(str(path))
                if frame is None:
                    raise ValueError(f"Cannot read image {path}")
            pose = extractor.extract(frame)
            xy = pose["image_xy"]
            in_frame = np.isfinite(xy).all(axis=1) & ((xy >= 0) & (xy <= 1)).all(axis=1)
            world = correct_world_camera_roll(pose["world"], float(row.get("camera_roll_deg") or 0))
            f = normalize_world(world, np.where(in_frame, pose["confidence"], 0.0))
            f["valid"] = bool(f["valid"] and pose["person_count"] == 1)
            features.append(f)
            extra.append({**row, "resolved_path": str(path), "source_sha256": sources[str(path)],
                          "person_count": pose["person_count"], "pose_latency_ms": pose["pose_latency_ms"]})
        model_hash = extractor.model_sha256
    out.mkdir(parents=True, exist_ok=True)
    arrays = {k: np.stack([f[k] for f in features]) for k in ("xyz", "confidence", "mask", "confidence_known")}
    arrays.update(y=np.array([list(LABELS).index(r["label"]) if r.get("label") else -1 for r in rows]),
                  ids=np.array([r["id"] for r in rows]), subject=np.array([r["subject"] for r in rows]),
                  valid=np.array([f["valid"] for f in features]))
    np.savez_compressed(out / "cache.npz", **arrays)
    write_json(out / "manifest.json", extra)
    metadata = {"preprocessing_version": "world_v1", "pose_model_sha256": model_hash,
                "mediapipe_version": importlib.metadata.version("mediapipe"),
                "running_mode": "IMAGE (stateless, reproducible across frame order)",
                "confidence_available": True, "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                "rows": len(rows), "valid_rows": int(arrays["valid"].sum()),
                "warning": "This cache is for collection/review. Training command currently supports audited MultiPosture only. New media need explicit subject/session/video grouping and validation."}
    write_json(out / "metadata.json", metadata)
    return metadata
