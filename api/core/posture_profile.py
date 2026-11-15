"""The shape of how THIS person slouches, from the downsampled posture readings. Pure.

Input is the hourly per-state rollup (`store.sample_rollup`): rows of {hour, state, n, avg_dev,
avg_neck, avg_torso, avg_head_fwd}. The slouch "fingerprint" asks which feature moves most away from
the person's OWN good-posture average when they slouch: head forward, or the trunk leaning forward.

ASSUMED CONVENTION (flagged; confirm with the model teammate): for all three features a LARGER value
is further forward / worse, as in the example payloads (good about 16 / 5.5 / 0.19, slouched about
34 / 18 / 0.52). The normalising scales below are product constants tied to that assumption.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from api.core.state_machine import GOOD, SLOUCHING

NECK_SCALE, TORSO_SCALE, HEAD_SCALE = 10.0, 10.0, 0.2   # "one unit" of change per feature
MIN_GOOD_SAMPLES, MIN_SLOUCH_SAMPLES = 50, 30
DEEP_ENOUGH = 0.5                                       # normalised change below this = not a clear pattern
WEEK_MS = 7 * 86_400_000
MIN_DRIFT_WEEKS, MIN_WEEK_SAMPLES, DRIFT_DELTA = 4, 100, 0.05
RECALIBRATE_AFTER_DAYS = 45

# ---------------------------------------------------------------------------- exercises (instructions only)
# A small vetted library the Gemini analysis may only SELECT from (it can't invent exercises). These are
# generic mobility instructions with no outcome claims; have a clinician/PT review the wording before a
# real release (docs/health-claims.md).
EXERCISES: list[dict[str, Any]] = [
    {"id": "chin_tuck", "title": "Chin tucks", "for": ["headForward"],
     "steps": ["Sit tall.", "Glide your head straight back, as if making a double chin.", "Hold for 5 seconds, then release.", "Repeat 5 times."]},
    {"id": "doorway_stretch", "title": "Doorway chest stretch", "for": ["trunkLean"],
     "steps": ["Rest your forearm on a doorframe.", "Step through gently until you feel a stretch across your chest.", "Hold 20 to 30 seconds each side."]},
    {"id": "shoulder_blade_squeeze", "title": "Shoulder-blade squeezes", "for": ["headForward", "trunkLean"],
     "steps": ["Sit tall with your arms relaxed.", "Gently squeeze your shoulder blades together and down.", "Hold for 5 seconds, then release.", "Repeat 5 times."]},
    {"id": "stand_and_walk", "title": "Stand-and-walk break", "for": ["fatigue", "longSits"],
     "steps": ["Stand up and walk for a minute or two.", "Roll your shoulders and reach overhead.", "Come back and reset your seat."]},
]
SAFETY_NOTE = "Stop if anything hurts, and talk to a clinician about ongoing pain."
EXERCISE_IDS = [e["id"] for e in EXERCISES]


def exercise_by_id(ex_id: str) -> Optional[dict[str, Any]]:
    return next((e for e in EXERCISES if e["id"] == ex_id), None)


def recommend_exercises(signature: Optional[str], fatigue_onset_min: Optional[int], long_sits: bool) -> list[str]:
    """At most 3 exercise ids, matched to the person's own pattern."""
    ids: list[str] = []
    if signature == "headForward":
        ids += ["chin_tuck", "shoulder_blade_squeeze"]
    elif signature == "trunkLean":
        ids += ["doorway_stretch", "shoulder_blade_squeeze"]
    elif signature == "mixed":
        ids += ["chin_tuck", "doorway_stretch"]
    if fatigue_onset_min is not None or long_sits:
        ids.append("stand_and_walk")
    return ids[:3]


# ---------------------------------------------------------------------------- fingerprint
def _weighted_mean(rows: Sequence[dict[str, Any]], key: str) -> Optional[float]:
    num = den = 0.0
    for r in rows:
        v = r.get(key)
        if v is not None and r["n"] > 0:
            num += v * r["n"]
            den += r["n"]
    return num / den if den else None


def fingerprint(rollups: Sequence[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Which way does this person slouch? Percent of slouching time that is head-forward, trunk-lean or
    neither (`other`), measured against their own good-posture average. None without enough data."""
    good = [r for r in rollups if r["state"] == GOOD]
    slouch = [r for r in rollups if r["state"] == SLOUCHING]
    if sum(r["n"] for r in good) < MIN_GOOD_SAMPLES or sum(r["n"] for r in slouch) < MIN_SLOUCH_SAMPLES:
        return None
    ref = {k: _weighted_mean(good, k) for k in ("avg_neck", "avg_torso", "avg_head_fwd")}
    weights = {"headForward": 0.0, "trunkLean": 0.0, "other": 0.0}
    for r in slouch:
        def delta(key: str, scale: float) -> float:
            v, base = r.get(key), ref[key]
            return 0.0 if v is None or base is None else (v - base) / scale

        head = max(delta("avg_neck", NECK_SCALE), delta("avg_head_fwd", HEAD_SCALE))
        trunk = delta("avg_torso", TORSO_SCALE)
        kind = "other" if max(head, trunk) < DEEP_ENOUGH else ("headForward" if head >= trunk else "trunkLean")
        weights[kind] += r["n"]
    total = sum(weights.values())
    pct = {k: round(100 * v / total, 1) for k, v in weights.items()}
    top = max(weights, key=lambda k: weights[k])
    signature = top if pct[top] >= 60 and top != "other" else "mixed"
    return {"headForwardPct": pct["headForward"], "trunkLeanPct": pct["trunkLean"], "otherPct": pct["other"],
            "samples": int(total), "signature": signature}


# ---------------------------------------------------------------------------- drift
def posture_drift(rollups: Sequence[dict[str, Any]], calibrations: Sequence[dict[str, Any]], now_ms: int) -> dict[str, Any]:
    """Has the person's GOOD posture moved away from their goal? Weekly average deviation while in the
    GOOD state (oldest first), and whether the newest weeks are meaningfully worse than the oldest."""
    weeks: dict[int, list[float]] = {}                   # weeksAgo -> [sum(dev*n), n]
    for r in rollups:
        if r["state"] != GOOD or r.get("avg_dev") is None:
            continue
        w = max(0, int((now_ms - r["hour"]) // WEEK_MS))
        a = weeks.setdefault(w, [0.0, 0.0])
        a[0] += r["avg_dev"] * r["n"]
        a[1] += r["n"]
    series = [{"weeksAgo": w, "avgDeviation": round(v[0] / v[1], 3), "n": int(v[1])}
              for w, v in sorted(weeks.items(), reverse=True) if v[1] >= MIN_WEEK_SAMPLES]
    cal_age = None
    if calibrations:
        cal_age = int((now_ms - max(c["t"] for c in calibrations)) // 86_400_000)
    out: dict[str, Any] = {"weekly": series, "drifting": False, "deltaDeviation": None,
                           "calibrationAgeDays": cal_age, "recalibrateSuggested": False}
    if len(series) >= MIN_DRIFT_WEEKS:
        old = sum(s["avgDeviation"] for s in series[:2]) / 2
        new = sum(s["avgDeviation"] for s in series[-2:]) / 2
        out["deltaDeviation"] = round(new - old, 3)
        out["drifting"] = (new - old) >= DRIFT_DELTA
    out["recalibrateSuggested"] = out["drifting"] or (cal_age is not None and cal_age >= RECALIBRATE_AFTER_DAYS)
    return out


# ---------------------------------------------------------------------------- setup hints
def setup_hints(signature: Optional[str], fatigue_onset_min: Optional[int], longest_sit_min: Optional[int]) -> list[dict[str, str]]:
    """Ergonomic checklist items chosen by the person's own pattern. These are generic suggestions: we
    don't measure the desk, so each says why it was picked."""
    hints: list[dict[str, str]] = []
    if signature == "headForward":
        hints.append({"id": "screen", "title": "Check your screen height and distance",
                      "detail": "Raise the screen so the top is about at eye level and sit about an arm's length away, so your head isn't pulled forward.",
                      "because": "Your slouching is mostly your head drifting forward."})
    if signature == "trunkLean":
        hints.append({"id": "chair", "title": "Check your chair support",
                      "detail": "Sit back into the backrest with your lower back supported and your feet flat on the floor.",
                      "because": "Your slouching is mostly your upper body leaning forward."})
    if fatigue_onset_min is not None:
        hints.append({"id": "break-timer", "title": "Set a movement reminder before your usual drop-off",
                      "detail": f"Stand up a few minutes before the {fatigue_onset_min}-minute mark, which is when your posture tends to slip.",
                      "because": f"Your posture slips after about {fatigue_onset_min} minutes of sitting."})
    elif longest_sit_min is not None and longest_sit_min > 90:
        hints.append({"id": "break-up-sits", "title": "Break up your longest sits",
                      "detail": "Your longest stretch without a break is long. A quick stand-up between tasks resets your posture.",
                      "because": f"Your longest unbroken sit was about {longest_sit_min} minutes."})
    return hints
