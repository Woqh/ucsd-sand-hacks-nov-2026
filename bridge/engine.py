"""One frame in, one PostureSample out: the teammate's model plus our adapter, in one place.

Both ways of feeding the real model use this, so they can't drift apart:
  * `bridge/runner.py`          a Python process reading a webcam itself (`python -m bridge`)
  * `scripts/posture_model.py`  the dashboard's Camera page (iPhone through Camo) -> scripts/model_server.py

The pose extractor and the angle rule are the teammate's (posture_pipeline-main/, imported, never modified).
Frames are analysed in memory and dropped; the only thing this returns that can leave the machine is the
PostureSample dict (see adapter.validate_outgoing).
"""
from __future__ import annotations

import statistics
import sys
from collections import deque
from pathlib import Path
from typing import Any, Optional, Sequence

from bridge import adapter

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PIPELINE = ROOT / "posture_pipeline-main"
DEFAULT_NECK_FRAMES = 5   # the ear-shoulder angle is jumpy frame to frame; the median ignores one-frame spikes


class Engine:
    def __init__(self, extractor: Any, predictor: Any, landmark_names: Sequence[str], source: str,
                 neck_median_frames: int = DEFAULT_NECK_FRAMES):
        self.extractor, self.predictor, self.names, self.source = extractor, predictor, list(landmark_names), source
        self.goal: Optional[float] = None          # the user's calibrated torso angle; None = vertical
        self._neck: deque[float] = deque(maxlen=max(1, neck_median_frames))
        self._facing: Optional[str] = None

    @classmethod
    def load(cls, pipeline_dir: Path | str = DEFAULT_PIPELINE, model_file: Path | str | None = None,
             lean_threshold_deg: float = 10.0, smoothing_window: int = 1, smoothing_max_age_s: float = 0.5,
             neck_median_frames: int = DEFAULT_NECK_FRAMES) -> "Engine":
        """Import the teammate's package and open the pose model. Needs Python 3.12 with mediapipe + OpenCV."""
        pipeline = Path(pipeline_dir).resolve()
        if str(pipeline) not in sys.path:
            sys.path.insert(0, str(pipeline))
        from posture import __version__
        from posture.core import LANDMARK_NAMES
        from posture.pose import PoseExtractor
        from posture.side_angle import SideAnglePredictor
        model = Path(model_file) if model_file else pipeline / "models" / "pose_landmarker_heavy.task"
        if not model.is_file():
            raise FileNotFoundError(f"pose model not found at {model}")
        return cls(PoseExtractor(model), SideAnglePredictor(lean_threshold_deg, 0.0, smoothing_window, smoothing_max_age_s),
                   LANDMARK_NAMES, f"posture-pipeline/side-angle-rule@{__version__}", neck_median_frames)

    def close(self) -> None:
        close = getattr(self.extractor, "close", None)
        if close:
            close()

    # ------------------------------------------------------------------ the user's goal posture
    def set_goal(self, goal: Optional[float]) -> bool:
        """Make the user's calibrated torso angle the model's reference (None = vertical). True if it changed."""
        if goal == self.goal:
            return False
        self.goal = goal
        self.predictor.set_neutral(0.0 if goal is None else float(goal))
        return True

    # ------------------------------------------------------------------ one frame
    def analyze(self, frame_bgr: Any, facing: str, camera_roll_deg: float = 0.0, *,
                session_id: str = "00000000-0000-4000-8000-000000000000", t_ms: int = 0) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """-> (pose, model result, PostureSample). `facing` is left | right | unknown (where the nose points in the image)."""
        pose = self.extractor.extract(frame_bgr)
        result = self.predictor.analyze(pose, "side", facing, camera_roll_deg)
        if facing != self._facing:
            self._neck.clear()
            self._facing = facing
        self._steady_neck(result)
        details = (result.get("measurement_details") or {}).get("sagittal_torso_inclination_deg") or {}
        confidence = adapter.chain_confidence(details.get("landmarks") or [], self.names, pose["confidence"])
        sample = adapter.sample_from_result(result, session_id=session_id, t_ms=t_ms, confidence=confidence, source=self.source)
        return pose, result, sample

    def _steady_neck(self, result: dict[str, Any]) -> None:
        """Replace the per-frame neck angle with the median of the last few frames (the model's value is raw)."""
        m = result.get("measurements")
        raw = m.get("neck_inclination_deg") if m else None
        if not result.get("prediction_valid") or raw is None:
            self._neck.clear()                              # don't carry a stale head position across a gap
            return
        self._neck.append(float(raw))
        m["neck_inclination_deg"] = statistics.median(self._neck)


def note_for(result: dict[str, Any], sample: dict[str, Any]) -> Optional[str]:
    """A short human reason when the model can't give a reading (shown on the Camera page, never stored)."""
    if sample["label"] == "AWAY":
        return "Nobody in view."
    if sample["label"] != "UNKNOWN":
        return None
    reasons = result.get("abstention_reasons") or []
    text = reasons[0] if reasons else "Can't measure your posture yet."
    if "facing" in text.lower():
        text += " Pick which way you face."
    return text[:160]
