"""Measure a real image through frozen pose + classifier; no accuracy claim.

Run from the project root: python tools/benchmark_pose.py --image path/to/person.jpg
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from posture.pose import PoseExtractor
from posture.inference import Predictor
from posture.data import write_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', required=True)
    p.add_argument('--model', default='models/pose_landmarker_heavy.task')
    p.add_argument('--checkpoint', default='artifacts/run/best_model.pt')
    p.add_argument('--out', default='artifacts/run/pose_benchmark_rerun.json')
    p.add_argument('--warmup', type=int, default=3)
    p.add_argument('--iterations', type=int, default=20)
    args = p.parse_args()
    if args.warmup < 0 or args.iterations < 1:
        p.error('warmup must be nonnegative and iterations positive')
    frame = cv2.imread(args.image)
    if frame is None:
        p.error('image could not be read')
    predictor = Predictor(args.checkpoint)
    pose_ms, combined_ms, counts = [], [], []
    with PoseExtractor(args.model) as extractor:
        for i in range(args.warmup + args.iterations):
            start = time.perf_counter()
            pose = extractor.extract(frame)
            predictor.analyze(pose, viewpoint='unknown')
            duration = (time.perf_counter() - start) * 1000
            if i >= args.warmup:
                pose_ms.append(pose['pose_latency_ms'])
                combined_ms.append(duration)
                counts.append(pose['person_count'])
    report = {'input_sha256': hashlib.sha256(Path(args.image).read_bytes()).hexdigest(),
              'input_dimensions': [frame.shape[1], frame.shape[0]],
              'warmup': args.warmup, 'iterations': args.iterations,
              'person_counts': counts, 'pose_ms_p50': float(np.median(pose_ms)),
              'pose_ms_p95': float(np.percentile(pose_ms, 95)),
              'pose_geometry_classifier_ms_p50': float(np.median(combined_ms)),
              'pose_geometry_classifier_ms_p95': float(np.percentile(combined_ms, 95)),
              'compute_throughput_fps': 1000 / float(np.mean(combined_ms)),
              'hardware': {'platform': platform.platform(), 'processor': platform.processor()},
              'scope': 'Repeated static image, CPU, after warmup. Excludes camera, decoding, display and startup. No accuracy claim.'}
    write_json(args.out, report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
