# Verification performed

## Side-angle update

The camera's default side-view mode now uses `SideAnglePredictor`, a deterministic three-category sagittal-angle rule. It does not use the frontal checkpoint or inherit its reported accuracy. The full updated suite passed **48 tests**, including 14 new cases covering category thresholds, mirrored anatomical facing, a visible unilateral torso, invalid/multiple people, occlusion, cropping, unknown direction, wrong viewpoints, reference changes and smoothing resets. Existing CNN and geometry tests still pass.

The updated camera loop decoded two fixture-video frames with `--viewpoint side --facing right --checkpoint nonexistent.pt --no-display`, verifying auto-routing without a CNN checkpoint. Both returned angle-rule categories, null probabilities and explicit lateral unobservability. This is a code-path test using the same public fixture, not labeled side-view accuracy. Physical webcam display and keyboard interactions remain untested; their handlers set direction/reference for subsequent frames. The default 10-degree band is an adjustable heuristic, not a source-dataset annotation or clinical criterion.

## Original CNN baseline verification

The pipeline was executed locally on Windows 11, CPython 3.12.14, CPU PyTorch 2.6.0, MediaPipe 0.10.21. The runtime reported Intel64 Family 6 Model 140 Stepping 1, GenuineIntel; a more specific CPU marketing name was unavailable. `artifacts/run/environment.json` and the Windows CPU requirements lock record packages.

- Downloaded the exact user-supplied CSV and checked its published MD5 plus a recorded SHA-256.
- Prepared all 4,794 rows, checked four-class presence per partition, rejected overlaps and cross-partition exact coordinate duplicates, and saved disjoint subject manifests.
- Trained the CNN and shallow baseline on real MultiPosture samples. Early stopping ran 34 epochs and selected epoch 22. Separate calibration participants fitted temperature; untouched test participants produced the saved report.
- Ran **34 tests successfully**. These include known-angle geometry, pixel aspect ratio, explicit roll correction, unknown confidence, anatomical signs, masks, side lateral nulls, participant leakage rejection, train/calibrate/evaluate round trip, checkpoint provenance, invalid/multiple people, cropped and nonfinite image landmarks, and smoothing resets across invalid frames and long gaps. One upstream scikit-learn/SciPy deprecation warning was emitted.
- Loaded the actual frozen Heavy pose model. A blank frame detected no person and returned a valid abstention schema. The public Google pose test image detected one person; unknown/side viewpoints abstained and the side lateral measurement was null.
- The example JSON files are integration fixtures: side/unknown viewpoint arguments were supplied to test gating on the same public image. They are not verified side-camera images or accurate ground-truth-angle examples.
- Exercised the camera demo's video capture/JSON path on eight decoded frames. Physical webcam access and interactive display were not exercised.
- Exercised the media-manifest extraction stage on one image and one explicit video frame; both cached successfully and remained unlabeled (`y=-1`) without invented labels.
- Confirmed that the complete 44-package Windows CPU lock resolves with a clean-environment pip dry run. The executed tests used those recorded versions in a local environment.

The [pose integration benchmark](../artifacts/run/pose_integration_benchmark.json) measured 20 repeats of a 1000×667 static test image after three warmups: pose median **246.2 ms**, pose+geometry+classifier median **254.5 ms**, p95 **275.5 ms**, compute throughput **3.98 frames/s**. This excludes camera/decode/display/startup. It is not a live-camera or posture-accuracy benchmark. Heavy pose inference dominates latency on this CPU; no real-time performance claim is made.

The CNN-only median in the held-out evaluation is **0.380 ms** (p95 **0.737 ms**, batch size one, two PyTorch threads). Its scope excludes pose extraction, feature preparation, softmax and display. Eight-frame video-loop throughput including initialization and file/JSON I/O was **2.45 frames/s**, too short to characterize production throughput.

To repeat the pose timing with a local image:

```powershell
.\.venv\Scripts\python.exe tools/benchmark_pose.py --image path/to/person.jpg
```

The input used here was Google's [pose test JPEG](https://storage.googleapis.com/mediapipe-assets/pose.jpg), SHA-256 `c8a830ed683c0276d713dd5aeda28f415f10cd6291972084a40d0d8b934ed62b`; it is not bundled or used for training. Results will vary with the image and hardware.

No measured side-view recognition accuracy, angle error, occlusion-stratified performance, temporal-CNN benefit or physical webcam frame rate is available. The classifier scores are derived from an approximately frontal, seated source domain. An operator-supplied viewpoint and sitting precondition are not automatic out-of-distribution detectors.
