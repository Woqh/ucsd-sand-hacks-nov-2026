from api.core import calibration_feed as cf

NOW = 1_700_000_000_000


def feed(angles, step=1000, ok=True, neck=None, head=None, start=NOW):
    recent = []
    for i, a in enumerate(angles):
        recent = cf.push_recent(recent, start + i * step, ok, {"torsoAngle": a, **({"neckAngle": neck} if neck is not None else {}),
                                                                 **({"headForwardOffset": head} if head is not None else {})})
    return recent


def test_a_steady_comfortable_posture_becomes_the_goal():
    r = cf.baseline_from_recent(feed([5.0, 5.2, 4.8, 5.1, 4.9, 5.0, 5.3, 4.7, 5.0, 5.0], neck=14.0, head=0.2), NOW + 10_000)
    assert r["accepted"] and r["issues"] == []
    assert r["goal"] == {"torsoAngle": 5.0, "neckAngle": 14.0, "headForwardOffset": 0.2}
    assert r["tolerance"] >= 4.0 and r["capturedAt"] == NOW + 10_000


def test_only_the_last_countdown_counts():
    # 30 s of slouching, then 10 s of steady good posture: the baseline is the good part
    recent = feed([20.0] * 20 + [5.0] * 11)
    r = cf.baseline_from_recent(recent, NOW + 31_000)
    assert r["accepted"] and r["goal"]["torsoAngle"] == 5.0


def test_moving_around_is_refused_with_a_reason():
    r = cf.baseline_from_recent(feed([0.0, 12.0, 2.0, 14.0, 1.0, 13.0, 3.0, 12.0, 0.0, 14.0]), NOW)
    assert not r["accepted"]
    assert any("moved around" in i for i in r["issues"])
    assert r["tolerance"] == 10.0          # clamped


def test_not_being_seen_is_refused():
    r = cf.baseline_from_recent(feed([5.0] * 10, ok=False), NOW)
    assert not r["accepted"] and r["goal"] == {}
    assert any("couldn't see you" in i for i in r["issues"])


def test_a_mostly_unseen_window_is_refused_even_if_a_few_readings_are_fine():
    recent = []
    for i in range(10):
        recent = cf.push_recent(recent, NOW + i * 1000, i < 4, {"torsoAngle": 5.0})   # 4 usable of 10
    r = cf.baseline_from_recent(recent, NOW)
    assert not r["accepted"]


def test_too_few_readings_is_refused():
    r = cf.baseline_from_recent(feed([5.0, 5.0, 5.0]), NOW)
    assert not r["accepted"]


def test_optional_features_are_left_out_unless_most_readings_have_them():
    recent = []
    for i in range(10):
        f = {"torsoAngle": 5.0}
        if i < 3:
            f["neckAngle"] = 20.0
        recent = cf.push_recent(recent, NOW + i * 1000, True, f)
    assert "neckAngle" not in cf.baseline_from_recent(recent, NOW)["goal"]


def test_push_recent_is_bounded_and_drops_old_readings():
    recent = feed([5.0] * 100, step=1000)
    assert len(recent) <= cf.RECENT_MAX
    assert min(e[0] for e in recent) >= NOW + 99_000 - cf.RECENT_KEEP_MS


def test_entries_are_json_safe():
    import json
    assert json.loads(json.dumps(feed([5.0, 6.0], neck=1.0)))[0][4] is True


def test_liveness_needs_readings_and_a_recent_device():
    recent = feed([5.0])
    assert cf.is_live(recent, NOW, NOW + 5_000)
    assert not cf.is_live(recent, NOW, NOW + 60_000)
    assert not cf.is_live([], NOW, NOW)
    assert not cf.is_live(recent, None, NOW)
