import json
import re

import pytest

from api.core import coach_pack, posture_profile as pp, scoring, seedgen

H = 3_600_000
DAY = 86_400_000
NOW = 1_731_672_000_000


def row(state, n, neck=None, torso=None, head=None, dev=None, hour=NOW):
    return {"hour": hour, "state": state, "n": n, "avg_dev": dev, "avg_neck": neck, "avg_torso": torso, "avg_head_fwd": head}


GOOD = row("GOOD", 100, 16.0, 5.0, 0.19)


# --------------------------------------------------------------------------- fingerprint
def test_fingerprint_head_forward_dominates():
    rolls = [GOOD, row("SLOUCHING", 70, 33.0, 6.0, 0.50), row("SLOUCHING", 30, 17.0, 20.0, 0.20)]
    f = pp.fingerprint(rolls)
    assert f["headForwardPct"] == 70.0 and f["trunkLeanPct"] == 30.0 and f["otherPct"] == 0.0
    assert f["signature"] == "headForward" and f["samples"] == 100


def test_fingerprint_trunk_mixed_and_other():
    assert pp.fingerprint([GOOD, row("SLOUCHING", 100, 17.0, 20.0, 0.2)])["signature"] == "trunkLean"
    assert pp.fingerprint([GOOD, row("SLOUCHING", 50, 33.0, 6.0, 0.5), row("SLOUCHING", 50, 17.0, 20.0, 0.2)])["signature"] == "mixed"
    # barely different from good posture: "other", and never a confident signature
    other = pp.fingerprint([GOOD, row("SLOUCHING", 100, 17.0, 6.0, 0.21)])
    assert other["otherPct"] == 100.0 and other["signature"] == "mixed"


def test_fingerprint_needs_enough_samples_and_tolerates_missing_features():
    assert pp.fingerprint([GOOD, row("SLOUCHING", 10, 33.0, 6.0, 0.5)]) is None            # too few slouch samples
    assert pp.fingerprint([row("GOOD", 10, 16.0, 5.0, 0.19), row("SLOUCHING", 100, 33.0, 6.0, 0.5)]) is None
    partial = pp.fingerprint([GOOD, row("SLOUCHING", 100, neck=33.0)])                       # only the neck feature present
    assert partial["signature"] == "headForward"


# --------------------------------------------------------------------------- drift
def week_rows(weeks_ago, dev, n=200):
    return row("GOOD", n, dev=dev, hour=NOW - weeks_ago * 7 * DAY - H)


def test_posture_drift_flags_a_rising_good_state_deviation():
    rolls = [week_rows(3, 0.10), week_rows(2, 0.11), week_rows(1, 0.16), week_rows(0, 0.17)]
    d = pp.posture_drift(rolls, [{"t": NOW - 10 * DAY, "baseline": {}}], NOW)
    assert d["drifting"] and d["deltaDeviation"] == 0.06 and d["recalibrateSuggested"] and d["calibrationAgeDays"] == 10
    assert [w["weeksAgo"] for w in d["weekly"]] == [3, 2, 1, 0]                           # oldest first, no dates
    stable = pp.posture_drift([week_rows(3, 0.10), week_rows(2, 0.10), week_rows(1, 0.11), week_rows(0, 0.10)], [], NOW)
    assert stable["drifting"] is False and stable["recalibrateSuggested"] is False


def test_an_old_calibration_suggests_recalibrating_even_without_drift():
    d = pp.posture_drift([], [{"t": NOW - 50 * DAY, "baseline": {}}], NOW)
    assert d["drifting"] is False and d["recalibrateSuggested"] and d["calibrationAgeDays"] == 50
    assert pp.posture_drift([], [], NOW)["calibrationAgeDays"] is None


def test_thin_weeks_are_not_reported():
    d = pp.posture_drift([week_rows(1, 0.1, n=20), week_rows(0, 0.3, n=20)], [], NOW)
    assert d["weekly"] == [] and d["drifting"] is False


# --------------------------------------------------------------------------- exercises and hints
def test_exercise_library_is_consistent_and_recommendations_are_matched_and_capped():
    ids = [e["id"] for e in pp.EXERCISES]
    assert len(ids) == len(set(ids)) == len(pp.EXERCISE_IDS)
    assert all(e["steps"] and e["for"] for e in pp.EXERCISES) and pp.exercise_by_id("nope") is None
    assert pp.recommend_exercises("headForward", None, False) == ["chin_tuck", "shoulder_blade_squeeze"]
    assert pp.recommend_exercises("trunkLean", None, False) == ["doorway_stretch", "shoulder_blade_squeeze"]
    assert pp.recommend_exercises("headForward", 40, False) == ["chin_tuck", "shoulder_blade_squeeze", "stand_and_walk"]
    assert pp.recommend_exercises(None, None, True) == ["stand_and_walk"] and pp.recommend_exercises(None, None, False) == []
    assert all(len(pp.recommend_exercises(s, o, l)) <= 3 for s in (None, "headForward", "trunkLean", "mixed") for o in (None, 30) for l in (True, False))


def test_setup_hints_explain_why_they_were_picked():
    h = pp.setup_hints("headForward", 40, 60)
    assert [x["id"] for x in h] == ["screen", "break-timer"] and all(x["because"] for x in h)
    assert "40" in h[1]["detail"]
    assert [x["id"] for x in pp.setup_hints("trunkLean", None, 120)] == ["chair", "break-up-sits"]
    assert pp.setup_hints(None, None, 30) == []


# --------------------------------------------------------------------------- the pack, on the demo history
def demo_pack(days=42):
    events = seedgen.generate(days, NOW, 0, seed=7)
    samples = seedgen.samples_from_events(events, seed=7)
    off = 0
    today_idx = (NOW + off) // DAY
    since = (today_idx - days + 1) * DAY - off
    segs = scoring.build_segments(events, None, since, NOW)
    daily = scoring.fill_days(scoring.daily_breakdown(scoring.clip(segs, since, NOW), 0), today_idx - days + 1, today_idx)
    heat = scoring.heatmap(scoring.clip(segs, since, NOW), 0)
    # the same hourly rollup the stores produce (UTC hour, per state)
    groups = {}
    for s in samples:
        groups.setdefault(((s["t"] // H) * H, s["state"]), []).append(s)

    def avg(rows, k):
        v = [r[k] for r in rows if r.get(k) is not None]
        return sum(v) / len(v) if v else None

    rollups = [{"hour": h, "state": st, "n": len(rs), "avg_dev": avg(rs, "deviation"), "avg_neck": avg(rs, "neck"),
                "avg_torso": avg(rs, "torso"), "avg_head_fwd": avg(rs, "head_fwd")} for (h, st), rs in sorted(groups.items())]
    settings = {"slouchThresholdSec": 30, "cooldownSec": 120, "sensitivity": 0.5, "nudgeTone": "gentle"}
    cal = [{"t": NOW - 60 * DAY, "baseline": {}}]
    return coach_pack.build_pack(now_ms=NOW, tz_offset_min=0, window_days=days, segs=segs, events=events, daily=daily, heat=heat,
                                 rollups=rollups, settings=settings, calibrations=cal)


def test_the_pack_tells_the_demo_persons_story():
    p = demo_pack()
    assert p["schema"] == 1 and p["window"]["seatedHours"] > 100 and 0 < p["window"]["slouchPct"] < 60
    pat = p["patterns"]
    assert pat["fingerprint"]["signature"] == "headForward" and 55 <= pat["fingerprint"]["headForwardPct"] <= 85
    assert pat["fatigue"]["buckets"][0]["slouchPct"] is not None and len(pat["fatigue"]["buckets"]) == 13
    assert pat["dangerHours"] and pat["triggers"] and pat["setupHints"]
    assert pat["drift"]["calibrationAgeDays"] == 60 and pat["drift"]["recalibrateSuggested"]
    assert p["coaching"]["response"]["nudges"] > 50 and p["coaching"]["recoveryTrend"]
    assert p["habits"]["strength"]["consistencyPct"] is not None and p["habits"]["challenge"]["title"]
    assert p["workHours"] and p["workHours"]["startHour"] < p["workHours"]["endHour"]
    assert [e["id"] for e in p["exercises"]] and all(e["safety"] for e in p["exercises"])
    assert p["breaks"]["longestSitMin"] and p["breaks"]["breaksPerDay"] >= 0


def test_the_pack_is_deidentified_and_small():
    p = demo_pack()
    text = json.dumps(p)
    # no identity, no timestamps or dates, no health data (pain check-ins are never part of the pack)
    for banned in ("userId", "user_id", "token", "email", "weekStart", "date", "checkin", "session"):
        assert banned.lower() not in text.lower(), banned
    assert not re.search(r"\b1[67]\d{11}\b", text), "contains an epoch-ms timestamp"
    assert not re.search(r"\b20\d\d-\d\d-\d\d\b", text), "contains a calendar date"
    assert len(text) < 25_000
    slim = coach_pack.compact_for_ai(p)
    assert "exercises" not in slim and "steps" not in json.dumps(slim)
    # what is actually sent to Gemini carries NO pain/health data at all (the only "pain" in the full pack is
    # the exercise safety note shown in the UI, which is dropped from this payload)
    sent = json.dumps(slim).lower()
    for banned in ("pain", "checkin", "clinician", "userid", "token", "email", "session"):
        assert banned not in sent, banned
    assert {e["id"] for e in slim["exerciseLibrary"]} == set(pp.EXERCISE_IDS) and slim["recommendedByRules"]


def test_an_empty_history_yields_an_honest_empty_pack():
    p = coach_pack.build_pack(now_ms=NOW, tz_offset_min=0, window_days=42, segs=[], events=[], daily=[], heat=[], rollups=[],
                              settings={}, calibrations=[])
    assert p["window"]["seatedHours"] == 0 and p["patterns"]["fingerprint"] is None and p["patterns"]["dangerHours"] == []
    assert p["coaching"]["response"]["nudges"] == 0 and p["workHours"] is None and p["exercises"] == []
    assert p["coaching"]["alertFatigue"]["status"] == "insufficient" and p["habits"]["relapse"] == {"active": False}
