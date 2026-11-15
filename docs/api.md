# API notes

Machine-readable contract: [`openapi.yaml`](openapi.yaml). Mirrors: `web/src/types.ts`,
`ios/Sitwise/Models/Types.swift`. Keep all four in sync in the same change.

All routes are under `/api`, JSON in/out, `"schema": 1`. Errors are `{"error": {"code", "message"}}`.
Auth is `Authorization: Bearer <token>`; tokens are random secrets stored only as SHA-256 hashes.
Every route needs a token except `/pair/*`, `/health` and `/push/web/public-key` (see "Deviations").

## Pairing

1. Dashboard `POST /pair/create` -> `{dashboardToken, pairingCode, expiresAt}` (anonymous user; code lives 10 min).
2. Phone `POST /pair/claim {code}` -> `{deviceToken}`. One-time; a new claim replaces the previous phone.

## Ingest and the state machine

The phone posts a `PostureSample` about once a second to `POST /posture/ingest`. The server runs the
pure function `step(state, sample, config)` (`api/core/state_machine.py`), persists the new state on
the session row, stores **transition events** (not raw samples), fires alerts, and returns
`{state, stateSince, serverTime, alert}`.

```
AWAY -> GOOD <-(recovered, 3 s)- DEVIATING --(>= user threshold)--> SLOUCHING -> alert
```

### For the model teammate: how a sample is read

The model owns `label`, `deviation`, `confidence`; the **server owns the policy**:

| Sample | Treated as |
|---|---|
| `confidence < 0.5` or `label = UNKNOWN` | ignored entirely (not even a heartbeat) |
| `label = AWAY` | away (debounced 5 s before AWAY) |
| otherwise | decided by `deviation` against the **user's sensitivity**: `>= bad` is off-posture, `<= bad x 0.75` is good, in between is a dead-band that changes nothing. `bad = 0.6 - 0.4 x sensitivity` (0.40 at the default 0.5) |
| `deviation` missing | falls back to `label` |

So `deviation` must be on a roughly 0 (goal posture) to ~1 (clearly slouched) scale, and **the user's
sensitivity can override `label`**. If you'd rather the model's own label always win, that's a
contract change: flag it.

Other behaviour worth knowing:
- Off-posture must last the user's **slouch threshold** (default 30 s) before it becomes SLOUCHING; brief good blips (< 3 s) don't reset the timer.
- **COOLDOWN is not a separate state** (deviation from the original diagram): it is "an alert was sent less than `cooldownSec` ago", so slouch time isn't split in two. If they're still slouching after the cooldown there's a gentle escalation (levels 2 and 3), then it stops until they recover.
- No usable sample for 20 s => the old state is closed as AWAY at the last time we saw them; a new `sessionId` closes the previous session the same way.
- `t` is the phone clock. Out-of-order samples are clamped; `t` more than 1 h from server time is rejected (`clock_skew`).
- Alerts respect quiet hours and the per-channel toggles. Push failures never fail ingest; `alert.channels` reports what happened (`skipped: apns_not_configured`, etc.).

### The real model (webcam bridge)

The teammate's model is a Python/MediaPipe pipeline. It runs next to a camera and posts `PostureSample`s through
`bridge/` (guide: [`model-bridge.md`](model-bridge.md)), so everything above applies unchanged. How its output
fills the fields:

- `label`: upright -> `GOOD`; leaning_forward / leaning_back -> `SLOUCHING`; no person -> `AWAY` (confidence 1.0); anything it cannot judge -> `UNKNOWN` (confidence 0.0, so the server ignores it).
- `features.torsoAngle`: the model's `sagittal_torso_inclination_deg` (degrees from vertical, **+ anatomical forward**). `features.neckAngle`: its ear-to-shoulder inclination signed forward with the camera-facing direction. `headForwardOffset` is **not produced**, so it is omitted (all feature keys are optional).
- `deviation = abs(torsoAngle - the user's goal torsoAngle) / 25`, clamped to 0..1, so the user's Sensitivity setting maps to degrees: about 15 deg forgiving, 10 deg balanced (the model's own default band), 5 deg strict.
- `confidence`: the lowest visibility score among the landmarks the angle used.
- Optional `source` (string, at most 80 printable characters): which model produced the reading, kept with the latest sample and returned in `GET /status` as `sample.source`. Anything invalid is ignored, not an error.

**Live-feed calibration.** The session keeps its last ~30 s of readings (`state.recent`, never returned by the API). While a model has streamed within 15 s, `POST /model/calibrate/finish` averages the last 10 s (`api/core/calibration_feed.py`) and returns `{goal, tolerance, capturedAt, accepted, issues, stub: false, source}`: refused if the person was seen clearly in under 60% of readings (or fewer than 5), or the torso angle varied by more than 3 degrees (standard deviation); the back-angle gate is applied on top. With no live feed it returns the stub baseline (`stub: true`). `GET /model/health` returns `{ready, stub, live, source}`: `stub` is false and `live` true only while a model is streaming. `?force=bad` always returns the stub rejection.

## Calibration gate: only a good posture is accepted

The goal posture is what every later nudge is measured against, so a slouched "goal" would silently
break the product. Two checks guard it, and **both must pass** before a baseline is stored:

1. **The interface checks the spine/back angle** (server-side, on every baseline, `api/core/calibration_gate.py`). `goal.torsoAngle` is **required** and must be a finite number. **Convention (the teammate's `sagittal_torso_inclination_deg` uses the same one, see `model-bridge.md`):** *trunk (spine/back) inclination from vertical, in degrees; 0 = upright, positive = leaning forward (slouching), negative = reclined against the backrest.* The allowed range is **10° either side of upright (-10° to +10°)**: leaning too far forward (slouching) and leaning too far back are both refused, and the range always brackets 0. The limits are product parameters, not medical thresholds; the 10° forward limit separates the example good (5°) and slouched (18°) values. **Caveat:** ergonomics notes (S5/S6 in `docs/health-claims.md`) describe a slightly reclined back as comfortable, so a 10° backward limit will refuse some comfortable reclined postures. If real users get refused for sitting back, widen `MAX_BACKWARD_LEAN_DEG` (one constant). Tune both against real model output.
2. **The model's own verdict** (optional, default accepted): the calibration result may carry `accepted` (bool) and `issues` (string[], user-facing reasons). `accepted: false` means "not a good goal posture".

`PUT /calibration` answers **422 `posture_not_good`** with the reasons in `error.issues` (and joined into `error.message`) and stores nothing; a missing or non-finite `torsoAngle` is a 400. `accepted`/`issues` are verdict fields and are never persisted. So a client that forgets to check can't save a bad baseline, and NaN/Infinity (which Python's JSON parser accepts) can't slip past the comparisons.

- **Dashboard / iPhone:** show the reasons and a "Try again" step (iOS: a model throws `CalibrationError.notGoodPosture(issues:)`, so the `PostureModel` signature is unchanged; the server's 422 is the backstop).
- **Testing without a model:** `POST /model/calibrate/finish?force=bad` returns a rejection whose issues come from the same back-angle gate; the dashboard has a dev-only "Demo: simulate a slouched posture" button; on iOS add the launch argument `-simulateBadCalibration`.

**For the model teammate, in `calibrate()`:** report `torsoAngle` per the convention above, and also judge: (a) the person is fully in frame with high confidence for the whole capture window; (b) the posture is **stable** across the countdown, not mid-movement; (c) neck/head alignment (head over shoulders) beyond the back angle. Keep envelopes **wide**: the promise is "your own comfortable posture", so reject clear slouching, not personal preference, and say *why* in `issues`.

## Pain check-ins, the personal insight, and the export

Research hasn't shown that slouching causes pain (`docs/health-claims.md`), so there is **no prediction
or risk score**. Instead:

- `POST /checkins` (`pain` 0-10, optional `area`) / `GET /checkins`: a weekly self-report. Dashboard only.
- `GET /insights/pain`: pairs each check-in with the share of seated time spent slouching in the 7 days before it and, once there are **5+ weekly points kept 6+ days apart** (and at least 2 seated hours in each window), a **Spearman rank correlation** with a plain bucket (`none` below 0.3, `modest` below 0.6, else `stronger`). It describes a pattern in *this person's* data. The UI must call it a pattern and not a cause, show n, and call anything under 8 weeks tentative.
- `GET /export`: de-identified weekly aggregates for the last 12 weeks plus check-ins by week. No user id, tokens, device details or timestamps finer than a day. It is built for the user to preview and download; **nothing is sent anywhere**. A future research-sharing option would have to be opt-in with explicit consent and ethics review; it does not exist.

## Coach: personal analysis, the on-device profile, and optional Gemini

- `GET /coach/insights` returns the **coaching pack**, computed from the user's own last 42 days with **no AI and no
  identifiers**: fatigue curve (slouch share by minutes since sitting down, and the personal "slip point"), danger
  hours, onset latency, triggers, **slouch fingerprint** (head-forward vs trunk-lean, from the `samples` table),
  posture drift against the saved baseline, response to nudges (first/repeat/break prompt, by time of day), recovery
  trend, alert-fatigue check, suggested settings changes (each is a valid partial `PUT /settings` body), habit
  strength, bests, relapse and challenge text, break quality, inferred work hours, setup hints, and matched exercises
  from a vetted library. Plus the full exercise library and `ai: {configured, model}`.
- The **profile lives only in the browser** (`localStorage`, key `sitwise.profile.v1`). The server has no endpoint that
  stores it. The dashboard builds an on-device version from the pack with plain rules, so Gemini is optional.
- Gemini (`POST /coach/analyze`, `/coach/ask`, `/coach/settings-from-text`) needs `consent: true` in the body and a
  configured `GEMINI_API_KEY` (503 `ai_not_configured` otherwise). What it receives is the de-identified pack from
  `compact_for_ai` (`GET /coach/preview` shows the exact payload and sends nothing). It never receives pain
  check-ins, ids, tokens, dates, images or the exercise steps. Outputs are validated against a JSON schema
  (Gemini ignores length limits, so the server enforces them) and returned to the browser **without being stored**.
  Per-user limit 6 calls/hour (in-process, so per server instance). Errors never include provider detail to the client (the real reason, with the key redacted, is written to the server log)
  (`ai_unavailable`, `ai_bad_output`, `rate_limited`).
- `settings-from-text` returns a **proposal** (`patch` plus a `changes` diff, validated by the same code as
  `PUT /settings`). It is never applied here; the dashboard shows the diff and applies it only after the user confirms.
- **Terms:** use a billing-enabled (paid) Gemini key. Google's terms for the free tier allow using inputs to improve
  its products and forbid personal or sensitive information. Sitwise sends habit numbers only, but the paid tier is
  the safe choice. Not medical advice: the prompts forbid it and say to use only the numbers provided.
- `GET /segments?days=` returns raw posture segments so the dashboard can overlay a calendar `.ics` **locally**: the
  file is parsed in the browser (times only, never titles or attendees) and is never uploaded.
- `POST /focus` starts (1-240 min) or stops (0) a focus session; with `settings.focus.onlyDuringFocus` on, nudges only
  fire while one is running. `settings.nudgeTone` (`gentle|neutral|direct`) changes the notification wording.
- Ingest now also stores a **downsampled reading** (about one per 5 s, only confident non-UNKNOWN samples, with the
  features) in the `samples` hypertable, which powers the fingerprint and drift. Frames are never stored: these are the
  numbers the phone already sends.
- Assumed feature convention (**confirm with the model teammate**): a larger `neckAngle`, `torsoAngle` and
  `headForwardOffset` means more forward / worse. The fingerprint and drift read them that way.

## Status, staleness, metrics

- `GET /status` is polled every ~2 s. Nothing runs in the background on Vercel, so **staleness is computed on read**: no sample for 15 s => `stale: true` and `state: AWAY` (`rawState` keeps the last real state).
- `GET /metrics?range=day|week|month&tzOffsetMin=` derives everything from events. **Posture score** = `100 x (GOOD + DEVIATING) / seated time`, where seated = GOOD + DEVIATING + SLOUCHING (AWAY excluded). The grace window the user chose isn't penalised. "On track" is a score of 70 or more (`GOOD_THRESHOLD_PCT`, a product threshold, not a medical one).
- Day boundaries use the browser's `tzOffsetMin`; the dashboard also saves it into settings so quiet hours match.

## Deviations from / additions to CLAUDE.md's contract table

| Change | Why |
|---|---|
| `GET /health` (public) | Dashboard shows the demo-data button only when dev routes are on; reports the store (`memory` or `postgres`) and `db: {ok, problem}` (`schema_missing` / `connect_failed` / `error`; never connection details). `ok` is false when the DB check fails. Non-sensitive. |
| `GET /push/web/public-key` (public) | The browser needs the VAPID **public** key to subscribe. |
| `POST /push/test` | "Send test notification" buttons in Settings, essential for demoing alerts. |
| `GET/PUT /settings` and `/calibration` accept either token | The iPhone app has a Settings screen and runs calibration. |
| `PUT /settings` is a partial update | Sliders save one field at a time. |
| `POST /pair/create` with a dashboard token | Re-issues a code (pair a new phone) without creating a new user. |
| `POST /dev/seed` without a token | Creates a new demo user and returns its tokens (dev routes only). |
| `POST/GET /checkins`, `GET /insights/pain`, `GET /export` | The pain check-in vs slouching view and the downloadable de-identified summary (dashboard token only). |
| `GET /coach/insights`, `/coach/preview`, `/segments`; `POST /coach/analyze`, `/coach/ask`, `/coach/settings-from-text`, `/focus` | The coaching layer (see the Coach section above). All dashboard-token only. |
| `settings.nudgeTone`, `settings.focus` | Nudge wording and focus mode. `focus.untilMs` is set by `POST /focus` (server time). |
| `POST /dev/seed` also returns `samples` | Seeds downsampled readings and an aged calibration so the Coach tab has data. |
| Error bodies may carry `issues` (string[]) | Structured reasons for `posture_not_good`. |
| `goal.torsoAngle` is now **required** and values must be finite | The calibration gate checks the spine/back angle (convention above, to confirm with the model teammate). |
| `/model/*` require a token (either kind) | "Validate the token on every route except /pair/*". |
| `PostureSample.source` (optional) | Which model produced a reading; shown on the Live page and returned with calibration. |
| `POST /model/calibrate/finish` and `GET /model/health` use the live feed when a model is streaming | The real model isn't on the server; the dashboard's calibration flow measures through the live feed instead of the stub. Response gains `stub: false`, `source`; health gains `live`, `source`. Still stubs when nothing is streaming. |

## Open contract questions (need a decision)

1. **Calibration trigger:** answered for the webcam bridge (the dashboard's countdown measures the live feed, see above). For the iPhone app, which runs its own stub `calibrate()`, a dashboard-to-phone "recalibrate" request (e.g. a flag in the ingest response) is still not built.
2. **`label` vs `deviation` precedence** (above).
3. **Angle conventions and units:** `torsoAngle` is spine/back inclination from vertical, + forward, which the teammate's pipeline confirms (`docs/MEASUREMENTS.md` in their repo). `neckAngle` is their ear-to-shoulder proxy signed forward by the bridge (a projected 2D angle, not a clinical neck angle). `headForwardOffset` is not produced by their model: ask them whether to add it, or drop it from the contract. Their side-view labels are a heuristic angle rule, not a validated classifier.

## Collection consent and external phone setup

`PUT /settings` accepts `dataCollectionConsent` (boolean, default false). `POST /posture/ingest`
returns HTTP 403 with `collection_consent_required` until the dashboard opts in. Withdrawal stops
new readings but retains history. This is separate from the per-request Gemini `consent: true`.

`GET /push/phone/status` requires a dashboard token and returns `webPushConfigured`, `receivers`,
`enabled`, `collectionAllowed`, and `thresholdSec` for setup diagnostics. Receiver tokens cannot
read this endpoint. See [iPhone alerts](iphone-alerts.md) for registration and physical testing.

Calibration endpoints documented above remain for legacy clients. The dashboard and Camera page
no longer expose calibration; the camera uses the upright reference.
