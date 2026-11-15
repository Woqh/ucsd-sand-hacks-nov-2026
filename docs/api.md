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
break the product. Whether a posture is *good* is a posture judgement, so **the model decides**; the
interface enforces and surfaces it.

- **Contract addition (flagged; optional and backwards-compatible):** the calibration result may carry `accepted` (bool, default `true` when absent) and `issues` (string[], user-facing reasons). `accepted: false` means "not a good goal posture".
- **Server:** `PUT /calibration` answers **422 `posture_not_good`** for `accepted: false` and stores nothing; `accepted` and `issues` are verdict fields and are never persisted. So even a client that forgets to check can't save a bad baseline.
- **Dashboard / iPhone:** show the reasons and a "Try again" step (iOS: a model throws `CalibrationError.notGoodPosture(issues:)`, the `PostureModel` signature is unchanged).
- **Testing it without a model:** `POST /model/calibrate/finish?force=bad` returns a rejection; the dashboard has a dev-only "Demo: simulate a slouched posture" button; on iOS add the launch argument `-simulateBadCalibration`.

**For the model teammate: what `calibrate()` should check before accepting** (thresholds are yours, since they depend on your angle conventions; cite an ergonomic reference for them):
1. The person is fully in frame, with high confidence for the whole capture window.
2. The posture is **stable** (low variance across the countdown), not mid-movement.
3. The measured angles fall inside a *healthy envelope* (roughly: head over shoulders over hips, no pronounced forward head or rounded upper back).
4. Keep the envelope **wide**. The product promise is "your own comfortable posture", so reject clear slouching, not personal preference, and report *why* in `issues` so the user can fix it.

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
| `/model/*` require a token (either kind) | "Validate the token on every route except /pair/*". |

## Open contract questions (need a decision)

1. **Calibration trigger:** the real model runs on the phone, so who starts calibration? Today the dashboard runs the guided flow against the server model *stubs*; the phone runs its own. A dashboard-to-phone "recalibrate" request (e.g. a flag in the ingest response) is not built.
2. **`label` vs `deviation` precedence** (above).
3. **Angle conventions and units** for `features` / `goal` are the model's; the server stores any numeric keys unchanged.
