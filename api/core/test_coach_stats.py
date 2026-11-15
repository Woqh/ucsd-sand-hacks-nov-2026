import pytest

from api.core import coach_stats as cs
from api.core.scoring import Segment
from api.core.settings import merge_settings

MIN = 60_000
SEC = 1_000
HOUR = 3_600_000
DAY = 86_400_000
MON = 1_731_283_200_000          # Monday 2024-11-11 00:00 UTC


def seg(state, a_min, b_min, base=0):
    return Segment(state, base + int(a_min * MIN), base + int(b_min * MIN))


# --------------------------------------------------------------------------- runs
def test_seated_runs_absorb_short_gaps_and_split_on_long_ones():
    segs = [seg("GOOD", 0, 30), seg("AWAY", 30, 31), seg("SLOUCHING", 31, 50), seg("AWAY", 50, 55), seg("GOOD", 55, 70)]
    runs = cs.seated_runs(segs)
    assert [(r.start // MIN, r.end // MIN) for r in runs] == [(0, 50), (55, 70)]
    assert runs[0].seated_sec == 49 * 60 and runs[0].minutes == 50
    assert cs.seated_runs([seg("AWAY", 0, 100)]) == []


# --------------------------------------------------------------------------- fatigue / onset
def run_of(good_min, slouch_min, base=0):
    return [seg("GOOD", 0, good_min, base), seg("SLOUCHING", good_min, good_min + slouch_min, base)]


def test_fatigue_curve_finds_when_posture_slips():
    segs = []
    for i in range(4):                                    # four 60-min sits: good for 40 min, then slouching
        base = i * 3 * HOUR
        segs += run_of(40, 20, base)
        segs.append(Segment("AWAY", base + 60 * MIN, base + 3 * HOUR))
    curve = cs.fatigue_curve(cs.seated_runs(segs))
    b = curve["buckets"]
    assert b[0]["slouchPct"] == 0 and b[3]["slouchPct"] == 0 and b[4]["slouchPct"] == 100 and b[5]["slouchPct"] == 100
    assert curve["baselinePct"] == 0 and curve["onsetMin"] == 40
    assert b[0]["runs"] == 4 and b[6]["runs"] == 0 and b[0]["minTo"] == 10 and b[-1]["minTo"] is None


def test_fatigue_curve_reports_nothing_when_there_is_no_slip_or_too_little_data():
    steady = [seg("GOOD", 0, 60), seg("AWAY", 60, 200), seg("GOOD", 200, 260)]
    assert cs.fatigue_curve(cs.seated_runs(steady))["onsetMin"] is None
    thin = cs.fatigue_curve(cs.seated_runs([seg("GOOD", 0, 8)]))
    assert thin["baselinePct"] is None and thin["onsetMin"] is None            # under 10 min of early data
    assert all(x["slouchPct"] is None for x in thin["buckets"][1:])


def test_onset_latency_is_the_median_time_to_first_slouch():
    segs = []
    for i in range(6):
        base = i * 3 * HOUR
        segs += [seg("GOOD", 0, 20, base), seg("SLOUCHING", 20, 25, base), Segment("AWAY", base + 25 * MIN, base + 3 * HOUR)]
    out = cs.onset_latency(cs.seated_runs(segs))
    assert out["medianSec"] == 1200 and out["runsWithSlouchPct"] == 100.0 and out["runs"] == 6
    assert cs.onset_latency(cs.seated_runs(segs[:6]))["medianSec"] is None      # only 2 runs


# --------------------------------------------------------------------------- when
def test_danger_hours_rank_the_worst_hours_against_the_persons_own_average():
    cells = [{"day": 1, "hour": 15, "seatedSec": 3600, "goodPct": 50.0}, {"day": 3, "hour": 10, "seatedSec": 3600, "goodPct": 80.0},
             {"day": 2, "hour": 16, "seatedSec": 600, "goodPct": 10.0},       # too little data
             {"day": 4, "hour": 14, "seatedSec": 3600, "goodPct": 60.0}, {"day": 0, "hour": 9, "seatedSec": 3600, "goodPct": None}]
    out = cs.danger_hours(cells, overall_slouch_pct=20.0)
    assert [(d["day"], d["hour"], d["slouchPct"]) for d in out] == [(1, 15, 50.0), (4, 14, 40.0)]
    assert cs.danger_hours(cells, None) == []


def test_triggers_are_plain_language_with_numbers():
    fatigue = {"onsetMin": 40}
    hours = [{"day": 1, "hour": 15, "slouchPct": 50.0, "seatedMin": 60}]
    wk = {1: {"slouchPct": 45.0, "seatedMin": 300}, 2: {"slouchPct": 22.0, "seatedMin": 300}}
    out = cs.triggers(fatigue, hours, wk, 20.0)
    kinds = {t["kind"]: t["label"] for t in out}
    assert "40 minutes" in kinds["sit_length"] and "Tuesday around 3 PM" in kinds["time_of_day"] and "Tuesdays" in kinds["weekday"]
    assert cs.triggers({"onsetMin": None}, [], {}, None) == []


# --------------------------------------------------------------------------- nudges
def ev(t_sec, to, alert=False, level=0, kind="transition"):
    return {"t": 10 * HOUR + t_sec * SEC, "kind": kind, "to_state": to, "alert": alert, "level": level}


def test_resolve_nudges_pairs_each_alert_with_what_happened_next():
    events = [ev(0, "SLOUCHING", True, 1), ev(20, "GOOD"),                       # recovered in 20 s
             ev(100, "SLOUCHING", True, 1), ev(130, "AWAY"),                      # walked away
             ev(300, "SLOUCHING", True, 1), ev(400, "SLOUCHING", True, 2, kind="alert"), ev(430, "GOOD"),   # escalation
             ev(900, "SLOUCHING", True, 1)]                                       # unresolved at the end
    out = cs.resolve_nudges(events)
    assert [(r["level"], r["outcome"], r["sec"]) for r in out] == [(1, "recovered", 20.0), (1, "left", None),
                                                                   (1, "recovered", 130.0), (2, "recovered", 30.0)]


def rows(secs, level=1, part_hour=10):
    return [{"t": part_hour * HOUR + i * HOUR // 100, "level": level, "outcome": "recovered", "sec": s} for i, s in enumerate(secs)]


def test_nudge_response_rates_and_groups():
    resolved = rows([5, 10, 12, 14, 20, 28, 35, 45, 59, 200])
    resolved += [{"t": 10 * HOUR, "level": 1, "outcome": "left", "sec": None}]
    r = cs.nudge_response(resolved, tz_offset_min=0)
    assert r["nudges"] == 11 and r["recovered"] == 10 and r["leftAfterNudge"] == 1
    assert (r["within15Pct"], r["within30Pct"], r["within60Pct"]) == (40.0, 60.0, 90.0) and r["medianRecoverySec"] == 24.0
    assert r["byLevel"][0]["n"] == 10 and r["byLevel"][1]["within30Pct"] is None            # under 3 nudges: no rate
    morning = next(p for p in r["byPartOfDay"] if p["part"] == "morning")
    assert morning["n"] == 10 and next(p for p in r["byPartOfDay"] if p["part"] == "evening")["within30Pct"] is None


def test_part_of_day_uses_local_time():
    t = 23 * HOUR                                          # 23:00 UTC
    assert cs.part_of_day(cs.local_hour(t, 0)) == "evening"
    assert cs.part_of_day(cs.local_hour(t, -9 * 60)) == "afternoon"            # 14:00 local


def test_recovery_trend_is_per_week_oldest_first_without_dates():
    now = 100 * DAY
    resolved = [{"t": now - 1 * DAY, "level": 1, "outcome": "recovered", "sec": s} for s in (10, 20, 30)]
    resolved += [{"t": now - 10 * DAY, "level": 1, "outcome": "recovered", "sec": s} for s in (60, 70, 80)]
    resolved += [{"t": now - 20 * DAY, "level": 1, "outcome": "recovered", "sec": 5}]      # too few to report
    assert cs.recovery_trend(resolved, now) == [{"weeksAgo": 1, "avgRecoverySec": 70.0, "n": 3},
                                                {"weeksAgo": 0, "avgRecoverySec": 20.0, "n": 3}]


def test_alert_fatigue_compares_older_and_newer_halves():
    def mk(quick_flags):
        return [{"t": i, "level": 1, "outcome": "recovered", "sec": 10 if q else 90} for i, q in enumerate(quick_flags)]
    fatigued = cs.alert_fatigue(mk([True] * 12 + [True] * 6 + [False] * 6))
    assert fatigued["status"] == "fatigued" and fatigued["firstHalfPct"] == 100.0 and fatigued["secondHalfPct"] == 50.0
    assert cs.alert_fatigue(mk([True] * 24))["status"] == "ok"
    assert cs.alert_fatigue(mk([True] * 12 + [True] * 11 + [False] * 1))["status"] == "watch"   # 100 -> 91.7: an 8-point dip
    assert cs.alert_fatigue(mk([True] * 13 + [True] * 12 + [False] * 1))["status"] == "ok"      # 100 -> 92.3: under 8 points
    assert cs.alert_fatigue(mk([True] * 5))["status"] == "insufficient"


def test_setting_suggestions_are_data_backed_and_valid_patches():
    base = {"slouchThresholdSec": 30, "cooldownSec": 120, "sensitivity": 0.5}
    quick = cs.nudge_response(rows([10] * 12), 0)                                        # responds fast to level-1 nudges
    s = cs.setting_suggestions(quick, {"status": "ok"}, base, seated_hours=20, slouch_pct=20)
    assert [x["id"] for x in s] == ["shorter-threshold"] and s[0]["patch"] == {"slouchThresholdSec": 20}

    naggy = cs.nudge_response(rows([90] * 12), 0)                                        # slow to respond, nudged a lot
    s = cs.setting_suggestions(naggy, {"status": "ok"}, base, seated_hours=1, slouch_pct=20)
    assert s and s[0]["id"] == "longer-threshold" and s[0]["patch"] == {"slouchThresholdSec": 45}

    s = cs.setting_suggestions(cs.nudge_response([], 0), {"status": "fatigued", "firstHalfPct": 90.0, "secondHalfPct": 40.0},
                               base, seated_hours=20, slouch_pct=30)
    assert {x["id"] for x in s} == {"fatigue-cooldown", "more-sensitive"}
    cool = next(x for x in s if x["id"] == "fatigue-cooldown")
    assert cool["patch"] == {"cooldownSec": 180}
    # every suggestion must be something the settings API will actually accept
    for x in s:
        merged, errors = merge_settings(None, x["patch"])
        assert not errors, (x["id"], errors)
    assert cs.setting_suggestions(quick, {"status": "ok"}, {**base, "slouchThresholdSec": 15}, 20, 20) == []   # already short


# --------------------------------------------------------------------------- habits
def day(idx, pct, seated=3600):
    return {"dayIndex": idx, "goodPct": pct, "score": None if pct is None else round(pct), "seatedSec": seated if pct is not None else 0}


def test_habit_strength_consistency_and_forgiving_streak():
    pcts = [75, 75, 75, 60, 75, 75, 75, 75, 75, 60, 75, 75, 75, 75]
    daily = [day(i, p) for i, p in enumerate(pcts)]
    h = cs.habit_strength(daily, today_idx=13)
    assert h["daysWithData"] == 14 and h["daysAtTarget"] == 12 and h["consistencyPct"] == 85.7
    # walking back: 4 good days, the day-9 miss uses the weekly freeze, 5 more good days, then the day-3 miss
    # is within 7 days of the last forgiven one, so the streak ends: 4 + 5 = 9. A strict streak stops at day 9.
    assert h["forgivingStreak"] == 9 and h["strictStreak"] == 4
    # today in progress and below target never counts against the streak
    assert cs.habit_strength(daily[:13] + [day(13, 50)], 13)["forgivingStreak"] == 8    # day 13 ignored; 3 + freeze + 5
    assert cs.habit_strength([day(0, 80), day(1, 80)], 1)["consistencyPct"] is None      # under 5 days of data


def test_today_in_progress_does_not_break_the_forgiving_streak():
    daily = [day(i, 80) for i in range(6)] + [day(6, 40)]
    assert cs.habit_strength(daily, today_idx=6)["forgivingStreak"] == 6


def test_bests():
    daily = [day(i, p) for i, p in enumerate([60, 80, 90, 85, 70, 65, 95, 40])]
    segs = [Segment("GOOD", 0, 25 * MIN)]
    b = cs.bests(daily, segs)
    assert b["bestDayScore"] == 95 and b["longestDayStreak"] == 4 and b["longestGoodStretchMin"] == 25
    assert b["bestWeekScore"] is not None and 70 <= b["bestWeekScore"] <= 95


def test_relapse_needs_a_good_stretch_then_three_bad_days():
    good = [day(i, 80) for i in range(7)]
    bad = [day(7, 50), day(8, 55), day(9, 52)]
    r = cs.relapse(good + bad + [day(10, 30)], today_idx=10)                  # day 10 is in progress
    assert r["active"] and r["smallerGoalPct"] == 57 and "smaller win" in r["message"]            # (50+55+52)/3 + 5, rounded
    assert cs.relapse([day(i, 50) for i in range(10)], today_idx=10)["active"] is False     # never had a good stretch
    assert cs.relapse(good, today_idx=7)["active"] is False


def test_challenge_is_sized_from_the_persons_data():
    c = cs.challenge([{"day": 3, "hour": 14, "slouchPct": 41.0}], 20.0, 70)
    assert "Thursday 2 PM" in c["title"] and "41%" in c["detail"]
    assert cs.challenge([], None, 65)["title"] == "Reach 65% good posture this week"


# --------------------------------------------------------------------------- breaks, workday
def test_break_quality():
    segs = []
    for i in range(6):                                    # six sits: 30, 60, 90, 30, 30, 120 minutes
        base = i * 4 * HOUR
        segs += [seg("GOOD", 0, [30, 60, 90, 30, 30, 120][i], base), Segment("AWAY", base + [30, 60, 90, 30, 30, 120][i] * MIN, base + 4 * HOUR)]
    segs.append(Segment("AWAY", 0, 0))
    segs += [Segment("AWAY", 30 * HOUR, 30 * HOUR + 30 * SEC)]                 # a 30-second micro-break
    runs = cs.seated_runs(segs)
    q = cs.break_quality(runs, segs, active_days=3)
    assert q["longestSitMin"] == 120 and q["avgSitMin"] == 60 and q["runsOverTargetPct"] == 50.0
    assert q["breaksPerDay"] == 2.0 and q["microBreaksPerDay"] == 0.3


def test_work_hours_are_inferred_from_weekdays_only():
    segs = []
    for d in range(7):                                    # Mon..Sun, 09:00-17:00 each day
        segs.append(Segment("GOOD", MON + d * DAY + 9 * HOUR, MON + d * DAY + 17 * HOUR))
    w = cs.work_hours(segs, 0)
    assert w == {"startHour": 9.0, "endHour": 17.0, "days": 5}                  # the weekend is ignored
    assert cs.work_hours(segs[:4], 0) is None                                  # fewer than 5 weekdays
    # a UTC-8 viewer sees the same sessions as 01:00-09:00 local
    assert cs.work_hours(segs, -8 * 60)["startHour"] == 1.0
