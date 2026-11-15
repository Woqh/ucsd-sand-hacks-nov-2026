"""THE MODEL SEAM (laptop path): put the trained PyTorch model here.

scripts/model_server.py calls `load()` once at startup and `predict(frame)` about once a second
with the current camera frame from the dashboard's Camera page. Only these two functions need to
change; the server, the page and the dashboard stay as they are.

`predict` must return a dict:
    label       "GOOD" | "SLOUCHING" | "AWAY" | "UNKNOWN"   (AWAY = nobody in frame)
    deviation   float >= 0     0 = on the goal posture, ~1 = far off it
    confidence  float 0..1
    features    {name: number}  e.g. neckAngle, torsoAngle, headForwardOffset
                torsoAngle convention (docs/api.md): degrees from vertical, + = leaning forward
The server owns the alert policy (grace period, cooldown); the model just reports what it sees.

Right now this is a PLACEHOLDER: it does not judge posture. It returns UNKNOWN plus a few numbers
measured from the picture, which is enough to prove real frames reach Python.
"""
from __future__ import annotations

import cv2
import numpy as np

NAME = "Placeholder (no posture model yet)"
IS_PLACEHOLDER = True   # set to False once predict() runs the real model


def load() -> None:
    """One-time setup. Example for a PyTorch model:

        import torch
        global _model
        _model = torch.load("models/posture.pt", map_location="cpu", weights_only=False)
        _model.eval()
    """


def predict(frame_bgr: np.ndarray) -> dict:
    """`frame_bgr`: the camera image as OpenCV gives it, uint8, shape (height, width, 3), BGR order,
    longest side at most 640 px. It is the vertical view the Camera page shows (bars trimmed, wide
    pictures cropped to their centre), e.g. 360 x 640.

    Example for a PyTorch image classifier:

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        x = torch.from_numpy(cv2.resize(rgb, (224, 224))).permute(2, 0, 1).float().div(255).unsqueeze(0)
        with torch.no_grad():
            probs = _model(x).softmax(dim=1)[0]
        slouch = float(probs[1])
        return {"label": "SLOUCHING" if slouch > 0.5 else "GOOD", "deviation": slouch,
                "confidence": float(probs.max()), "features": {}}
    """
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    return {
        "label": "UNKNOWN",
        "deviation": 0.0,
        "confidence": 0.0,
        "features": {
            "brightness": round(float(gray.mean()) / 255, 3),
            "frameWidth": w,
            "frameHeight": h,
        },
    }
