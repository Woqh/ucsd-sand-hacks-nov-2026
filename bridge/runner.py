"""The capture loop: camera frame -> the teammate's pose + side-angle model -> PostureSample -> /posture/ingest.

Frames stay on this machine. Each frame is analyzed in memory and dropped; only a PostureSample (numbers and a
label, see adapter.validate_outgoing) is sent, about once a second. The engine (model), the camera and the API
client are injected so the loop is testable without a camera, MediaPipe or a network (bridge/test_runner.py).

This is the headless path (a Python process opens the webcam itself). The dashboard's Camera page uses the same
engine through scripts/model_server.py instead.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Optional

from bridge.client import Api, BridgeError
from bridge.engine import Engine

FATAL_CODES = {"unauthorized", "clock_skew", "forbidden"}
MAX_READ_FAILURES = 30


class Bridge:
    def __init__(self, *, capture: Any, engine: Engine, api: Optional[Api], facing: str, camera_roll_deg: float = 0.0,
                 interval_s: float = 1.0, goal_every_s: float = 10.0, fps: float = 5.0, is_file: bool = False,
                 loop_video: bool = False, rewind: Optional[Callable[[], None]] = None,
                 preview: Optional[Callable[..., Optional[str]]] = None,
                 clock: Callable[[], float] = time.monotonic, wall_ms: Callable[[], int] = lambda: int(time.time() * 1000),
                 sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print,
                 session_id: Optional[str] = None):
        self.capture, self.engine, self.api = capture, engine, api
        self.facing, self.roll = facing, camera_roll_deg
        self.interval, self.goal_every, self.fps = interval_s, goal_every_s, fps
        self.is_file, self.loop_video, self.rewind, self.preview = is_file, loop_video, rewind, preview
        self.clock, self.wall_ms, self.sleep, self.log = clock, wall_ms, sleep, log
        self.session_id = session_id or str(uuid.uuid4())
        self.stats = {"frames": 0, "posted": 0, "failed": 0, "abstained": 0}
        self._last_warn = float("-inf")
        self._goal_known = False

    # ------------------------------------------------------------------ goal posture (from the dashboard calibration)
    def refresh_goal(self) -> None:
        if self.api is None:
            return
        try:
            goal = self.api.goal_torso_angle()
        except BridgeError as e:
            self._warn(f"couldn't read your goal posture ({e.message}); keeping {self._goal_text()}")
            return
        if self.engine.set_goal(goal) or not self._goal_known:
            self.log(f"goal posture: {self._goal_text()}")
        self._goal_known = True

    def _goal_text(self) -> str:
        g = self.engine.goal
        return "upright (not calibrated yet: use Calibrate in the dashboard)" if g is None else f"{g:.1f} deg from vertical"

    def _warn(self, message: str) -> None:
        now = self.clock()
        if now - self._last_warn >= 10:                    # don't spam when the network is down
            self.log(f"warning: {message}")
            self._last_warn = now

    # ------------------------------------------------------------------ one frame
    def post(self, sample: dict[str, Any]) -> Optional[dict[str, Any]]:
        if self.api is None:                                # --dry-run
            self.log(f"[dry run] {sample}")
            return None
        try:
            out = self.api.ingest(sample)
        except BridgeError as e:
            if e.status == 401 or e.code in FATAL_CODES:
                raise
            self.stats["failed"] += 1
            self._warn(f"couldn't send a reading ({e.message})")
            return None
        self.stats["posted"] += 1
        return out

    # ------------------------------------------------------------------ the loop
    def run(self, max_frames: Optional[int] = None, max_seconds: Optional[float] = None) -> dict[str, Any]:
        started = self.clock()
        next_post = started
        next_goal = started
        failures = 0
        while True:
            if max_frames is not None and self.stats["frames"] >= max_frames:
                break
            if max_seconds is not None and self.clock() - started >= max_seconds:
                break
            tick = self.clock()
            ok, frame = self.capture.read()
            if not ok:
                failures += 1
                if self.is_file:
                    # A video file simply ended: stop, or start over (giving up if rewinding yields nothing).
                    if not (self.loop_video and self.rewind and failures <= 3):
                        break
                    self.rewind()
                    continue
                if failures >= MAX_READ_FAILURES:
                    raise RuntimeError("The camera stopped delivering frames.")
                self.sleep(0.1)                             # a live camera can drop a frame: try again
                continue
            failures = 0
            # Pick up a recalibration BEFORE judging this frame, so no reading uses a stale reference.
            if self.api is not None and self.clock() >= next_goal:
                self.refresh_goal()
                next_goal = self.clock() + self.goal_every
            pose, result, sample = self.engine.analyze(frame, self.facing, self.roll, session_id=self.session_id, t_ms=self.wall_ms())
            self.stats["frames"] += 1
            if sample["label"] in ("UNKNOWN", "AWAY"):
                self.stats["abstained"] += 1

            now = self.clock()
            server = None
            if now >= next_post:
                server = self.post(sample)
                next_post = now + self.interval
                self._status(sample, result, server)

            if self.preview is not None:
                key = self.preview(frame, pose, result, sample, self.facing)
                if key == "quit":
                    break
                if key in ("left", "right"):
                    self.facing = key
            if self.fps > 0:
                self.sleep(max(0.0, 1.0 / self.fps - (self.clock() - tick)))
        return {**self.stats, "seconds": round(self.clock() - started, 1), "sessionId": self.session_id}

    def _status(self, sample: dict[str, Any], result: dict[str, Any], server: Optional[dict[str, Any]]) -> None:
        f = sample["features"]
        parts = [sample["label"]]
        if "torsoAngle" in f:
            parts.append(f"torso {f['torsoAngle']:+.1f} deg")
        if "neckAngle" in f:
            parts.append(f"neck {f['neckAngle']:+.1f} deg")
        if sample["deviation"] is not None:
            parts.append(f"deviation {sample['deviation']:.2f}")
        if sample["label"] == "UNKNOWN":
            reasons = result.get("abstention_reasons") or []
            parts.append("(" + (reasons[0] if reasons else "can't measure yet") + ")")
        if server:
            parts.append(f"-> server: {server.get('state')}")
            if server.get("alert"):
                parts.append("NUDGE SENT")
        self.log("  ".join(parts))
