# Demo script

Five minutes. Fallback at the bottom if anything misbehaves.

## Before you go on

```bash
# 1. API (dev routes on, in-memory store is fine for a local demo)
ENABLE_DEV_ROUTES=1 flask --app api.index run --port 5001
# 2. dashboard
cd web && npm run dev
# 3. seed six weeks of history (+ demo pain check-ins) and get a login link + pairing code
python scripts/seed.py            # prints  http://localhost:5173/?token=...  and a pairing code
```

- Open the printed link (it signs this browser in). In **Settings**, set the slouch threshold to ~**8 s** so the live part is quick, and click **Enable on this computer** (needs VAPID keys: `python scripts/gen_vapid.py`) then **Test desktop alert**.
- On the iPhone: enter the pairing code (or run the simulator: `python scripts/simulate.py --code <CODE> --loop`).

## The pitch

1. **Hook.** "Every posture app just yells at you. Ours learns *your* good posture and helps you improve it over weeks."
2. **Calibrate.** Dashboard > Calibrate (or on the phone): sit comfortably, countdown, "goal posture saved". "The model runs on the phone." Then click **Demo: simulate a slouched posture** (dev builds): it is refused with "Your back is leaning forward about 18° (aim for under 10°)" and nothing is saved. "Only a good posture can become your goal."
3. **Live.** Slouch past the threshold. Show the **Live** page go *Good -> Drifting (nudge countdown) -> Slouching*, the **phone vibrating** (push) and the **desktop notification** firing. Sit up and show it recover to Good.
4. **Analytics.** Open **Analytics > Week**: score 80, up 13 vs last week, the trend line climbing, the hour-by-weekday heatmap showing afternoons are the problem, the outlook ("on track"), the goal ("67% -> 70%") and the streak. Mention the earlier days were "at risk".
5. **Pain & evidence.** Analytics > **Pain & evidence**: the 10-second weekly check-in, "your pain vs your slouching" (a pattern in *your* data, not a cause; the demo check-ins are synthetic), the evidence meter ("nobody has shown slouching causes pain"), and the cited population context. Pitch line: "We don't scare you with a made-up 'you'll get arthritis in 10 years'. We show your own data and what the research actually says." Mention Settings > **Your data**: a de-identified export that never leaves the device.
6. **Coach.** Open **Coach**. The profile was just built **on this device**: "you mostly slouch by letting your head drift forward", "your posture slips after about 110 minutes", "Wednesday around 5 PM is your weakest time". Flip to **Patterns** (the fatigue curve and the slip point) and **Coaching** (how fast you sit back up after each kind of nudge; apply one suggested setting with a click). Pitch line: "A detector says *you're slouching*. This says *how you slouch, when it happens, and what works for you*, and it stays in your browser." If Gemini is configured: **See what would be sent** (show the exact numbers, no ids, dates or pain data), tick consent, and build the Gemini profile. The demo history is synthetic, so say so.
7. **Privacy + hardware.** "Nothing but numbers leaves the phone: no video, no photos." Show the side-mounted chair setup (`docs/hardware.md`).

## Fallback

- No camera or model yet: the **simulator** (`scripts/simulate.py --loop`) drives the same dashboard and alerts.
- No push credentials: the Live page, analytics and **Test** buttons still demo everything except the actual vibration; show the recorded clip of the phone buzzing.
- Gemini unavailable or no key: skip the "Improve with Gemini" click; the on-device profile is the demo. **Gemini has never been run live in this repo, so test it once before you rely on it.**
- Dashboard down: the recorded demo video.
