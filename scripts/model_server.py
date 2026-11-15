#!/usr/bin/env python3
"""Local model server: runs the posture model on frames from the dashboard's Camera page (the iPhone
through Camo). The dev path for running the real model on a laptop; the iPhone app has its own (stub) model.

  posture_pipeline-main\\.venv\\Scripts\\python.exe -m pip install flask     # once, into the model's Python 3.12 venv
  posture_pipeline-main\\.venv\\Scripts\\python.exe scripts/model_server.py   # listens on http://127.0.0.1:5002

The Camera page finds it automatically (Vite proxies /local-model here) and falls back to the
stub when it isn't running. The model itself sits behind scripts/posture_model.py (the teammate's
MediaPipe pipeline through bridge/engine.py). With any other Python it serves a placeholder and says why.

Privacy: this listens on 127.0.0.1 only, so frames never leave this computer. Each frame is
decoded in memory, passed to the model and dropped; nothing is written to disk or logged. The
hosted API (api/) still accepts no images, by design.
"""
from __future__ import annotations

import argparse
import math
import threading
import time

import cv2
import numpy as np
from flask import Flask, jsonify, request

import posture_model

LABELS = ("GOOD", "SLOUCHING", "AWAY", "UNKNOWN")
MAX_FRAME_BYTES = 4 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_FRAME_BYTES
_lock = threading.Lock()   # one inference at a time; PyTorch models aren't re-entrant by default


def _num(v, lo: float, hi: float, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, f)) if math.isfinite(f) else default


def _clean(out: dict) -> dict:
    """Coerce the model's answer into the PostureSample shape the API accepts."""
    if not isinstance(out, dict):
        raise ValueError("predict() must return a dict")
    label = out.get("label")
    if label not in LABELS:
        raise ValueError(f"predict() label must be one of {', '.join(LABELS)}; got {label!r}")
    features = {}
    for k, v in (out.get("features") or {}).items():
        if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool) and math.isfinite(float(v)):
            features[str(k)] = round(float(v), 4)
    cleaned = {
        "label": label,
        "deviation": round(_num(out.get("deviation"), 0.0, 1e6, 0.0), 4),
        "confidence": round(_num(out.get("confidence"), 0.0, 1.0, 0.0), 4),
        "features": features,
        "stub": bool(posture_model.IS_PLACEHOLDER),
    }
    for key, limit in (("source", 80), ("note", 160)):     # optional short text; kept printable and bounded
        v = out.get(key)
        if isinstance(v, str) and v.strip() and v.isprintable():
            cleaned[key] = v.strip()[:limit]
    return cleaned


def _options():
    """Optional query parameters: ?facing=left|right|auto and ?goal=<torso angle, degrees from vertical>."""
    facing = request.args.get("facing", "auto")
    if facing not in ("left", "right", "auto"):
        raise ValueError("facing must be left, right or auto")
    goal = request.args.get("goal")
    if goal in (None, "", "null"):
        return facing, None
    try:
        g = float(goal)
    except ValueError:
        raise ValueError("goal must be a number")
    if not math.isfinite(g) or abs(g) >= 90:
        raise ValueError("goal must be between -90 and 90 degrees")
    return facing, g


@app.get("/health")
def health():
    return {"ready": True, "name": posture_model.NAME, "placeholder": bool(posture_model.IS_PLACEHOLDER),
            "problem": posture_model.PROBLEM}


@app.post("/analyze")
def analyze():
    """Body: one JPEG or PNG image (the raw bytes, not a form). Query: facing, goal (see _options)."""
    try:
        facing, goal = _options()
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    data = request.get_data(cache=False)
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None
    if frame is None:
        return jsonify(error="Body must be a JPEG or PNG image"), 400
    started = time.perf_counter()
    try:
        with _lock:
            out = _clean(posture_model.predict(frame, facing, goal))
    except Exception as exc:  # show the model's error on the Camera page instead of a bare 500
        app.logger.exception("predict() failed")
        return jsonify(error=f"{type(exc).__name__}: {exc}"), 500
    out["inferenceMs"] = round((time.perf_counter() - started) * 1000, 1)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=5002)
    args = p.parse_args()
    posture_model.load()
    print(f"Model: {posture_model.NAME}" + ("  (PLACEHOLDER: the real model did not load)" if posture_model.IS_PLACEHOLDER else ""))
    app.run(host="127.0.0.1", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
