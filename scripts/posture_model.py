r"""THE MODEL SEAM (laptop path): the model behind the dashboard's Camera page.

scripts/model_server.py calls `load()` once at startup and `predict(frame, facing, goal)` about once a second
with the current camera frame (the iPhone through Camo). `predict` runs the teammate's pipeline
(posture_pipeline-main/: MediaPipe pose landmarks + the side-view angle rule) through `bridge.engine`, the same
code the headless webcam bridge uses, and returns a PostureSample-shaped dict that the Camera page posts to
/posture/ingest. See docs/model-bridge.md for what the model is, and is not.

It needs the model's Python 3.12 environment (mediapipe 0.10.21 has no 3.14 build):

    posture_pipeline-main\.venv\Scripts\python.exe scripts/model_server.py

If the pipeline can't be loaded (wrong Python, mediapipe missing) this falls back to the PLACEHOLDER below, loudly:
`IS_PLACEHOLDER` stays True, the Camera page shows "placeholder", and the reason is in the server's terminal and at
/health. Nothing is written to disk; frames are analysed in memory and dropped.

`predict` returns a dict:
    label       "GOOD" | "SLOUCHING" | "AWAY" | "UNKNOWN"   (AWAY = nobody in frame)
    deviation   float >= 0     0 = on the user's goal posture, ~1 = 25 degrees off it
    confidence  float 0..1
    features    {torsoAngle, neckAngle}   torsoAngle: degrees from vertical, + = leaning forward (docs/api.md)
    source      which model measured it (kept with the reading)
    note        a short reason when it can't give a reading (shown on the page, never stored)
The server owns the alert policy (grace period, cooldown); the model just reports what it sees.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))          # so `bridge` imports when run as `python scripts/model_server.py`

NAME = "Placeholder (the posture model did not load)"
IS_PLACEHOLDER = True   # False once the real pipeline is loaded
PROBLEM: Optional[str] = None
_engine = None


def load() -> None:
    """One-time setup: open the teammate's MediaPipe pose model. Falls back to the placeholder, loudly."""
    global NAME, IS_PLACEHOLDER, PROBLEM, _engine
    try:
        from bridge.engine import Engine
        _engine = Engine.load(smoothing_window=1, neck_median_frames=3)   # ~1 frame/s: a short median is enough
    except Exception as exc:   # ImportError (wrong Python / no mediapipe), missing weights, ...
        PROBLEM = f"{type(exc).__name__}: {exc}"
        print(f"WARNING: the posture model did not load ({PROBLEM}).\n"
              f"  Run this with the model's Python 3.12 environment: "
              f"posture_pipeline-main\\.venv\\Scripts\\python.exe scripts/model_server.py\n"
              f"  Serving the PLACEHOLDER instead (it does not judge posture).", file=sys.stderr)
        return
    NAME = f"Side-angle rule on MediaPipe ({_engine.source})"
    IS_PLACEHOLDER = False
    PROBLEM = None


def predict(frame_bgr: np.ndarray, facing: str = "auto", goal: Optional[float] = None) -> dict:
    """`frame_bgr`: the camera image as OpenCV gives it, uint8, (height, width, 3), BGR, longest side at most
    640 px: the vertical view the Camera page shows (e.g. 360 x 640). `facing`: where the person's nose points in
    that picture ("left" | "right"), or "auto" to let the model guess from face and feet. `goal`: the user's
    calibrated torso angle in degrees (None = not calibrated, so vertical)."""
    if _engine is None:
        return _placeholder(frame_bgr)
    from bridge.engine import note_for
    _engine.set_goal(goal)
    _, result, sample = _engine.analyze(frame_bgr, "unknown" if facing == "auto" else facing)
    return {"label": sample["label"], "deviation": sample["deviation"] or 0.0, "confidence": sample["confidence"],
            "features": sample["features"], "source": sample["source"], "note": note_for(result, sample)}


def _placeholder(frame_bgr: np.ndarray) -> dict:
    """Proves frames reach Python; does not judge posture."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    return {
        "label": "UNKNOWN",
        "deviation": 0.0,
        "confidence": 0.0,
        "features": {"brightness": round(float(gray.mean()) / 255, 3), "frameWidth": w, "frameHeight": h},
        "note": "Placeholder model: the posture model did not load (see the model server's terminal).",
    }
