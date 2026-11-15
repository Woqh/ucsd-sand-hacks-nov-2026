# Sitwise: posture coaching that learns *you*

> **Mission.** Modern posture-detection projects focus solely on detecting poor posture, but they lack the
> foundation to drive long-term growth. Sitwise collects personalized data that is private to you and turns it
> into insights about your posture, so that you sit well in the long run.

*(Sitwise is our working name.)*

## The 30-second version

Most posture apps do one thing: they spot a slouch and buzz you. It has no memory, no idea what
"good" means *for your body*, and no way to tell whether any of it is helping. Sitwise is built the other way
round. A camera on your chair watches from the side and the model measures posture **on your own device, so only numbers
ever leave it**. We learn *your* goal posture, nudge you against a threshold *you* set, and keep a private
history that turns into insight over weeks: when you slouch, how fast you recover, whether your habits are
improving, and how your own pain lines up with your own posture. From that history we build a **coaching profile
that stays in your browser**: how you slouch, when your posture slips, how you respond to nudges, and what to try next.
We built it on a time-series database (Tiger Data) because posture is a time series, used Gemini to go deeper on what
coaching works for *you*, and grounded the health side in public research, including the parts that say *"we don't
know yet"*.

## The problem

- **Detectors have no foundation for growth.** They classify "bad posture" and nag. Nothing accumulates, so
  nothing improves, and the nag is the same for everyone.
- **"Good posture" is generic.** A single textbook posture ignores how you actually sit.
- **Health claims are easy to overstate.** It's tempting for a posture product to imply that slouching *causes*
  specific diseases. The research doesn't support that (see Data for Good below), and we think users deserve the truth.
- **Privacy.** A camera pointed at you all day is a real ask. Sending video to a server shouldn't be the price.

## What we do differently

| Typical posture detector | Sitwise |
|---|---|
| Fixed definition of "bad posture" | You calibrate **your own goal posture**; only a good one is accepted (the spine/back angle must be within 10° of upright, leaning too far forward *or* back is refused) |
| One alert for everyone | Your slouch threshold, sensitivity, cooldown and quiet hours; gentle escalation, then it stops |
| Stateless: fires and forgets | A private history: score, streaks, hour-by-weekday heatmap, time-to-recover, week-over-week goals |
| No idea what works for *you* | A private **coaching profile**: how you slouch (head forward vs leaning), the point in a sit where your posture slips, how fast you respond to each kind of nudge, and a weekly plan. Saved only in your browser |
| Says nothing about outcomes | Compares *your* weekly pain check-in with *your* slouch data, with the caveats stated |
| Implied health scare tactics | An evidence meter showing what research does and doesn't show; no made-up predictions |
| Video to the cloud, or unclear | Frames are analysed on the phone and dropped; the API has no field that could carry an image |

## How it works

```
iPhone on the chair (side view)           Flask API on Vercel             Tiger Cloud
 camera -> on-device model  --numbers-->   state machine + alerts  -->    events hypertable
 (frames never leave)        ~1 Hz         per-user thresholds             (time series)
          ^                                       |   \
          '---- push notification (vibrates) -----'    '--> React dashboard (analytics, coaching, evidence)
```

- **The model** (teammate-built): MediaPipe pose landmarks plus a side-view angle rule that labels upright / leaning
  forward / leaning back. In our demo the iPhone's picture (through Camo) shows in the dashboard's Camera page, the model runs on the laptop, and
  only its numbers go on to the database; the iPhone app itself still uses a stub until the model is ported to the phone.
- **A posture state machine** (GOOD, DEVIATING, SLOUCHING, AWAY) driven by *your* thresholds, written as a pure,
  unit-tested function so it runs on stateless serverless functions.
- **Alerts:** a push notification on the phone (it vibrates) and a web push on the desktop.
- **Coaching profile:** the dashboard works out your patterns from your own numbers and builds the profile **on your
  device**. Optionally, Gemini writes a deeper version from de-identified habit numbers, after you see exactly what
  would be sent and say yes.
- **Private by construction:** anonymous pairing code instead of accounts, tokens stored hashed, no third-party
  analytics, and a de-identified export you can inspect and download. Nothing is shared.

## Live demo (about 3 minutes)

1. **Calibrate.** Sit comfortably, countdown, goal posture saved. Then show a slouched attempt being **refused**
   with the reason ("Your back is leaning forward about 18° (aim for within 10° of upright)"). *Only a good
   posture can become your goal.*
2. **Live coaching.** Slouch past the threshold: Good, then Drifting (with a countdown), then Slouching, and the
   desktop notifies (and the phone, once the iOS build and push keys are set up). Sit up and it recovers.
3. **Analytics.** Six weeks of history: the score climbing, a heatmap showing afternoons are the weak spot, time
   to recover, goal and streak.
4. **Pain & evidence.** The 10-second weekly check-in, "your pain vs your slouching" (a pattern in *your* data,
   explicitly not a cause), the evidence meter, and population context.
5. **Coach.** The profile built from six weeks of (synthetic) data: "you mostly slouch by letting your head drift
   forward", "your posture slips after about 110 minutes", "Wednesday around 5 PM is your weakest time", plus how fast
   you respond to each kind of nudge. (Read the numbers off the screen; they are generated, not real people.)
   Show the fatigue curve, then **"See what would be sent"** (the exact payload, no ids, dates or pain data) and the
   consent box before Gemini is ever called. Apply one suggested setting change with a click.
6. **Your data.** A de-identified weekly export that never leaves the device.

*(The demo history and check-ins are synthetic, generated for the demo and labelled as such.)*

## Data for Good: public research and data we used

We started out wanting to build a "keep slouching and you'll get X in N years" predictor. We went and read the
public research and data first, and it told us **no honest model like that exists**. So we built something more
useful and more truthful: *your own data, next to what the evidence actually says.*

| Public source (web) | What we took | Where it shows up |
|---|---|---|
| **Global Burden of Disease 2021, low back pain** ([Lancet Rheumatol 2023](https://pubmed.ncbi.nlm.nih.gov/37273833/)) | 619 million people lived with low back pain in 2020 (95% UI 554-694M), projected 843 million by 2050 | "How common are back and neck pain?" (population context, labelled *not your risk*) |
| **Global Burden of Disease 2021, neck pain** ([Lancet Rheumatol 2024](https://pubmed.ncbi.nlm.nih.gov/38383088/)) | 203 million in 2020 (95% UI 163-253M); prevalence peaks between ages 45 and 74 | Same card |
| **Swain et al. 2020**, review of 41 systematic reviews ([J Biomech](https://pubmed.ncbi.nlm.nih.gov/31451200/)) | "There is no consensus regarding causality" between physical exposure (posture, prolonged sitting) and low back pain | Evidence meter (back pain: *mixed*); reworded outlook message |
| **Mahmoud et al. 2019**, 15 studies ([Curr Rev Musculoskelet Med](https://pmc.ncbi.nlm.nih.gov/articles/PMC6942109)) | Forward-head posture is associated with neck pain in adults (not adolescents), but cross-sectional data **can't establish cause**, and the authors call for longitudinal studies | Evidence meter (neck pain: *associated, cause not established*); our longitudinal-data angle |
| **Ergonomics guidance** ([Cornell ergonomics course notes](https://ergo.human.cornell.edu/DEA3250Flipbook/DEA3250notes/sitting.html)) | A supported, slightly reclined back is described as comfortable; rigid 90-degree sitting isn't required | Context for the calibration range, and an honest caveat that the limits need tuning |
| *Not found:* any source linking sitting posture to **arthritis** (our search wasn't exhaustive) | Nothing, so we **don't claim it** | The evidence meter says "No evidence found" for arthritis |

**What this changed in the product**
- We replaced a scary-sounding prediction with a **personal, hedged comparison**: your weekly pain rating against your
  own slouch share, shown only once there are enough weeks, always labelled "a pattern in your own weeks, not
  proof", and called *tentative* under 8 weeks.
- We reworded the outlook from "associated with neck and back pain risk over the years" to "linked with neck
  discomfort in some studies, but research hasn't shown that it causes pain".
- Every health number in the app is cited in one file, and the rule is: **no source, no number.**

**Why it's data for good:** it turns public research and private personal data into health literacy people can
trust. And there is a real gap we could help close: the authors of the forward-head-posture review note that all 15
eligible studies were cross-sectional and call for longitudinal studies. A privacy-first app that measures posture
exposure objectively over weeks, alongside pain check-ins, is the kind of data collector that gap needs.

**Status, stated plainly:** the personal comparison, evidence meter, population context and a **local de-identified
export** are built. **Actual data sharing is not built:** it would need explicit opt-in consent, ethics review and a
destination, and we'd only ever share de-identified weekly aggregates. We link the IHME GBD Results Tool for
age/region detail, but we use only the headline figures above.

## Tiger Data: why a time-series database is the right foundation

Posture is a time series. Every state change (good, drifting, slouching, away) is an event with a timestamp,
and everything users value is a time-bucketed question: today's score, the hour-by-weekday heatmap, the 7 days of
exposure before a pain rating, week-over-week progress.

**What's built for Tiger Cloud (TimescaleDB)**
- **`events` and `samples` are hypertables**, partitioned by time (weekly and daily chunks), with compression
  policies for old chunks and a 90-day retention policy on `samples`. Applying the schema is one command
  (`python scripts/init_db.py`, idempotent).
- **`samples`: one posture reading per ~5 s** (deviation, label, neck/torso/head-forward features, never an image).
  It is what lets the Coach see *how* you slouch and when your posture drifts. The fatigue curve, fingerprint and
  drift are SQL rollups over it (`date_trunc` hour buckets, the same shape as a continuous aggregate).
- **Serverless-ready connections.** Vercel functions open many short-lived connections, so the app is designed for
  Tiger's **connection pooler in transaction mode** (small client pool, no prepared statements).
- **Chunk-friendly queries (by design):** time-range queries filter on the hypertable's time column so Timescale can
  skip chunks that aren't in range.
- **Verified, not assumed:** the data layer is covered by store-contract tests and a full end-to-end API suite
  (**243 Python tests**, plus 25 for the dashboard's on-device analysis), run against both an in-memory store and a
  **real Postgres engine**.

**What Tiger Data unlocks next (partly built)**
- **Continuous aggregates:** `samples_hourly` is created (best effort) but **the app still reads the raw table**.
  Pointing the dashboard at the rollup, so it stays current as data arrives, is the next step.
- **`time_weight` hyperfunctions** (included on Tiger Cloud) for correct averages over unevenly sampled data, with
  *each user's own threshold applied at query time*, which is personalization done in the database.

**Honest status:** the schema and data layer are tested on standard Postgres. **We have not yet run it on a live
Tiger Cloud service**, and the hypertable, compression, retention and continuous-aggregate statements are verified
only once we do. That is the first
item in our prep checklist below.

## Gemini: what coaching works for *you*, and a profile that stays yours

A detector can't tell you whether its nudges help. Sitwise measures it: after every nudge we record whether and how
fast you sat back up, then break that down by nudge type, time of day and time in the sit. That becomes a personal
profile of **your sitting habits, how you respond to coaching, and how best to improve**.

**What the profile contains** (all from your own numbers):
- *How you slouch:* head drifting forward vs upper body leaning, measured against your own good posture.
- *When it slips:* your fatigue curve and the minute your posture usually drops, and your weakest weekday and hour.
- *How you respond:* the share of nudges you fix within 30 s, first vs repeat nudges, morning vs afternoon, whether
  you are getting faster, and whether you are tuning out (alert fatigue).
- *What to do:* a weekly plan, exercises matched to how you slouch (from a vetted library), and suggested setting
  changes you apply with one click. It also suggests the nudge wording (gentle, neutral or direct) that suits you.

**Where Gemini fits.** The dashboard builds this profile **on your device** with plain rules, so it works with no AI.
Gemini is the "go deeper" option: it reads the de-identified numbers and writes a more tailored analysis (the
structured result is checked against a JSON schema, and it can only pick exercises from our library, so it cannot
invent medical advice). Gemini also powers **"Ask about your habits"** (answers only from your numbers and our cited
facts) and **"Describe your day"** (turns "I work 9 to 6 and hate nudges in meetings" into a settings change you
review and confirm).

**Why the profile "never leaves your device", and what that does and doesn't mean.**
- The profile is saved only in your browser's local storage. Our server has **no route that stores it**.
- Gemini is a cloud service, so using it means habit numbers *do* leave the device, once, and only if you opt in. We
  show you the **exact payload first** and nothing is sent until you tick consent. It contains no name, email,
  account ID, dates, images or **pain check-ins**.
- What comes back is shown to you and saved only in your browser. If Gemini is off, unconfigured or errors, you keep the
  on-device profile.
- Google's terms for the free Gemini tier allow using inputs to improve its products and forbid personal or
  sensitive data, so a real deployment must use a **paid-tier key**. We say so in the app, the README and the docs.

**Honest status:** built and tested with a fake client; **not yet run against the live Gemini API** (we had no key
when we built it). The on-device profile is what we demo if the API is unavailable.

## What's built vs. what's next

| Built | Not yet / caveats |
|---|---|
| Web dashboard: Live status, Analytics, Pain & evidence, **Coach**, Calibration, Settings, Pairing | iOS app is written but **not yet compiled on a Mac/device** |
| 27-route API with a unit-tested state machine, per-user alert rules, quiet hours | **Real model integrated end to end** (iPhone feed in the Camera page -> MediaPipe + angle rule -> database, calibration measured live; also a headless webcam bridge), verified with a simulated camera feed, **not yet with a physical camera**. The **iPhone app is still on the stub**; the side-view rule is a heuristic, not a validated classifier |
| Calibration gate (spine/back angle within 10° of upright, plus the model's verdict) | Push notifications not yet tested with real Apple/VAPID credentials |
| Analytics: score, trend, heatmap, recovery time, goals, streaks, session timeline | Tiger Cloud service not yet connected (tested on plain Postgres) |
| Pain check-in vs your slouching; evidence meter; cited population context; local export | No data sharing exists (by design, until consent and ethics are in place) |
| Coach: fatigue curve, slouch fingerprint, nudge-response analysis, habit strength, exercises, printable report, share card, local calendar overlay | Adaptive nudging **suggests** changes (one-click apply); it doesn't tune itself. Calendar is a local `.ics` import, not a live calendar |
| Gemini coaching profile, ask-your-habits, describe-your-day (consent, payload preview, on-device fallback) | **Never run on the live Gemini API yet**; needs a paid-tier key. Ask is context-stuffed, not function calling |
| Simulator and seed scripts so everything is demoable without a camera | Continuous aggregates not yet read by the app; Tiger Cloud not yet connected |

## Questions we expect

- **"Why not just use a posture-detection model?"** Detection is table stakes and it's the teammate's piece. The
  product is the layer that turns detection into long-term change: personal baselines, private history, and
  insight over time.
- **"Is slouching actually harmful?"** The honest answer from the research is *associated with neck pain in
  adults, cause not established, and no consensus for back pain*. We show that, rather than a scare.
- **"Where does my data go?"** Camera frames are analysed on the phone and dropped. Only numeric features and posture
  states are sent, the database holds no images, and any export is de-identified and stays on your device.
- **"Does Gemini see my data?"** Only if you opt in, and only de-identified habit numbers: no name, email, account
  ID, dates, images or pain check-ins. You see the exact payload before it is sent. The profile it returns is stored
  only in your browser. Without Gemini the same profile is built on your device.
- **"Why Tiger Data?"** Our core data is a time series; hypertables, compression and (next) continuous aggregates
  are the natural fit, and the pooler suits serverless.
- **"What's real?"** Everything in the demo is real software, including the teammate's pose model when the webcam bridge is running (the phone app's model is still a stub), except the demo history and
  pain check-ins (synthetic, labelled).

## Where we're going

1. Connect the real on-device model and run on a physical iPhone.
2. Tiger-native analytics: read the continuous aggregates, use `time_weight`, and run it all on a live Tiger Cloud service.
3. Adaptive coaching that applies what works for *you* (nudge timing and wording) on its own, with your approval, and
   a live calendar (read-only, opt-in) instead of a file import.
4. An opt-in, de-identified research contribution, once consent and ethics review exist.

**Close:** posture apps have been answering "are you slouching right now?" for years. Sitwise answers the question
that actually changes habits: *"what's true about **your** posture over time, and what can **you** do about it?"*

---

### Prep checklist (team only; delete before sharing)

- [ ] Create a Tiger Cloud service, run `python scripts/init_db.py`, and confirm `events` is a hypertable. **Don't say "running on Tiger Cloud" on stage until this is done.**
- [ ] Re-check every number against `docs/health-claims.md` (no source, no number); the demo data is synthetic, so say so.
- [ ] Confirm the hackathon track rules (Tiger Data, Data for Good) and tailor the emphasis.
- [ ] Try the real flow with the **physical iPhone through Camo** on a chair side mount (`docs/camera-setup.md`; the model server needs the Python 3.12 venv). Choose Left/Right under "Which way do you face?", set the goal posture, turn on "Send readings". It has only been run on a simulated feed (a test photo), never a live camera.
- [ ] Ask the teammate: does a 10° band suit real sitters, should `headForwardOffset` exist, and can the side-view rule be checked on labelled footage? Don't call it "validated" until then.
- [ ] Rehearse the demo from `docs/demo-script.md`; keep the simulator as the fallback and a recorded video as backup.
- [ ] Get a **billing-enabled** Gemini key, set `GEMINI_API_KEY`, and run the Coach tab's "Improve with Gemini" once end to end. It has **never been run live**; don't claim it on stage until it has. Keep the on-device profile as the fallback.
- [ ] Re-read Google's current Gemini API terms (free vs paid data use) before the demo.
- [ ] The fingerprint and drift read larger torso/neck angle as more forward; the teammate's convention matches for torso, and the bridge signs the neck forward. They have no head-forward offset, so the fingerprint uses neck and torso only.
