# Camera setup: iPhone feed on your laptop, and where the model plugs in

This gets an iPhone's camera showing in the dashboard on your laptop, then runs your trained
(PyTorch) model on that feed. It is the laptop path for developing the model before the iOS app is
built. It takes about 15 minutes the first time.

How the pieces connect:

```
iPhone (Camo app)  ->  Camo Studio on the laptop  ->  shows up as a webcam
   ->  dashboard Camera page (browser)  --one frame per second-->  scripts/model_server.py
   ->  scripts/posture_model.py: predict(frame)   <- YOUR MODEL GOES HERE
   ->  result shown on the page, and (optional) sent to the Live dashboard
```

## What you need

- An iPhone, and a way to prop it upright, side-on to your chair (see [`hardware.md`](hardware.md)).
- A laptop (Windows or Mac) with **Python 3.12+** and **Node 20.19+ or 22.12+**.
- **Chrome or Edge.** Browsers embedded in other apps often block cameras.
- **Camo**, which turns the iPhone into a webcam. The free version is enough:
  - on the iPhone: the **Camo** app from the App Store (by Reincubate);
  - on the laptop: **Camo Studio** from <https://camo.com>.

## 1. Get the iPhone showing in Camo Studio

1. Install Camo on the iPhone and Camo Studio on the laptop, and open both.
2. Connect the phone. A USB cable is the most reliable; Camo Studio also offers Wi-Fi pairing. Follow
   the prompts in Studio, and allow camera access on the phone when it asks.
3. You should now see the phone's picture inside Camo Studio.
4. On the iPhone, turn **orientation lock off** (Control Center), and stand the phone **upright**.
5. **Leave Camo Studio open.** It is what feeds the picture to other apps; if you close it, every
   other app gets a black picture.

You do not need to change the profile, resolution or rotation in Camo Studio. The dashboard turns
the feed into a vertical view by itself (step 4).

## 2. Set up the repo

From the repo root, one time:

```bash
git pull
python -m venv .venv
.venv\Scripts\activate               # macOS/Linux: source .venv/bin/activate   PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt  # includes Flask and OpenCV
cd web
npm install
cd ..
```

Install what your model needs as well, for example `pip install torch`.

## 3. Start three things

Three terminals, from the repo root (activate the venv in the two Python ones):

```bash
# 1. API (port 5001)
python -m flask --app api.index run --debug --port 5001
```

```bash
# 2. model server (port 5002): runs scripts/posture_model.py on each frame
python scripts/model_server.py
```

```bash
# 3. dashboard (port 5173)
cd web
npm run dev
```

## 4. See the feed

1. Open <http://localhost:5173> in Chrome or Edge.
2. First time only: on the **Pair** page click **Create my dashboard**.
3. Go to **Camera** and click **Start camera**. Allow the camera when the browser asks.
4. Check the title above the video. If it names the laptop's own webcam, choose the Camo camera in
   the **Source** dropdown. The choice is remembered.

What you should see:

- **A vertical picture of you**, head to chair base. Webcam feeds are always wide, so the page trims
  the dark bars Camo adds either side of an upright phone, and crops anything still wide to its
  centre. The line above the video says what it did, for example `showing 405×720 of 1280×720`.
- **Model reading** says `Model: Local Python model: Placeholder (no posture model yet)` and shows
  `UNKNOWN` with a brightness and frame size. That is the placeholder proving frames reach Python.
  If it says `Stub (fixed mock data)` instead, the model server was not running when the camera
  started: start it, then **Stop camera** and **Start camera**.

## 5. Plug in your model

Everything model-specific lives in one file: [`scripts/posture_model.py`](../scripts/posture_model.py).
The server, the page and the dashboard do not need to change.

- `load()` runs once when the server starts. Load your weights here.
- `predict(frame_bgr)` runs about once a second. It gets the current picture and returns a dict.

**What `predict` receives:** a NumPy array exactly as OpenCV gives it: `uint8`, shape
`(height, width, 3)`, **BGR** channel order (use `cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)` for
RGB). It is the same vertical picture the page shows, with the longest side at most 640 px, so
typically about 360 wide by 640 tall.

**What `predict` must return:**

| Key | Value |
|---|---|
| `label` | `"GOOD"`, `"SLOUCHING"`, `"AWAY"` (nobody in frame) or `"UNKNOWN"` |
| `deviation` | number, 0 = on the goal posture, about 1 = far off it |
| `confidence` | number from 0 to 1 |
| `features` | dict of numbers to show and store, e.g. `neckAngle`, `torsoAngle`, `headForwardOffset` (may be empty) |

`torsoAngle` has a fixed meaning because calibration depends on it: degrees from vertical, positive =
leaning forward (see [`api.md`](api.md)). The model only reports what it sees; the server decides
when to alert (grace period, cooldown, quiet hours).

When your model is in:

1. Set `IS_PLACEHOLDER = False` and give `NAME` your model's name (both at the top of the file).
2. Restart `python scripts/model_server.py`.
3. On the Camera page, **Stop camera** then **Start camera**.

The page then shows your label, confidence, features and how long each prediction took. If
`predict` raises, the error text appears on the page under **Model reading**, and the full traceback
is in the model server's terminal.

The file's docstrings contain a short PyTorch example of both functions. Keep large weight files out
of git unless the team agrees otherwise.

## 6. Drive the dashboard from the camera (optional)

On the Camera page, turn on **Send readings to the dashboard**. The browser tab then acts as the
phone: each reading is posted to the API, so **Live**, alerts and **Analytics** run off your real
posture. Turning it on for the first time replaces any phone that is currently paired.

## Check the camera without the browser

```bash
python scripts/camera_test.py --list
python scripts/camera_test.py --index 1
```

`--list` saves one snapshot per camera into `scripts/_camera_snapshots/` (ignored by git) so you can
see which number is the iPhone; `--index N` opens a live preview (`q` quits). Camo may show black
here while a browser tab is using it, so stop the camera on the page first.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Black picture | Camo Studio is closed, the phone disconnected, or the Camo app on the phone is not open. Reopen both. |
| "Camera permission was denied" | Click the camera icon in the browser's address bar, allow it for `localhost`, and try again. Use Chrome or Edge directly, not a browser inside another app. |
| The picture is the laptop's own webcam | Pick the Camo camera in **Source**. |
| "The camera is in use by another app" | Close Zoom, Teams, or a running `camera_test.py` preview. |
| Model reading says `Stub (fixed mock data)` | The model server was not running when the camera started. Start it, then stop and start the camera. |
| "Can't reach the local model server" | `python scripts/model_server.py` stopped or crashed. Check its terminal. |
| The vertical view cuts into the picture, or shows black | Note the `showing … of …` line above the video and how the picture looks in Camo Studio, and tell whoever maintains `web/src/pages/Camera.tsx` (`findPicture`). |
| You do not fit head to chair base | Move the phone further back. The page can only show what the phone sees. |
| `flask` is not recognised | Use `python -m flask …` as above, with the venv active. |

## Privacy

Frames go from the browser tab to the model server on the same computer (`127.0.0.1`), are analysed
in memory and dropped. Nothing is saved or uploaded, and the hosted API accepts no images. Only the
numbers `predict` returns leave the tab, and only when **Send readings to the dashboard** is on.
