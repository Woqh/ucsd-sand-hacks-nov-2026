"""Verified MultiPosture acquisition, inspection and participant-separated cache."""
from __future__ import annotations

import csv
import hashlib
import json
import urllib.request
from collections import Counter
from pathlib import Path

import numpy as np

from .core import LANDMARK_NAMES, LABELS, normalize_world

URL = "https://zenodo.org/records/14230872/files/data.csv?download=1"
EXPECTED_MD5 = "7efbc94d653acf32eefecec3ff26d6c6"
LABEL_MAPPING = {"TUP": "upright", "TLF": "leaning_forward", "TLB": "leaning_back",
                 "TLL": "leaning_side", "TLR": "leaning_side"}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")


def download_csv(destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = urllib.request.urlopen(URL, timeout=120).read()
    if hashlib.md5(payload).hexdigest() != EXPECTED_MD5:
        raise ValueError("Dataset checksum differs from verified Zenodo v1; inspect before training.")
    destination.write_bytes(payload)
    return {"path": str(destination), "bytes": len(payload), "md5": EXPECTED_MD5}


def load_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        required = ["subject", "upperbody_label", "lowerbody_label"]
        required += [f"{name}_{axis}" for name in LANDMARK_NAMES for axis in "xyz"]
        missing = sorted(set(required) - set(fields))
        if missing:
            raise ValueError(f"CSV missing columns: {missing}")
        rows = list(reader)
    if not rows:
        raise ValueError("Dataset is empty.")
    unknown = set(r["upperbody_label"] for r in rows) - set(LABEL_MAPPING)
    if unknown:
        raise ValueError(f"Unmapped upper-body labels: {sorted(unknown)}")
    world = np.array([[[float(r[f"{name}_{axis}"]) for axis in "xyz"]
                       for name in LANDMARK_NAMES] for r in rows], dtype=np.float32)
    return rows, world, fields


def audit_csv(path, output=None):
    rows, world, fields = load_csv(path)
    raw = Path(path).read_bytes()
    keys = [hashlib.sha256(x.tobytes()).hexdigest() for x in world]
    audit = {
        "record": "https://zenodo.org/records/14230872", "license": "CC-BY-4.0",
        "source_file": "data.csv", "actual_rows": len(rows), "record_description_rows": 4800,
        "actual_landmarks": 33, "record_description_landmarks": 11,
        "md5": hashlib.md5(raw).hexdigest(), "sha256": hashlib.sha256(raw).hexdigest(),
        "verified_v1_checksum": hashlib.md5(raw).hexdigest() == EXPECTED_MD5,
        "columns": fields,
        "upper_labels": dict(sorted(Counter(r["upperbody_label"] for r in rows).items())),
        "mapped_labels": dict(sorted(Counter(LABEL_MAPPING[r["upperbody_label"]] for r in rows).items())),
        "lower_labels": dict(sorted(Counter(r["lowerbody_label"] for r in rows).items())),
        "subjects": dict(sorted(Counter(r["subject"] for r in rows).items(), key=lambda x: int(x[0]))),
        "nonfinite_coordinates": int((~np.isfinite(world)).sum()),
        "duplicate_coordinate_rows": len(keys) - len(set(keys)),
        "coordinate_space": "MediaPipe estimated world landmarks, camera axes; uncalibrated monocular estimates",
        "viewpoint": "Study reports front camera, slight lateral adjustment; no per-row annotations",
        "missing_metadata": ["session", "video_id", "timestamp", "viewpoint", "occlusion", "visibility", "presence", "angle_ground_truth"],
        "raw_images_available": False,
    }
    if output:
        write_json(output, audit)
    return audit


def validate_split(split, subjects, n):
    required = ("train", "val", "calibration", "test")
    seen_indices, seen_subjects = set(), set()
    for name in required:
        indices = split.get(name, [])
        if not indices:
            raise ValueError(f"Empty split: {name}")
        if any(not isinstance(i, int) or i < 0 or i >= n for i in indices):
            raise ValueError("Invalid split row index.")
        if len(set(indices)) != len(indices) or seen_indices.intersection(indices):
            raise ValueError("Rows overlap between splits.")
        people = set(str(subjects[i]) for i in indices)
        if people & seen_subjects:
            raise ValueError("Participant leakage between splits.")
        seen_indices.update(indices)
        seen_subjects.update(people)
    if seen_indices != set(range(n)):
        raise ValueError("Every dataset row must belong to exactly one split.")


def prepare_csv(path, output_dir, split_config=None, seed=42):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    audit = audit_csv(path, out / "audit.json")
    if not audit["verified_v1_checksum"]:
        raise ValueError("Expected verified MultiPosture v1 file; checksum mismatch.")
    rows, world, _ = load_csv(path)
    normalized = [normalize_world(w) for w in world]
    arrays = {key: np.stack([r[key] for r in normalized])
              for key in ("xyz", "confidence", "mask", "confidence_known")}
    arrays.update(y=np.array([list(LABELS).index(LABEL_MAPPING[r["upperbody_label"]]) for r in rows], dtype=np.int64),
                  subject=np.array([r["subject"] for r in rows]),
                  ids=np.array([f"zenodo14230872:csv_row:{i+2}" for i in range(len(rows))]),
                  valid=np.array([r["valid"] for r in normalized], dtype=bool))
    if not arrays["valid"].all():
        raise ValueError("Dataset contains invalid torso references; inspect before training.")
    people = sorted(set(arrays["subject"].tolist()), key=int)
    if split_config:
        groups = json.loads(Path(split_config).read_text(encoding="utf-8"))
    else:
        if len(people) < 8:
            raise ValueError("Need at least eight subjects for train/val/calibration/test partitions.")
        np.random.default_rng(seed).shuffle(people)
        groups = {"test": people[:2], "calibration": people[2:4], "val": people[4:6], "train": people[6:]}
    groups = {k: [str(p) for p in v] for k, v in groups.items()}
    split = {k: [i for i, p in enumerate(arrays["subject"]) if p in groups[k]]
             for k in ("train", "val", "calibration", "test")}
    validate_split(split, arrays["subject"], len(rows))
    # Duplicate skeletons in different partitions can leak even with distinct IDs.
    owners = {}
    for partition, indices in split.items():
        for i in indices:
            key = hashlib.sha256(world[i].tobytes()).hexdigest()
            if key in owners and owners[key] != partition:
                raise ValueError("Identical coordinates cross partitions; investigate duplicates.")
            owners[key] = partition
        if set(arrays["y"][indices]) != set(range(4)):
            raise ValueError(f"All four classes required in {partition}.")
    np.savez_compressed(out / "cache.npz", **arrays)
    write_json(out / "split.json", split)
    write_json(out / "subject_split.json", groups)
    write_json(out / "label_mapping.json", {"labels": list(LABELS), "source_mapping": LABEL_MAPPING})
    metadata = {"preprocessing_version": "world_v1", "source_sha256": audit["sha256"],
                "normalization": "hip midpoint; median visible shoulder-hip lengths; no rotation",
                "confidence_available": False, "source_estimator": "MediaPipe Pose Heavy, source version unknown",
                "confidence_semantics": "zeros with known=0 mean unavailable, not invisible",
                "split_seed": seed, "subject_split": groups,
                "split_sizes": {k: len(v) for k, v in split.items()},
                "supported_viewpoints": ["front"],
                "viewpoint_limit": "Approximate acquisition domain from paper, not per-frame verified",
                "temporal_available": False,
                "session_leakage_control": "Subjects are disjoint, enclosing all their sessions; sessions not separately identified"}
    write_json(out / "metadata.json", metadata)
    return metadata
