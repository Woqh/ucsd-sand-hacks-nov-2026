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

## Calibration gate: only a good posture is accepted

The goal posture is what every later nudge is measured against, so a slouched "goal" would silently
break the product. Two checks guard it, and **both must pass** before a baseline is stored:

1. **The interface checks the spine/back angle** (server-side, on every baseline, `api/core/calibration_gate.py`). `goal.torsoAngle` is **required** and must be a finite number. **Convention (flagged: confirm with the model teammate, since it defines the payload):** *trunk (spine/back) inclination from vertical, in degrees; 0 = upright, positive = leaning forward (slouching), negative = reclined against the backrest.* The allowed range is **10° either side of upright (-10° to +10°)**: leaning too far forward (slouching) and leaning too far back are both refused, and the range always brackets 0. The limits are product parameters, not medical thresholds; the 10° forward limit separates the example good (5°) and slouched (18°) values. **Caveat:** ergonomics notes (S5/S6 in `docs/health-claims.md`) describe a slightly reclined back as comfortable, so a 10° backward limit will refuse some comfortable reclined postures. If real users get refused for sitting back, widen `MAX_BACKWARD_LEAN_DEG` (one constant). Tune both against real model output.
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
| Error bodies may carry `issues` (string[]) | Structured reasons for `posture_not_good`. |
| `goal.torsoAngle` is now **required** and values must be finite | The calibration gate checks the spine/back angle (convention above, to confirm with the model teammate). |
| `/model/*` require a token (either kind) | "Validate the token on every route except /pair/*". |

## Open contract questions (need a decision)

1. **Calibration trigger:** the real model runs on the phone, so who starts calibration? Today the dashboard runs the guided flow against the server model *stubs*; the phone runs its own. A dashboard-to-phone "recalibrate" request (e.g. a flag in the ingest response) is not built.
2. **`label` vs `deviation` precedence** (above).
3. **Angle conventions and units:** `torsoAngle` now has a fixed convention (spine/back inclination from vertical, + forward) because the calibration gate depends on it; confirm it with the model teammate. `neckAngle` / `headForwardOffset` stay the model's, stored unchanged.
