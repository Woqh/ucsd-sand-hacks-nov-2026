"""Optional local preview window (OpenCV only; the teammate's own overlay needs PyTorch, which the side-angle
path does not). Shows the skeleton, the label and the angles on this machine's screen. Nothing is saved or sent.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

import cv2
import numpy as np

TITLE = "Sitwise model bridge - Q/Esc to quit, L/F = facing left/right"


def make_preview(connections: Sequence[tuple[int, int]]):
    def show(frame: Any, pose: dict[str, Any], result: dict[str, Any], sample: dict[str, Any], facing: str) -> Optional[str]:
        image = frame.copy()
        h, w = image.shape[:2]
        pixels = pose["image_xy"] * np.array([w, h])
        ok = np.isfinite(pixels).all(axis=1) & (pose["confidence"] >= 0.5)
        for a, b in connections:
            if ok[a] and ok[b]:
                cv2.line(image, tuple(pixels[a].astype(int)), tuple(pixels[b].astype(int)), (80, 215, 80), 2)
        for p in pixels[ok]:
            cv2.circle(image, tuple(p.astype(int)), 3, (30, 220, 255), -1)
        f = sample["features"]
        lines = [f"{sample['label']}  (facing {facing})"]
        if "torsoAngle" in f:
            lines.append(f"torso {f['torsoAngle']:+.1f} deg   deviation {sample['deviation']:.2f}")
        if "neckAngle" in f:
            lines.append(f"neck {f['neckAngle']:+.1f} deg")
        for reason in (result.get("abstention_reasons") or [])[:2]:
            lines.append(reason[:70])
        for i, line in enumerate(lines):
            y = 24 + i * 22
            cv2.putText(image, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
            color = {"GOOD": (70, 230, 70), "SLOUCHING": (0, 190, 255)}.get(sample["label"], (255, 255, 255)) if i == 0 else (255, 255, 255)
            cv2.putText(image, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)
        cv2.imshow(TITLE, image)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            return "quit"
        if key == ord("l"):
            return "left"
        if key == ord("f"):
            return "right"
        return None

    return show


def close() -> None:
    cv2.destroyAllWindows()
