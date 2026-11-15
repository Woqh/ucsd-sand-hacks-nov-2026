"""Fake-but-realistic posture history for demos. Pure and deterministic (seeded RNG).

The story it tells: a user who starts the period slouching nearly half the time, in long
episodes, and learns to respond to nudges. Each day the slouch share and the length of each
slouch shrink, so the score climbs from the 50s to the high 80s and crosses the "on track" line
partway through. Afternoons are worse than mornings; weekends are short. The newest block is
cut at `now_ms`.
"""
from __future__ import annotations

import random
from typing import Any

from api.core import insights, scoring
from api.core.state_machine import AWAY, DEVIATING, GOOD, SLOUCHING

DAY = 86_400_000
MIN = 60_000
SEC = 1_000
THRESHOLD_SEC = 30  # matches the default slouch threshold (the grace period before SLOUCHING)


def generate(days: int, now_ms: int, tz_offset_min: int = 0, seed: int = 7) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    off = tz_offset_min * MIN
    today_idx = (now_ms + off) // DAY
    events: list[dict[str, Any]] = []

    for n, idx in enumerate(range(today_idx - days + 1, today_idx + 1)):
        progress = n / max(1, days - 1)                          # 0 = oldest day, 1 = today
        slouch_share = 0.45 - 0.33 * progress + rng.uniform(-0.03, 0.03)
        longest_slouch = 360 - 260 * progress                    # seconds: nudges get answered faster
        weekday = (idx + 3) % 7                                  # Mon = 0
        midnight = idx * DAY - off
        if weekday < 5:
            blocks = [(9 * 60 + rng.randint(-10, 20), 12 * 60 + rng.randint(0, 25)),
                      (13 * 60 + rng.randint(0, 20), 17 * 60 + rng.randint(0, 40))]
            if rng.random() < 0.3:
                blocks.append((20 * 60, 21 * 60 + rng.randint(0, 20)))
        else:
            blocks = [(14 * 60, 16 * 60 + rng.randint(0, 30))]
        for start_min, end_min in blocks:
            start, end = midnight + start_min * MIN, min(midnight + end_min * MIN, now_ms - MIN)
            if end - start > 5 * MIN:
                _block(events, rng, start, end, midnight, slouch_share, longest_slouch)

    return sorted(events, key=lambda e: e["t"])


def _ev(t: int, frm: str, to: str, *, alert: bool = False, level: int = 0, reason: str = "",
        kind: str = "transition", deviation: float | None = None) -> dict[str, Any]:
    return {"kind": kind, "t": int(t), "from_state": frm, "to_state": to, "alert": alert,
            "level": level, "reason": reason, "deviation": deviation, "session_id": None}


def _block(events: list[dict[str, Any]], rng: random.Random, start: int, end: int, midnight: int,
           slouch_share: float, longest_slouch: float) -> None:
    t = start
    events.append(_ev(t, AWAY, GOOD, reason="appeared", deviation=0.1))
    while True:
        hour = (t - midnight) / (60 * MIN)
        f = slouch_share + (0.10 if 14 <= hour < 17.5 else -0.04 if hour < 10.5 else 0.0)
        f = min(0.7, max(0.04, f))
        slouch = rng.uniform(0.35, 1.0) * longest_slouch        # seconds spent SLOUCHING per episode
        # good-posture stretch sized so slouch / (slouch + good) lands near `f` (grace counts as good)
        good = max(60.0, slouch * (1 - f) / f - THRESHOLD_SEC) * rng.uniform(0.6, 1.4)

        t += int(good * SEC)
        if t >= end:
            break
        if rng.random() < 0.25:                                  # a lapse they corrected inside the grace window
            events.append(_ev(t, GOOD, DEVIATING, reason="deviated", deviation=0.45))
            t += int(rng.uniform(8, 25) * SEC)
            if t >= end:
                break
            events.append(_ev(t, DEVIATING, GOOD, reason="recovered", deviation=0.1))
            continue

        events.append(_ev(t, GOOD, DEVIATING, reason="deviated", deviation=0.45))
        t += THRESHOLD_SEC * SEC
        if t >= end:
            break
        events.append(_ev(t, DEVIATING, SLOUCHING, alert=True, level=1, reason="threshold", deviation=0.7))
        for level, after in ((2, 120), (3, 240)):                # gentle escalation if ignored
            if slouch > after and t + after * SEC < end:
                events.append(_ev(t + after * SEC, SLOUCHING, SLOUCHING, alert=True, level=level,
                                  reason="escalation", kind="alert", deviation=0.7))
        t += int(slouch * SEC)
        if t >= end:
            break
        events.append(_ev(t, SLOUCHING, GOOD, reason="recovered", deviation=0.1))
    # close the block: whatever state we were in, they leave
    last = [e for e in events if e["kind"] == "transition"][-1]["to_state"]
    events.append(_ev(end, last, AWAY, reason="left_frame"))


def checkins_from_events(events: list[dict[str, Any]], now_ms: int, seed: int = 7) -> list[dict[str, Any]]:
    """DEMO weekly pain check-ins for the seeded history: one per 7 days going back from now, with pain
    loosely tracking that week's slouch share plus noise (so the demo has a believable, imperfect
    relationship to show). Fake data for dev/demo only."""
    if not events:
        return []
    rng = random.Random(seed + 1)
    first = min(e["t"] for e in events)
    segs = scoring.build_segments(events, None, first - DAY, now_ms)
    out: list[dict[str, Any]] = []
    k = 0
    while now_ms - k * 7 * DAY - insights.WINDOW_MS >= first:
        t = now_ms - k * 7 * DAY
        pct, _seated = insights.slouch_exposure(segs, t)
        if pct is not None:
            pain = int(min(10, max(0, round(1.0 + 0.09 * pct + rng.uniform(-1.2, 1.2)))))
            out.append({"t": t, "pain": pain, "area": rng.choice(["neck", "lower_back", "upper_back"])})
        k += 1
    return sorted(out, key=lambda c: c["t"])


def samples_from_events(events: list[dict[str, Any]], seed: int = 7, step_s: int = 60) -> list[dict[str, Any]]:
    """DEMO posture readings (one per `step_s`) consistent with the generated events, so the slouch
    fingerprint, fatigue, drift and setup-hint features have data. Synthetic: this person slouches
    mostly head-forward (about 70% of episodes), their neck angle creeps up the longer they sit, and
    their good posture drifts slightly further from the goal over the weeks."""
    rng = random.Random(seed + 2)
    trans = sorted((e for e in events if e["kind"] == "transition"), key=lambda e: e["t"])
    if not trans:
        return []
    first = trans[0]["t"]
    out: list[dict[str, Any]] = []
    run_start = first
    prev_state = AWAY
    kind = "head"
    for i, e in enumerate(trans):
        state = e["to_state"]
        if prev_state == AWAY and state != AWAY:
            run_start = e["t"]
        if state == SLOUCHING and prev_state != SLOUCHING:
            kind = "head" if rng.random() < 0.7 else "trunk"          # this episode's way of slouching
        prev_state = state
        end = trans[i + 1]["t"] if i + 1 < len(trans) else e["t"]
        if state == AWAY:
            continue
        days_in = (e["t"] - first) / DAY
        t = e["t"] + (step_s * 1000) // 2
        while t < end:
            mins = (t - run_start) / MIN
            fatigue = 0.04 * mins                                        # neck creeps forward the longer they sit
            drift = 0.002 * ((t - first) / DAY)                          # good posture drifts away from the goal
            if state == GOOD:
                row = (0.10 + drift + rng.uniform(-0.04, 0.04), 15 + fatigue + rng.gauss(0, 1.2), 5 + rng.gauss(0, 1.0), 0.18 + rng.gauss(0, 0.015))
            elif state == DEVIATING:
                row = (0.45 + rng.uniform(-0.05, 0.05), 22 + rng.gauss(0, 1.5), 9 + rng.gauss(0, 1.0), 0.30 + rng.gauss(0, 0.02))
            elif kind == "head":
                row = (0.70 + rng.uniform(-0.06, 0.06), 33 + rng.gauss(0, 2.0), 6 + rng.gauss(0, 1.5), 0.50 + rng.gauss(0, 0.03))
            else:
                row = (0.70 + rng.uniform(-0.06, 0.06), 18 + rng.gauss(0, 2.0), 20 + rng.gauss(0, 2.0), 0.22 + rng.gauss(0, 0.02))
            out.append({"t": int(t), "session_id": None, "state": state,
                        "label": "SLOUCHING" if state == SLOUCHING else "GOOD", "deviation": round(max(0.0, row[0]), 3),
                        "confidence": round(min(1.0, 0.9 + rng.uniform(-0.05, 0.05)), 2),
                        "neck": round(row[1], 2), "torso": round(row[2], 2), "head_fwd": round(max(0.0, row[3]), 3)})
            t += step_s * 1000
    return out
