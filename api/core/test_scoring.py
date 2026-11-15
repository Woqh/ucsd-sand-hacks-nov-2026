from api.core.scoring import (
    DAY_MS, GOOD_THRESHOLD_PCT, Segment, avg_recovery_sec, build_segments, clip, daily_breakdown,
    day_streak, fill_days, heatmap, longest_good_streak, next_goal_pct, outlook, sitting_run_sec,
    split_at, summarize,
)

# 2024-11-14 00:00 UTC (a Thursday)
D0 = 1_731_542_400_000
MIN = 60_000


def ev(t_min, frm, to, alert=False, kind="transition"):
    return {"kind": kind, "t": D0 + t_min * MIN, "from_state": frm, "to_state": to, "alert": alert}


EVENTS = [
    ev(0, "AWAY", "GOOD"),
    ev(30, "GOOD", "DEVIATING"),
    ev(31, "DEVIATING", "SLOUCHING", alert=True),
    ev(35, "SLOUCHING", "GOOD"),
    ev(60, "GOOD", "AWAY"),
]


def test_build_segments_and_summary():
    segs = build_segments(EVENTS, None, D0, D0 + 120 * MIN)
    assert [(s.state, s.dur // MIN) for s in segs] == [
        ("GOOD", 30), ("DEVIATING", 1), ("SLOUCHING", 4), ("GOOD", 25), ("AWAY", 60)]
    s = summarize(segs, EVENTS, D0, D0 + 120 * MIN)
    assert s["seatedSec"] == 60 * 60
    assert s["slouchSec"] == 4 * 60
    assert s["goodPct"] == round(100 * 56 / 60, 1)     # grace (DEVIATING) counts as good
    assert s["score"] == 93
    assert s["slouchEvents"] == 1
    assert s["slouchEventsPerHour"] == 1.0
    assert s["avgRecoverySec"] == 4 * 60               # alert at :31 -> good at :35


def test_open_segment_stops_at_last_seen_then_away():
    evs = [ev(0, "AWAY", "GOOD")]                      # never closed (phone died)
    segs = build_segments(evs, None, D0, D0 + 100 * MIN, last_seen_ms=D0 + 10 * MIN)
    assert [(s.state, s.dur // MIN) for s in segs] == [("GOOD", 10), ("AWAY", 90)]


def test_live_phone_extends_the_open_segment_to_now():
    # last sample 400 ms ago: no sliver of AWAY at the end (regression: sitting time read 0)
    evs = [ev(0, "AWAY", "GOOD")]
    now = D0 + 30 * MIN
    segs = build_segments(evs, None, D0, now, last_seen_ms=now - 400)
    assert [(s.state, s.dur // MIN) for s in segs] == [("GOOD", 30)]
    assert sitting_run_sec(segs, now) == 30 * 60
    # but 20 s of silence does cut it
    segs = build_segments(evs, None, D0, now, last_seen_ms=now - 20_000)
    assert segs[-1].state == "AWAY" and segs[-1].dur == 20_000


def test_prior_event_gives_the_opening_state():
    segs = build_segments([ev(10, "GOOD", "AWAY")], ev(-5, "AWAY", "GOOD"), D0, D0 + 20 * MIN,
                          last_seen_ms=D0 + 10 * MIN)
    assert [(s.state, s.dur // MIN) for s in segs] == [("GOOD", 10), ("AWAY", 10)]


def test_no_events_means_away():
    segs = build_segments([], None, D0, D0 + 10 * MIN)
    assert [(s.state, s.dur // MIN) for s in segs] == [("AWAY", 10)]
    assert summarize(segs, [], D0, D0 + 10 * MIN)["score"] is None


def test_alert_kind_events_are_not_transitions():
    evs = EVENTS + [ev(33, "SLOUCHING", "SLOUCHING", alert=True, kind="alert")]
    segs = build_segments(evs, None, D0, D0 + 120 * MIN)
    assert len(segs) == 5
    s = summarize(segs, evs, D0, D0 + 120 * MIN)
    assert s["slouchEvents"] == 1


def test_recovery_skips_alerts_that_ended_in_away():
    evs = [ev(0, "AWAY", "SLOUCHING", alert=True), ev(5, "SLOUCHING", "AWAY"), ev(9, "AWAY", "GOOD")]
    assert avg_recovery_sec(evs) is None


def test_longest_streak_pauses_on_away_and_resets_on_slouch():
    segs = [Segment("GOOD", 0, 600_000), Segment("AWAY", 600_000, 900_000),
            Segment("GOOD", 900_000, 1_200_000), Segment("SLOUCHING", 1_200_000, 1_260_000),
            Segment("GOOD", 1_260_000, 1_300_000)]
    assert longest_good_streak(segs) == 900   # 10 min + 5 min across the away break


def test_split_at_day_boundaries_respects_timezone():
    # one segment from 22:00 to 02:00 UTC across midnight
    seg = Segment("GOOD", D0 + 22 * 60 * MIN - DAY_MS, D0 + 2 * 60 * MIN)
    parts = split_at([seg], DAY_MS, 0)
    assert [(i, p.dur // MIN) for i, p in parts] == [(D0 // DAY_MS - 1, 120), (D0 // DAY_MS, 120)]
    # UTC-8: that same span is 14:00 -> 18:00 local, one day
    parts = split_at([seg], DAY_MS, -8 * 60 * MIN)
    assert len(parts) == 1


def test_daily_breakdown_and_streak():
    def day(i, pct):  # seated 100 s, `pct` of it good
        base = D0 + i * DAY_MS
        return [Segment("GOOD", base, base + pct * 1000), Segment("SLOUCHING", base + pct * 1000, base + 100_000)]
    segs = sum([day(i, p) for i, p in [(-3, 80), (-2, 40), (-1, 75), (0, 90)]], [])
    daily = daily_breakdown(segs, 0)
    assert [d["score"] for d in daily] == [80, 40, 75, 90]
    today_idx = D0 // DAY_MS
    assert day_streak(daily, today_idx) == 2          # today + yesterday; the 40% day breaks it


def test_streak_does_not_break_on_in_progress_today():
    today_idx = D0 // DAY_MS
    daily = [{"dayIndex": today_idx - 1, "goodPct": 80.0}, {"dayIndex": today_idx, "goodPct": 50.0}]
    assert day_streak(daily, today_idx) == 1


def test_fill_days_adds_empty_days():
    daily = [{"date": "x", "dayIndex": 5, "seatedSec": 10, "goodPct": 50.0, "score": 50}]
    filled = fill_days(daily, 3, 6)
    assert [d["dayIndex"] for d in filled] == [3, 4, 5, 6]
    assert filled[0]["score"] is None and filled[2]["score"] == 50


def test_heatmap_weekday_and_hour():
    # D0 is a Thursday (Mon=0 -> Thu=3); 09:00-10:00 all good
    segs = [Segment("GOOD", D0 + 9 * 60 * MIN, D0 + 10 * 60 * MIN)]
    cells = heatmap(segs, 0)
    assert cells == [{"day": 3, "hour": 9, "seatedSec": 3600, "goodPct": 100.0}]


def test_next_goal_pct():
    assert next_goal_pct(None) == 60
    assert next_goal_pct(60) == 65
    assert next_goal_pct(62.4) == 65
    assert next_goal_pct(97) == 95


def test_sitting_run_resets_after_a_real_break():
    segs = [Segment("GOOD", 0, 3_600_000), Segment("AWAY", 3_600_000, 3_600_000 + 5 * MIN),
            Segment("GOOD", 3_600_000 + 5 * MIN, 3_600_000 + 35 * MIN)]
    assert sitting_run_sec(segs, 3_600_000 + 35 * MIN) == 30 * 60
    short_break = [Segment("GOOD", 0, 600_000), Segment("AWAY", 600_000, 660_000), Segment("GOOD", 660_000, 1_200_000)]
    assert sitting_run_sec(short_break, 1_200_000) == 1200
    assert sitting_run_sec([Segment("GOOD", 0, 10), Segment("AWAY", 10, 20)], 20) == 0


def test_clip():
    segs = [Segment("GOOD", 0, 100)]
    assert clip(segs, 20, 50) == [Segment("GOOD", 20, 50)]
    assert clip(segs, 200, 300) == []


def test_outlook():
    assert outlook(None)["status"] == "no_data"
    assert outlook(GOOD_THRESHOLD_PCT - 1)["status"] == "at_risk"
    assert outlook(GOOD_THRESHOLD_PCT)["status"] == "on_track"
