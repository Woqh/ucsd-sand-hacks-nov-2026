# Sitwise: posture coaching that learns *you*

> **Mission.** Modern posture-detection projects focus solely on detecting poor posture, but they lack the
> foundation to drive long-term growth. Sitwise collects personalized data that is private to you and turns it
> into insights about your posture, so that you sit well in the long run.

*(Sitwise is our working name.)*

## The 30-second version

Most posture apps do one thing: they spot a slouch and buzz you. It has no memory, no idea what
"good" means *for your body*, and no way to tell whether any of it is helping. Sitwise is built the other way
round. A phone on your chair watches from the side and measures posture **on the device, so only numbers
ever leave it**. We learn *your* goal posture, nudge you against a threshold *you* set, and keep a private
history that turns into insight over weeks: when you slouch, how fast you recover, whether your habits are
improving, and how your own pain lines up with your own posture. We built it on a time-series database
(Tiger Data) because posture is a time series, and we grounded the health side in public research, including the
parts that say *"we don't know yet"*.

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

- **On-device model** (teammate-owned; stubbed in our demo): OpenCV pose features, sent as numbers only.
- **A posture state machine** (GOOD, DEVIATING, SLOUCHING, AWAY) driven by *your* thresholds, written as a pure,
  unit-tested function so it runs on stateless serverless functions.
- **Alerts:** a push notification on the phone (it vibrates) and a web push on the desktop.
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
5. **Your data.** A de-identified weekly export that never leaves the device.

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
- **`events` is a hypertable**, partitioned by time in weekly chunks, with a compression policy for old chunks.
  Applying the schema is one command (`python scripts/init_db.py`, idempotent).
- **Serverless-ready connections.** Vercel functions open many short-lived connections, so the app is designed for
  Tiger's **connection pooler in transaction mode** (small client pool, no prepared statements).
- **Chunk-friendly queries (by design):** time-range queries filter on the hypertable's time column so Timescale can
  skip chunks that aren't in range.
- **Verified, not assumed:** the data layer is covered by store-contract tests and a full end-to-end API suite
  (**152 automated tests**), run against both an in-memory store and a **real Postgres engine**.

**What Tiger Data unlocks next (designed, not yet built)**
- **A `samples` hypertable** (one posture reading per ~5 s) so we can see *how* you slouch (head-forward vs
  rounded back), your fatigue curve, and posture drift.
- **Continuous aggregates** for hourly and daily rollups that stay current as data arrives, so the dashboard reads
  rollups instead of scanning raw rows.
- **`time_weight` hyperfunctions** (included on Tiger Cloud) for correct averages over unevenly sampled data, with
  *each user's own threshold applied at query time*, which is personalization done in the database.

**Honest status:** the schema and data layer are tested on standard Postgres. **We have not yet run it on a live
Tiger Cloud service**, and the hypertable/compression statements are verified only once we do. That is the first
item in our prep checklist below.

## What's built vs. what's next

| Built | Not yet / caveats |
|---|---|
| Web dashboard: Live status, Analytics, Pain & evidence, Calibration, Settings, Pairing | iOS app is written but **not yet compiled on a Mac/device** |
| 20-route API with a unit-tested state machine, per-user alert rules, quiet hours | **On-device pose model is a teammate's and is stubbed** (the interface runs end to end on it) |
| Calibration gate (spine/back angle within 10° of upright, plus the model's verdict) | Push notifications not yet tested with real Apple/VAPID credentials |
| Analytics: score, trend, heatmap, recovery time, goals, streaks, session timeline | Tiger Cloud service not yet connected (tested on plain Postgres) |
| Pain check-in vs your slouching; evidence meter; cited population context; local export | No data sharing exists (by design, until consent and ethics are in place) |
| Simulator and seed scripts so everything is demoable without a camera | Adaptive nudging, `samples` hypertable, continuous aggregates, AI weekly coach: **planned** |

## Questions we expect

- **"Why not just use a posture-detection model?"** Detection is table stakes and it's the teammate's piece. The
  product is the layer that turns detection into long-term change: personal baselines, private history, and
  insight over time.
- **"Is slouching actually harmful?"** The honest answer from the research is *associated with neck pain in
  adults, cause not established, and no consensus for back pain*. We show that, rather than a scare.
- **"Where does my data go?"** Camera frames are analysed on the phone and dropped. Only numeric features and posture
  states are sent, the database holds no images, and any export is de-identified and stays on your device.
- **"Why Tiger Data?"** Our core data is a time series; hypertables, compression and (next) continuous aggregates
  are the natural fit, and the pooler suits serverless.
- **"What's real?"** Everything in the demo is real software except the pose model (stubbed) and the demo history and
  pain check-ins (synthetic, labelled).

## Where we're going

1. Connect the real on-device model and run on a physical iPhone.
2. Tiger-native analytics: `samples` hypertable, continuous aggregates, `time_weight`.
3. Adaptive coaching that learns what works for *you* (nudge timing and channel) and an AI-written weekly summary
   built only from your aggregated numbers (planned; never from images).
4. An opt-in, de-identified research contribution, once consent and ethics review exist.

**Close:** posture apps have been answering "are you slouching right now?" for years. Sitwise answers the question
that actually changes habits: *"what's true about **your** posture over time, and what can **you** do about it?"*

---

### Prep checklist (team only; delete before sharing)

- [ ] Create a Tiger Cloud service, run `python scripts/init_db.py`, and confirm `events` is a hypertable. **Don't say "running on Tiger Cloud" on stage until this is done.**
- [ ] Re-check every number against `docs/health-claims.md` (no source, no number); the demo data is synthetic, so say so.
- [ ] Confirm the hackathon track rules (Tiger Data, Data for Good) and tailor the emphasis.
- [ ] Confirm the `torsoAngle` convention and the 10° range with the model teammate.
- [ ] Rehearse the demo from `docs/demo-script.md`; keep the simulator as the fallback and a recorded video as backup.
- [ ] Decide whether to name Gemini: nothing is built, so only mention it as planned.
