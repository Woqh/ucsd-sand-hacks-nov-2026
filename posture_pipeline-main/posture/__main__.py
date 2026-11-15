"""Run `python -m posture --help`. Imports are lazy so audit needs only NumPy."""
import argparse
import json


def main():
    parser = argparse.ArgumentParser(description="MultiPosture research baseline with conservative deployment gating")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("download", help="Fetch checksum-verified MultiPosture v1 CSV")
    p.add_argument("--out", default="data/raw/data.csv")
    p = commands.add_parser("download-model", help="Fetch pinned MediaPipe Heavy Tasks model")
    p.add_argument("--out", default="models/pose_landmarker_heavy.task")
    p = commands.add_parser("audit", help="Inspect exact CSV schema, counts and hash")
    p.add_argument("--csv", default="data/raw/data.csv")
    p.add_argument("--out", default="artifacts/audit.json")
    p = commands.add_parser("prepare", help="Normalize and make disjoint participant partitions")
    p.add_argument("--csv", default="data/raw/data.csv")
    p.add_argument("--out", default="data/prepared")
    p.add_argument("--subject-split", help="JSON mapping train,val,calibration,test to subject IDs")
    p.add_argument("--seed", type=int, default=42)
    p = commands.add_parser("train", help="Fit CNN, shallow baseline, and held-out calibration")
    p.add_argument("--cache", default="data/prepared/cache.npz")
    p.add_argument("--splits", default="data/prepared/split.json")
    p.add_argument("--config", default="configs/train.json")
    p.add_argument("--out", default="artifacts/run")
    p = commands.add_parser("evaluate", help="Evaluate saved checkpoint without tuning on test")
    p.add_argument("--cache", default="data/prepared/cache.npz")
    p.add_argument("--splits", default="data/prepared/split.json")
    p.add_argument("--checkpoint", default="artifacts/run/best_model.pt")
    p.add_argument("--out", default="artifacts/run")
    p.add_argument("--split", choices=["val", "calibration", "test"], default="test")
    p = commands.add_parser("extract", help="Cache frozen pose features from an explicit media manifest")
    p.add_argument("--manifest", required=True)
    p.add_argument("--model", default="models/pose_landmarker_heavy.task")
    p.add_argument("--out", required=True)
    p = commands.add_parser("webcam", help="Camera/video overlay; side view uses three-class angle rules by default")
    p.add_argument("--method", choices=["auto", "cnn", "side-angle"], default="auto")
    p.add_argument("--lean-threshold-deg", type=float, default=10.0)
    p.add_argument("--neutral-angle-deg", type=float, default=0.0)
    p.add_argument("--checkpoint", default="artifacts/run/best_model.pt")
    p.add_argument("--model", default="models/pose_landmarker_heavy.task")
    p.add_argument("--source", default="0", help="Camera index or video path")
    p.add_argument("--viewpoint", choices=["front", "side", "oblique", "unknown"], default="side")
    p.add_argument("--facing", choices=["left", "right", "unknown"], default="unknown")
    p.add_argument("--camera-roll-deg", type=float, default=0.0)
    p.add_argument("--threshold", type=float, default=0.6)
    p.add_argument("--smoothing-window", type=int, default=1)
    p.add_argument("--smoothing-max-age-ms", type=float, default=500)
    p.add_argument("--jsonl")
    p.add_argument("--max-frames", type=int, default=0)
    p.add_argument("--no-display", action="store_true")
    p.add_argument("--report")
    args = parser.parse_args()
    if args.command == "download":
        from .data import download_csv
        result = download_csv(args.out)
    elif args.command == "download-model":
        from .pose import download_model
        result = download_model(args.out)
    elif args.command == "audit":
        from .data import audit_csv
        result = audit_csv(args.csv, args.out)
    elif args.command == "prepare":
        from .data import prepare_csv
        result = prepare_csv(args.csv, args.out, args.subject_split, args.seed)
    elif args.command == "train":
        from .learning import train
        result = train(args.cache, args.splits, args.config, args.out)
    elif args.command == "evaluate":
        from .learning import evaluate
        result = evaluate(args.cache, args.splits, args.checkpoint, args.out, args.split)
    elif args.command == "extract":
        from .pose import extract_manifest
        result = extract_manifest(args.manifest, args.model, args.out)
    else:
        from .inference import run_camera
        result = run_camera(args.checkpoint, args.model, args.source, args.viewpoint, args.facing,
                            args.camera_roll_deg, args.threshold, args.smoothing_window,
                            args.jsonl, args.max_frames, not args.no_display, args.report,
                            args.smoothing_max_age_ms / 1000, args.method,
                            args.lean_threshold_deg, args.neutral_angle_deg)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
