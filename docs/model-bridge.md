# The real model: webcam bridge

The teammate's pipeline (`posture_pipeline-main/`, from their repo) is **Python 3.12 + MediaPipe**, not iOS code.
So it can't run inside the iPhone app today. It runs on the computer instead, through `bridge/engine.py`, which turns
its output into Sitwise `PostureSample`s. Two ways to feed it, both ending at `/api/posture/ingest` exactly like the
phone would, so the dashboard, state machine, nudges, analytics and Coach all work on the real numbers:

1. **The iPhone through Camo, in the dashboard (the iPhone side).** The **Camera** page shows the phone's picture, sends
   a frame a second to `scripts/model_server.py` on `127.0.0.1`, which runs the model, and the page posts the result.
   Calibrate and choose your facing on that page. Guide: [`camera-setup.md`](camera-setup.md).
2. **A webcam read by Python (`python -m bridge`).** Headless, no browser; described below.

**Privacy:** frames are analysed in memory on that computer and dropped. Only a label and a few angles leave it
(`bridge/adapter.py:validate_outgoing` refuses to send anything else, and a test enforces it).

## What the model is (and isn't)

From `posture_pipeline-main/README.md`, in short:

- MediaPipe **Pose Landmarker Heavy** finds the person; geometry in `posture/core.py` measures 2D projected angles.
- For a **side camera** (our mount) it labels *upright / leaning_forward / leaning_back* with a **deterministic angle
  rule** (default band +/-10 degrees around a reference). **This is a heuristic, not a trained or validated side-view
  model**; there is no side-view accuracy figure.
- The trained CNN (macro F1 0.88 on two held-out people) is for **frontal** views only and abstains on side views. The
  bridge does not use it, so PyTorch is not needed to run the bridge.
- Sideways lean is **unobservable** from a side camera, and "upright" only describes the visible sagittal projection.
- It abstains (instead of guessing) when there is no person, more than one person, the torso is out of frame or low
  confidence, or the facing direction is unknown.

## Set up (Windows)

The model needs **Python 3.12 exactly** (`requires-python = ">=3.12,<3.13"`; MediaPipe 0.10.21 has no 3.14 build).
Keep it separate from the API's Python. From the repo root:

```powershell
py -3.12 -m venv posture_pipeline-main\.venv        # install 3.12 first if `py -0` doesn't list it (winget install Python.Python.3.12)
posture_pipeline-main\.venv\Scripts\python.exe -m pip install numpy==1.26.4 mediapipe==0.10.21 opencv-contrib-python==4.11.0.86
```

That is all the bridge needs (about 700 MB on disk: MediaPipe pulls in JAX and Matplotlib). The teammate's full lock file (`requirements-lock.windows-cpu.txt`, adds
PyTorch etc.) is only for retraining or the frontal CNN. The weights (`models/pose_landmarker_heavy.task`) are already in
the folder. Their launcher `Start-Side-Webcam.cmd` also uses this `.venv`.

## Run it (headless bridge)

For the Camera page route use [`camera-setup.md`](camera-setup.md): it needs the same Python 3.12 venv plus `flask`
(`pip install flask` into it) and `posture_pipeline-main\.venv\Scripts\python.exe scripts/model_server.py`.

1. Start the API and dashboard as in the README quick start. Open the dashboard's **Pair** page and create a pairing code.
2. Mount the camera on the **side** of your chair so it sees your torso in profile (`docs/hardware.md`).
3. From the repo root:

```powershell
posture_pipeline-main\.venv\Scripts\python.exe -m bridge --facing right --code ABC234 --display
```

- **`--facing` is required**: `right` if your nose points toward the **right** of the camera image when you sit,
  `left` if toward the left (`auto` lets the model infer it from your face and feet, which needs your feet in view).
  A wrong value flips forward and backward.
- `--code` pairs once and remembers the token in `~/.sitwise/bridge.json` (outside the repo). **Pairing replaces any
  phone paired before**: one device per account. Later runs need no `--code`.
- `--display` opens a local preview (skeleton and angles; Q/Esc quits, L/F set facing). Nothing is saved or sent from it.
- `--base https://<project>.vercel.app` (or `SITWISE_BASE`) points it at a deployment; default is `http://127.0.0.1:5001`.
- `--source 1` picks another camera; `--source clip.mp4` analyses a video file (`--loop-video` repeats it);
  `--dry-run` prints readings and sends nothing.
- `--interval` (1 s), `--fps` (max frames analysed per second, 5), `--smoothing-window` (3), `--lean-threshold-deg` (10),
  `--camera-roll-deg` (0). `python -m bridge --help` lists everything.

**Calibrate from the dashboard as usual** (Calibrate tab): while the bridge streams, the 10-second countdown averages
what the model measured and the server judges it (below). The bridge reads the saved goal every ~10 s, so a new
calibration takes effect without restarting it. Until you calibrate, "goal" is vertical (0 degrees).

## What gets sent (the mapping)

| PostureSample field | From the model |
|---|---|
| `label` | upright -> `GOOD`; leaning_forward / leaning_back -> `SLOUCHING`; nobody in view -> `AWAY`; anything it can't judge -> `UNKNOWN` |
| `features.torsoAngle` | smoothed `sagittal_torso_inclination_deg`: degrees from vertical, **+ anatomical forward** (the convention the calibration gate already uses) |
| `features.neckAngle` | `neck_inclination_deg` (ear to shoulder, median of the last 5 frames), signed **+ forward** using `--facing` |
| `deviation` | `abs(torsoAngle - your goal torsoAngle) / 25`, clamped 0 to 1 |
| `confidence` | the lowest visibility/presence score among the landmarks the angle used (`1.0` for AWAY, `0.0` for UNKNOWN, which the server ignores) |
| `source` | `posture-pipeline/side-angle-rule@<version>` (shown on the Live page) |
| `headForwardOffset` | **not sent**: the model doesn't produce it |

**Why 25 degrees full scale.** The server decides good/bad from `deviation` with the user's sensitivity (`bad >= 0.6 -
0.4 x sensitivity`). With 25 degrees = 1.0 that is **10 degrees at balanced sensitivity (the model's own default band)**,
5 degrees when strict and 15 when forgiving, so the Sensitivity slider keeps meaning something. It is one constant
(`bridge/adapter.py:FULL_SCALE_DEG`). Leaning *back* past the band also counts as slouching, matching the calibration
gate's two-sided range (and its known tension with sources that call a slight recline comfortable).

**Calibration from the live feed.** The server keeps the last ~30 s of readings per session. `POST /model/calibrate/finish`,
when the model has streamed within 15 s, averages the last 10 s (`api/core/calibration_feed.py`) and refuses if it
couldn't see you for most of it, or you moved (torso standard deviation over 3 degrees, a product parameter). The
back-angle gate (within 10 degrees of upright, either way) is applied on top, here and again by `PUT /calibration`.
With no live feed it falls back to the old stub, so the simulator and demo still work. `GET /model/health` reports
`live` and `stub` accordingly.

## Limits to say out loud

- **Side view only**, one person, seated, facing set by hand. Camera tilt (roll) is assumed zero unless you pass it.
- **Not validated on real side-view footage** by us: the integration was verified with MediaPipe on a public test image
  (rotating it to emulate lean) and with synthetic poses, not with a physical webcam. The angle thresholds are the
  model's heuristics, not health criteria.
- The **iPhone app still uses its stub model.** Running the model on the phone means porting it (MediaPipe Tasks for iOS
  plus `posture/core.py:measure_pose` and the angle rule, which is small geometry) behind the `PostureModel` protocol.
  Not done.
- Throughput on CPU is a few to about 10 frames per second (the teammate measured about 4 on a repeated image; a dry run here managed about 11 on video); we post one reading per second. A blocked network call pauses capture
  (timeout 4 s), so the camera buffer can lag briefly.

## Layout and licences

`posture_pipeline-main/` is the teammate's repo, **unmodified** (their code, 31 MB model, dataset, results, docs). The
bridge imports it and adds nothing to it. `bridge/` is ours: `adapter.py` (pure mapping + the privacy check), `engine.py`
(frame in, sample out: the model plus the adapter, shared by both routes), `client.py` (stdlib HTTP), `runner.py` (the
webcam loop), `cli.py` (`python -m bridge`), `preview.py` (optional window). The Camera page's route adds
`scripts/model_server.py` and `scripts/posture_model.py` (the seam) on top of the same engine. Dataset (CC BY 4.0,
attribution required) and MediaPipe notices are in `posture_pipeline-main/THIRD_PARTY.md`: keep them. The folder adds
about 41 MB to the repo and is excluded from the Vercel function (`vercel.json`).

## Tests

- `pytest api bridge` (API's Python): mapping, privacy check, client against a real local server, the loop with a fake
  camera, calibration from the live feed on both stores.
- `posture_pipeline-main\.venv\Scripts\python.exe -m pytest bridge/test_real_model.py bridge/test_model_server.py`: the
  adapter against the real `SideAnglePredictor`, and the Camera page's model server over HTTP (skipped in the API's
  Python, which has no numpy, OpenCV or the model).
- The teammate's own suite, from inside their folder: `.venv\Scripts\python.exe -m pytest tests/test_core.py tests/test_data.py tests/test_side_angle.py`
  (32 pass with the bridge's packages; `test_inference.py` and `test_learning.py` need PyTorch etc. from their full lock).
