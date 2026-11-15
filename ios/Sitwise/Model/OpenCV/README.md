> **Update:** the teammate delivered a **Python 3.12 + MediaPipe** pipeline (`posture_pipeline-main/`), not OpenCV
> code, and it runs on a computer through `bridge/` (see `docs/model-bridge.md`). This iOS seam is **still the stub**.
> To run it on the phone: MediaPipe Tasks for iOS (Pose Landmarker) for the landmarks, a Swift/Obj-C++ port of
> `posture/core.py:measure_pose` and `posture/side_angle.py` (small 2D geometry; the sign and facing rules are in
> `docs/MEASUREMENTS.md`), mapped to `PostureSample` as `bridge/adapter.py` does. Not started.

# OpenCV bridge (teammate-owned, not started)

The real `PostureModel` lives here. Suggested shape (agree before editing the Xcode project):

- `opencv2.xcframework` added to the target.
- An Objective-C++ wrapper (`OpenCVBridge.h/.mm`) exposing a small Obj-C API, imported through a
  bridging header, because Swift can't call OpenCV's C++ directly.
- `OpenCVPostureModel.swift` implementing `PostureModel` (`calibrate()` and `analyze(frame:)`),
  then one line changes in `AppState`: `let model: PostureModel = OpenCVPostureModel()`.

Constraints from the contract:
- Frames are analysed in memory and dropped. Never write them to disk or send them anywhere.
- Output is `PostureSample` / `CalibrationBaseline` (see `Models/Types.swift`). Confirm angle
  conventions and units with the interface owner first, since they define the payload.
- Keypoints aren't built into OpenCV; decide the source (e.g. an ONNX pose model via OpenCV DNN).
