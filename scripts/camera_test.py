#!/usr/bin/env python3
"""Check that a webcam feed (e.g. the iPhone via Camo) reaches Python/OpenCV on this laptop.

Dev-only: the real app runs the model on the phone. This just proves frames arrive, so the
teammate's OpenCV model can be prototyped on the laptop against the Camo feed.

  pip install opencv-python
  python scripts/camera_test.py --list        # probe camera indices 0-5, save a snapshot of each
  python scripts/camera_test.py --index 1     # live preview of one camera (q = quit, s = snapshot)

Frames stay in memory; only the snapshots you ask for are written (to scripts/_camera_snapshots/).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    import cv2
except ImportError:
    sys.exit("OpenCV missing:  pip install opencv-python")

SNAP_DIR = Path(__file__).parent / "_camera_snapshots"


BACKENDS = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "any": cv2.CAP_ANY}
BACKEND = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY  # DirectShow sees Camo on Windows


def open_cam(index: int) -> "cv2.VideoCapture":
    cap = cv2.VideoCapture(index, BACKEND)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return cap


def list_cams(max_index: int) -> None:
    SNAP_DIR.mkdir(exist_ok=True)
    found = 0
    for i in range(max_index + 1):
        cap = open_cam(i)
        ok, frame = cap.read() if cap.isOpened() else (False, None)
        if ok:
            for _ in range(5):  # let exposure settle
                ok2, f2 = cap.read()
                frame = f2 if ok2 else frame
            path = SNAP_DIR / f"camera_{i}.jpg"
            cv2.imwrite(str(path), frame)
            h, w = frame.shape[:2]
            print(f"camera {i}: {w}x{h}  snapshot -> {path}")
            found += 1
        else:
            print(f"camera {i}: none")
        cap.release()
    if not found:
        print("No cameras opened. Is Camo Studio running with the phone connected? Is Zoom/Teams holding the camera?")
    else:
        print("Open the snapshots to see which index is the iPhone, then run with --index N.")


def preview(index: int) -> None:
    cap = open_cam(index)
    if not cap.isOpened():
        sys.exit(f"Couldn't open camera {index}. Try --list.")
    SNAP_DIR.mkdir(exist_ok=True)
    frames, t0, fps = 0, time.time(), 0.0
    print("Preview running: q = quit, s = save snapshot")
    while True:
        ok, frame = cap.read()
        if not ok:
            print("Frame read failed (feed dropped?)")
            break
        frames += 1
        if time.time() - t0 >= 1.0:
            fps, frames, t0 = frames / (time.time() - t0), 0, time.time()
        h, w = frame.shape[:2]
        cv2.putText(frame, f"camera {index}  {w}x{h}  {fps:.0f} fps", (12, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        cv2.imshow("Sitwise camera test", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q") or cv2.getWindowProperty("Sitwise camera test", cv2.WND_PROP_VISIBLE) < 1:
            break
        if key == ord("s"):
            path = SNAP_DIR / f"snap_{int(time.time())}.jpg"
            cv2.imwrite(str(path), frame)
            print(f"saved {path}")
    cap.release()
    cv2.destroyAllWindows()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", action="store_true", help="probe camera indices and save a snapshot of each")
    p.add_argument("--index", type=int, default=0, help="camera index to preview")
    p.add_argument("--max-index", type=int, default=5)
    p.add_argument("--backend", choices=BACKENDS, help="video backend (try msmf if the feed is black)")
    args = p.parse_args()
    global BACKEND
    if args.backend:
        BACKEND = BACKENDS[args.backend]
    list_cams(args.max_index) if args.list else preview(args.index)


if __name__ == "__main__":
    main()
