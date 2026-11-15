# MultiPosture posture pipeline

A runnable research baseline: frozen MediaPipe Heavy → masked, hip-centered world coordinates → anatomical-chain CNN → calibrated scores and abstention. A separate image-coordinate geometry layer returns projected angles with validity reasons.

**Side-camera mode now labels upright, leaning forward and leaning backward using projected torso angles.** It automatically selects a deterministic angle rule for `--viewpoint side`; the trained CNN still only accepts frontal views. Sideways leaning is explicitly **UNOBSERVABLE**, and an upright result describes only the visible sagittal projection. The angle rule is a configurable heuristic, not a trained or validated side-view model. The original frontal CNN results below do not measure its accuracy.

For the quickest local start, double-click `Start-Side-Webcam.cmd`. In the preview press **L** if your nose points toward image left, or **F** if it points toward image right. With the camera level and your chosen neutral torso posture visible, press **C** to set that angle as the reference; **R** resets the reference to vertical. Press **Q** or **Esc** to exit. Reference capture does not determine whether a posture is healthy and is separate from camera-roll calibration.

Default angle categories: within **±10 degrees** of the reference is `upright` (green); more than +10 degrees anatomically forward is `leaning_forward` (amber); less than -10 degrees is `leaning_back` (amber). Configure `--lean-threshold-deg` and `--neutral-angle-deg` explicitly if needed. No class probabilities are fabricated: angle-rule output uses `class_probabilities: null`, `classification_scope: sagittal_only`, and `lateral_posture: unobservable`. Missing visible shoulder/hip, unknown facing, multiple people, or a wrong viewpoint still cause abstention. A reliable visible shoulder/hip pair suffices; the far side may be occluded.

## Included and verified

- Original checksum-verified MultiPosture CSV, source metadata, processed feature cache, participant splits and label mapping.
- Trained 64,716-parameter CNN, logistic-regression baseline, training history, separate calibration fit, held-out evaluation, confusion matrix and plot.
- Frozen MediaPipe Heavy model, image/video feature extraction, webcam skeleton overlay, projected angles, quality gates, JSON output and bounded temporal smoothing.
- Tests covering geometry, missing data, leakage, training/checkpoint round trip, unsupported views, off-image torso joints and smoothing resets.

The held-out test contains **810 rows from two unseen people**. CNN macro F1 is **0.8807**, balanced accuracy **0.8873**, and accuracy **0.8901**. Logistic-regression macro F1 is **0.7916**. These are one participant-separated split, not a reproduction of the paper's LOSO experiment or evidence of side-view accuracy. See [measured results](docs/RESULTS.md) and [machine-readable evaluation](artifacts/run/evaluation_test.json).

All **48 tests passed**, including the side-angle update. Frozen-pose extraction, manifest caching and the video capture path were exercised. The original CNN path took 254.5 ms median on a repeated static image (3.98 compute frames/s); this is not a side-rule or physical-webcam performance claim. [Verification and timing details](docs/VERIFICATION.md).

## Dataset audit and task

The exact release is [MultiPosture v1, Zenodo 14230872](https://zenodo.org/records/14230872), licensed **CC BY 4.0**. It contains one CSV and no images/videos. Direct inspection finds **4,794 rows and all 33 MediaPipe landmarks**, despite the record describing 4,800 frames and 11 selected joints. There are 13 participant IDs, but no visibility, presence, video, session, timestamp, per-row viewpoint, occlusion or ground-truth-angle columns. [Full audit and attribution](docs/DATASET_AUDIT.md).

| Source label | Output | Meaning | Rows |
|---|---|---|---:|
| TUP | upright | Upright trunk, as manually labeled in the source | 1,615 |
| TLF | leaning_forward | Trunk leans in the person's anatomical forward direction | 1,897 |
| TLB | leaning_back | Trunk leans in the person's anatomical backward direction | 442 |
| TLL, TLR | leaning_side | Trunk leans anatomically left or right, combined | 840 |

The source supplies categorical annotations, not angle thresholds. We retain them without relabeling by heuristic angles. Lower-body labels are neither targets nor classifier inputs. A new annotation protocol must define thresholds, mixed postures and ambiguous frames before collecting side-view data; do not invent those labels from this CSV.

## Run on Windows (Python 3.12)

Open PowerShell in this folder. The delivered data, models and results can be inspected immediately. Create an environment to rerun code:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.windows-cpu.txt
.\.venv\Scripts\python.exe -m posture --help
```

The lock records the tested Windows CPU dependency set. `requirements.txt` lists the principal pins for a fresh compatible environment. A different OS or CUDA build needs its own resolved lock and verification; the saved checkpoint can be loaded on CPU.

Run each stage from this folder, in order:

```powershell
# Already included; these commands reproduce the verified downloads.
.\.venv\Scripts\python.exe -m posture download
.\.venv\Scripts\python.exe -m posture download-model

.\.venv\Scripts\python.exe -m posture audit
.\.venv\Scripts\python.exe -m posture prepare --seed 42
.\.venv\Scripts\python.exe -m posture train --config configs/train.json
.\.venv\Scripts\python.exe -m posture evaluate
.\.venv\Scripts\python.exe tools/make_report.py
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Training uses subjects 2, 3, 5, 6, 7, 9, 12; validation 4, 10; calibration 8, 11; test 1, 13. It fits class weights and the shallow model's scaler on training only. Validation macro F1 selects a checkpoint with early stopping. Separate calibration people fit one temperature. Test people are not used to choose weights, epochs or temperature. All frames from any participant remain together, enclosing their unidentified sessions. Explicit subject partitions can be passed as `prepare --subject-split configs/subject_split.json`; the saved default is `data/prepared/subject_split.json`.

The seed, resolved configuration, source/cache/split hashes and label order are saved. Evaluation rejects changed feature caches or partitions. Reproducibility means the same recorded pipeline and inputs; floating-point results across hardware/library builds need not be bit-identical.

## Camera and video demo

The person must be seated, visible in the frame, and alone. Viewpoint is operator-supplied and must describe the actual camera. Sitting is an operator-checked deployment precondition, not an automatically validated state.

```powershell
# Side view: three categories from angles; lateral leaning stays unobservable.
.\.venv\Scripts\python.exe -m posture webcam --source 0 --viewpoint side --facing right --jsonl live.jsonl --report live-benchmark.json

# Approximate training domain: frontal, seated person.
.\.venv\Scripts\python.exe -m posture webcam --source 0 --viewpoint front --threshold 0.6 --smoothing-window 3 --smoothing-max-age-ms 300

# Process a recording without opening a window.
.\.venv\Scripts\python.exe -m posture webcam --source path/to/video.mp4 --viewpoint side --no-display --jsonl frames.jsonl --report timing.json
```

Press **Q** or **Esc** to stop. Skeleton, accepted category, available angles and warnings appear on the frame. No camera is opened by importing the package or running tests. Physical webcam operation was not tested in this environment; the same capture loop was exercised with a decoded video fixture.

`--facing right` means the person's anatomical forward direction points toward image right before any display mirroring; left means image left. The demo does not mirror frames. Without an override, sagittal signs require high-confidence agreement between nose/ear and both foot-direction cues. A head turn or ambiguous feet cause null sagittal measurements. Classifier coordinates are not yaw-rotated or mirrored: arbitrary yaw generalization has not been established. Explicit camera roll is compensated in image measurements and estimated-world x/y before inference. That world-space compensation assumes approximate camera-aligned axes and does not calibrate monocular 3D.

Abstention sets top-level `posture_category` to null. Reasons include missing/multiple people, missing or out-of-frame torso joints, low pose confidence, too few usable joints, insufficient classifier probability, or unsupported viewpoint. Abstention is not a fifth class. Raw scores can be present during abstention and must not be interpreted as an accepted result. Pose confidence is the mean of `min(visibility,presence)` for the two shoulders and two hips, with unavailable required joints contributing zero; it is not classifier confidence.

Optional smoothing averages accepted angles in side mode, or probabilities in CNN mode, capped by both frame count and history age. Invalid frames reset history. Side-mode direction/reference changes also reset it. Gaps longer than the history limit discard stale results. Raw and smoothed outputs are both exposed; the timestamp span / 2 is reported as an approximate smoothing delay, not a guaranteed response time. Default CLI smoothing is off (window 1); the side-view launcher uses window 3. Use `--method cnn` to explicitly select the original trained baseline (which still abstains on side views).

## Output and measurements

Every result contains `posture_category`, `class_probabilities`, `prediction_valid`, `abstention_reasons`, `raw_prediction`, `smoothed_prediction`, `measurements`, `measurement_details`, `quality`, and timing. Measurements have numeric degree values or null, with a separate reason, landmarks, formula, sign and validity definition. See [measurement reference](docs/MEASUREMENTS.md) and [actual side-abstention output](artifacts/run/example_side_abstention.json).

- Torso inclination is the signed 2D shoulder-to-hip vector relative to image vertical; image-right is positive.
- Sagittal inclination is positive anatomically forward only in an adequate side view with reliable facing.
- Neck inclination uses an ear-to-shoulder proxy; hip and knee flexion use projected bend proxies. They are not clinical joint measurements.
- Shoulder/hip alignment and lateral inclination require sufficient frontal evidence. Side-view lateral inclination is null.

MediaPipe estimated-world coordinates feed the classifier only. They are monocular estimates, not calibrated depth or physical ground truth. Image measurement calculations use pixel aspect correction and explicit camera-roll correction. Without roll calibration, a level/upright camera is assumed. Perspective and occlusion still affect all projected angles. Dataset angle error cannot be measured because angle ground truth and original images are absent.

## Extract new labeled media

Create a CSV with columns `id,path,subject,session,video_id,frame_index,label,viewpoint,facing,camera_roll_deg`. Paths are relative to the manifest. For images, leave video and frame fields blank. For videos, specify an explicit zero-based frame index and a video ID. Labels must be manually supplied canonical names; an empty label is recorded as unlabeled, not guessed.

```powershell
.\.venv\Scripts\python.exe -m posture extract --manifest path/to/manifest.csv --out data/new_capture
```

The extractor caches normalized coordinates, real confidence, confidence-known flags, missing-joint masks, IDs and source/model hashes. `IMAGE` mode is stateless so extraction does not carry temporal state across people or partitions. This collection command does not grant new viewpoints validation status. Training/evaluation currently target the audited MultiPosture domain; adapting to new capture data requires a reviewed subject/session/video split, confidence-feature policy and separate target-view test set.

## Design choices and limitations

MediaPipe Tasks Heavy is the practical default: built-in person detection, 33 landmarks including feet, visibility/presence scores, CPU operation and an estimated-world output compatible in kind with the released CSV. Exact parity with the source extractor cannot be established because its version and original recordings are unavailable. [Official MediaPipe guide](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker).

RTMPose is a useful alternative for configurable detectors, pose backbones and deployment formats, but common body checkpoints have a different landmark schema and would need adaptation and fresh validation. Its accuracy/speed tradeoff depends on the chosen model, detector, hardware and input resolution; no speed superiority is claimed here. [RTMPose project](https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose). MediaPipe and MMPose source code use Apache 2.0; review chosen model and training-data terms separately. [Third-party notices](THIRD_PARTY.md).

The CNN uses four anatomical chains and shared 1D convolutions, then retains each chain's identity in a dense head. It never convolves across artificial chain boundaries. All 33 joints are cached; 15 distinct joints participate in these chains. Confidence and masks are explicit channels. Since source confidence is absent, classifier confidence channels stay unknown at inference for this checkpoint; actual scores still gate masking and abstention. Small scale jitter and non-torso joint dropout augment training without body rotation, label-changing flips or synthetic class labels. [Architecture and training details](docs/TRAINING.md).

Temperature scaling **worsened held-out calibration**, despite improving its fitting partition. The saved temperature is retained to avoid tuning on test results. Probability values are scores with measured calibration limitations, not guarantees of correctness. Full pose-quality coverage cannot be evaluated on this confidence-free CSV; reported coverage uses classifier thresholds alone.

No temporal CNN was trained: row order does not establish sequences or frame timing. No side-view, occlusion-stratified or angle-accuracy scores are invented. To complete a validated side-camera system, collect seated side/oblique footage with subject/session/video IDs, explicit anatomical labels, visibility/occlusion and independent viewpoint annotations; evaluate upright-versus-lateral errors on held-out people. For physically unobservable lateral lean, an additional view is necessary. Human labeling or independently measured ground-truth angles are required to assess geometry accuracy.

## Project layout

`posture/data.py` handles verified data loading and splits; `core.py` handles normalization and measurements; `pose.py` handles frozen pose extraction; `learning.py` handles CNN/baseline training, calibration and evaluation; `inference.py` handles quality gates, smoothing and overlays. `configs/` holds reproducible settings; `data/` holds original/prepared inputs; `models/` holds the frozen extractor; `artifacts/run/` holds learned checkpoints and measured outputs; `docs/` holds the audit, formulas and reports.
