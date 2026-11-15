# Demo script

Five minutes. Fallback at the bottom if anything misbehaves.

## Before you go on

```bash
# 1. API (dev routes on, in-memory store is fine for a local demo)
ENABLE_DEV_ROUTES=1 flask --app api.index run --port 5001
# 2. dashboard
cd web && npm run dev
# 3. seed two weeks of history and get a login link + pairing code
python scripts/seed.py            # prints  http://localhost:5173/?token=...  and a pairing code
```

- Open the printed link (it signs this browser in). In **Settings**, set the slouch threshold to ~**8 s** so the live part is quick, and click **Enable on this computer** (needs VAPID keys: `python scripts/gen_vapid.py`) then **Test desktop alert**.
- On the iPhone: enter the pairing code (or run the simulator: `python scripts/simulate.py --code <CODE> --loop`).

## The pitch

1. **Hook.** "Every posture app just yells at you. Ours learns *your* good posture and helps you improve it over weeks."
2. **Calibrate.** Dashboard > Calibrate (or on the phone): sit comfortably, countdown, "goal posture saved". "The model runs on the phone."
3. **Live.** Slouch past the threshold. Show the **Live** page go *Good -> Drifting (nudge countdown) -> Slouching*, the **phone vibrating** (push) and the **desktop notification** firing. Sit up and show it recover to Good.
4. **Analytics.** Open **Analytics > Week**: score 80, up 13 vs last week, the trend line climbing, the hour-by-weekday heatmap showing afternoons are the problem, the outlook ("on track"), the goal ("67% -> 70%") and the streak. Mention the earlier days were "at risk".
5. **Privacy + hardware.** "Nothing but numbers leaves the phone: no video, no photos." Show the side-mounted chair setup (`docs/hardware.md`).

## Fallback

- No camera or model yet: the **simulator** (`scripts/simulate.py --loop`) drives the same dashboard and alerts.
- No push credentials: the Live page, analytics and **Test** buttons still demo everything except the actual vibration; show the recorded clip of the phone buzzing.
- Dashboard down: the recorded demo video.
