from api.core.state_machine import (
    AWAY, DEVIATING, GOOD, SLOUCHING, MAX_ALERTS_PER_EPISODE, Config, MachineState, Sample,
    describe, in_quiet_hours, step,
)

T0 = 1_731_628_800_000  # arbitrary epoch ms
CFG = Config(slouch_threshold_sec=10, cooldown_sec=60)


def S(sec, label="GOOD", dev=0.1, conf=0.95):
    return Sample(t=T0 + int(sec * 1000), label=label, deviation=dev, confidence=conf)


def good(sec): return S(sec, "GOOD", 0.1)
def bad(sec): return S(sec, "SLOUCHING", 0.8)
def away(sec): return S(sec, "AWAY", None)


def run(samples, cfg=CFG, state=None):
    m = state or MachineState()
    events = []
    for s in samples:
        m, ev = step(m, s, cfg)
        events += ev
    return m, events


def transitions(events):
    return [(e.from_state, e.to_state) for e in events if e.kind == "transition"]


def test_first_good_sample_appears_as_good():
    m, ev = run([good(0)])
    assert m.state == GOOD
    assert transitions(ev) == [(AWAY, GOOD)]
    assert ev[0].reason == "appeared"


def test_first_bad_sample_goes_straight_to_deviating():
    m, ev = run([bad(0)])
    assert m.state == DEVIATING
    assert transitions(ev) == [(AWAY, DEVIATING)]


def test_slouch_needs_the_user_threshold_and_alerts_once():
    m, ev = run([good(0)] + [bad(s) for s in range(1, 10)])
    assert m.state == DEVIATING          # 9 s of bad < 10 s threshold
    m, ev2 = step(m, bad(11), CFG)
    assert m.state == SLOUCHING
    assert [(e.to_state, e.alert, e.level) for e in ev2] == [(SLOUCHING, True, 1)]


def test_threshold_is_user_configurable():
    strict = Config(slouch_threshold_sec=3)
    m, ev = run([good(0), bad(1), bad(2), bad(4)], strict)
    assert m.state == SLOUCHING


def test_brief_good_blip_does_not_reset_the_slouch_timer():
    # hysteresis: 2 s of good (< RECOVER_SEC) between bad runs keeps the original timer
    m, _ = run([good(0), bad(1), bad(5), good(6), good(7), bad(8)])
    assert m.state == DEVIATING
    assert m.deviating_since == T0 + 1000
    m, ev = step(m, bad(12), CFG)
    assert m.state == SLOUCHING  # 12 - 1 = 11 s since the run began


def test_recovery_needs_sustained_good_and_is_stamped_when_they_sat_up():
    m, _ = run([good(0)] + [bad(s) for s in range(1, 13)])
    assert m.state == SLOUCHING
    m, ev = run([good(20), good(21), good(22)], state=m)
    assert m.state == SLOUCHING          # only 2 s good so far
    m, ev = step(m, good(23), CFG)
    assert m.state == GOOD
    assert ev[0].reason == "recovered" and ev[0].t == T0 + 20_000
    assert m.alerts_sent == 0 and m.deviating_since is None


def test_neutral_band_neither_slouches_nor_recovers():
    # sensitivity 0.5 -> bad >= 0.40, good <= 0.30; 0.35 is the dead-band
    mid = lambda s: S(s, "GOOD", 0.35)
    m, ev = run([good(0)] + [mid(s) for s in range(1, 40, 5)])
    assert m.state == GOOD and transitions(ev) == [(AWAY, GOOD)]
    m, _ = run([bad(0), mid(5), mid(20)])
    assert m.state == DEVIATING          # neutral doesn't promote to SLOUCHING...
    m, _ = run([bad(0), bad(5), mid(6), mid(20)])
    assert m.state == DEVIATING          # ...and doesn't count as recovery either


def test_sensitivity_moves_the_deviation_cutoff():
    sample = S(1, "SLOUCHING", 0.45)
    assert run([good(0), sample], Config(sensitivity=0.0))[0].state == GOOD       # forgiving: cutoff 0.60
    assert run([good(0), sample], Config(sensitivity=1.0))[0].state == DEVIATING  # strict: cutoff 0.20


def test_deviation_wins_over_label():
    # model says SLOUCHING but deviation is tiny -> the user's sensitivity decides
    m, _ = run([good(0), S(1, "SLOUCHING", 0.05)])
    assert m.state == GOOD


def test_low_confidence_and_unknown_are_ignored():
    m, ev = run([good(0), S(1, "SLOUCHING", 0.9, conf=0.2), S(2, "UNKNOWN", None)])
    assert m.state == GOOD and transitions(ev) == [(AWAY, GOOD)]


def test_away_is_debounced_then_clears_timers():
    m, _ = run([good(0), bad(1), bad(2)])
    assert m.state == DEVIATING
    m, ev = run([away(3), away(5)], state=m)
    assert m.state == DEVIATING          # 2 s away: not yet
    m, ev = run([away(9)], state=m)
    assert m.state == AWAY
    assert ev[0].reason == "left_frame" and ev[0].t == T0 + 3000  # stamped when they left
    assert m.deviating_since is None


def test_flicker_away_does_not_change_state():
    m, ev = run([good(0), away(1), away(2), good(3)])
    assert m.state == GOOD and transitions(ev) == [(AWAY, GOOD)]
    assert m.away_since is None


def test_away_pauses_timers_so_coming_back_restarts_the_grace_period():
    m, _ = run([good(0)] + [bad(s) for s in range(1, 9)] + [away(9), away(15)])
    assert m.state == AWAY
    m, ev = run([bad(20)], state=m)
    assert m.state == DEVIATING and m.deviating_since == T0 + 20_000
    m, _ = step(m, bad(25), CFG)
    assert m.state == DEVIATING          # 5 s since returning, not 24


def test_long_gap_closes_the_old_state_at_last_seen():
    m, ev = run([good(0), bad(1), bad(2)])
    m, ev = step(m, bad(500), CFG)       # phone slept for ~8 minutes
    assert transitions(ev)[0] == (DEVIATING, AWAY)
    assert ev[0].reason == "gap" and ev[0].t == T0 + 2000
    assert m.state == DEVIATING and m.deviating_since == T0 + 500_000


def test_out_of_order_sample_never_moves_time_backwards():
    m, _ = run([good(10)])
    m2, ev = step(m, bad(5), CFG)
    assert m2.last_t == m.last_t
    assert all(e.t >= m.last_t for e in ev)


def test_cooldown_blocks_repeat_alerts_then_escalates_if_still_slouching():
    cfg = Config(slouch_threshold_sec=5, cooldown_sec=60)
    m, ev = run([good(0)] + [bad(s) for s in range(1, 8)], cfg)
    assert [e.alert for e in ev if e.to_state == SLOUCHING] == [True]
    m, ev = run([bad(s) for s in range(8, 60)], cfg, m)
    assert not any(e.alert for e in ev)                        # still inside cooldown
    m, ev = run([bad(s) for s in range(60, 70)], cfg, m)
    assert [(e.kind, e.level) for e in ev if e.alert] == [("alert", 2)]


def test_escalation_stops_after_max_alerts_per_episode():
    cfg = Config(slouch_threshold_sec=5, cooldown_sec=15)
    m, ev = run([good(0)] + [bad(s) for s in range(1, 400)], cfg)
    assert sum(1 for e in ev if e.alert) == MAX_ALERTS_PER_EPISODE


def test_cooldown_spans_episodes():
    cfg = Config(slouch_threshold_sec=5, cooldown_sec=120)
    m, ev = run([good(0)] + [bad(s) for s in range(1, 8)], cfg)           # alert #1
    m, ev = run([good(s) for s in range(8, 14)], cfg, m)                  # sat up
    assert m.state == GOOD
    m, ev = run([bad(s) for s in range(14, 24)], cfg, m)                  # slouch again, 20 s later
    slouch = [e for e in ev if e.to_state == SLOUCHING]
    assert slouch and slouch[0].alert is False                            # no spam
    m, ev = run([bad(s) for s in range(24, 131)], cfg, m)                 # keep slouching past the cooldown
    alerts = [e for e in ev if e.alert]
    assert [(e.kind, e.level, e.t) for e in alerts] == [("alert", 1, T0 + 126_000)]  # new episode -> level 1


def test_no_alert_when_both_channels_off():
    cfg = Config(slouch_threshold_sec=5, alert_phone=False, alert_desktop=False)
    m, ev = run([good(0)] + [bad(s) for s in range(1, 10)], cfg)
    assert m.state == SLOUCHING and not any(e.alert for e in ev)


def test_quiet_hours_suppress_alert_but_not_state():
    # tz_offset 0 -> local == UTC. T0 is 2024-11-15 00:00 UTC, i.e. inside 22:00-07:00.
    cfg = Config(slouch_threshold_sec=5, quiet_hours_enabled=True)
    assert in_quiet_hours(T0, cfg)
    m, ev = run([good(0)] + [bad(s) for s in range(1, 10)], cfg)
    assert m.state == SLOUCHING and not any(e.alert for e in ev)


def test_quiet_hours_window_and_timezone():
    cfg = Config(quiet_hours_enabled=True, quiet_start_min=22 * 60, quiet_end_min=7 * 60)
    noon_utc = T0 + 12 * 3600_000
    assert not in_quiet_hours(noon_utc, cfg)
    assert in_quiet_hours(noon_utc, Config(quiet_hours_enabled=True, quiet_start_min=22 * 60,
                                           quiet_end_min=7 * 60, tz_offset_min=-12 * 60 - 60))  # local 23:00? no: 11:00
    # same-day window (e.g. 12:00-13:00)
    lunch = Config(quiet_hours_enabled=True, quiet_start_min=12 * 60, quiet_end_min=13 * 60)
    assert in_quiet_hours(noon_utc + 30 * 60_000, lunch)
    assert not in_quiet_hours(noon_utc + 90 * 60_000, lunch)


def test_step_is_pure_and_state_roundtrips():
    m0 = MachineState()
    m1, _ = step(m0, good(0), CFG)
    assert m0.state == AWAY and m1.state == GOOD
    assert MachineState.from_dict(m1.to_dict()) == m1
    assert MachineState.from_dict(None) == MachineState()


def test_describe_reports_time_in_state_and_cooldown():
    cfg = Config(slouch_threshold_sec=5, cooldown_sec=60)
    m, _ = run([good(0)] + [bad(s) for s in range(1, 8)], cfg)
    d = describe(m, T0 + 20_000, cfg)
    assert d["state"] == SLOUCHING and d["inCooldown"] is True
    assert d["deviatingForSec"] == 19.0


def test_focus_mode_only_nudges_inside_a_focus_session():
    inside = Config(slouch_threshold_sec=5, focus_only=True, focus_until_ms=T0 + 60_000)
    m, ev = run([good(0)] + [bad(s) for s in range(1, 10)], inside)
    assert m.state == SLOUCHING and any(e.alert for e in ev)                  # the session is running: nudge
    expired = Config(slouch_threshold_sec=5, focus_only=True, focus_until_ms=T0)
    m, ev = run([good(0)] + [bad(s) for s in range(1, 10)], expired)
    assert m.state == SLOUCHING and not any(e.alert for e in ev)              # state still tracked, no nudge
    none_started = Config(slouch_threshold_sec=5, focus_only=True)            # focus mode on, no session started
    assert not any(e.alert for e in run([good(0)] + [bad(s) for s in range(1, 10)], none_started)[1])
    off = Config(slouch_threshold_sec=5, focus_only=False, focus_until_ms=0)
    assert any(e.alert for e in run([good(0)] + [bad(s) for s in range(1, 10)], off)[1])


def test_a_nudge_held_back_by_focus_mode_fires_when_a_session_starts():
    # slouching started outside focus; the user starts a session later while still slouching
    cfg_off = Config(slouch_threshold_sec=5, focus_only=True, focus_until_ms=0)
    m, ev = run([good(0)] + [bad(s) for s in range(1, 10)], cfg_off)
    assert not any(e.alert for e in ev)
    cfg_on = Config(slouch_threshold_sec=5, focus_only=True, focus_until_ms=T0 + 120_000)
    m, ev = run([bad(s) for s in range(10, 14)], cfg_on, m)
    assert [(e.kind, e.level) for e in ev if e.alert] == [("alert", 1)]
