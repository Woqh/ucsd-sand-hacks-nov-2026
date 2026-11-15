"""The real model streams to /posture/ingest (bridge/); the dashboard's calibration and the model-health
route use that live feed, and fall back to the stub when nothing is streaming. Runs on every store."""
import pytest

from api.tests.test_api import SID, T0, auth, env, paired, sample  # noqa: F401  (env is a fixture)

FEATURES_GOOD = {"torsoAngle": 4.0, "neckAngle": 12.0}


def stream(client, token, clock, seconds, label="GOOD", dev=0.1, features=None, confidence=0.95, **extra):
    """Post one reading per second like the bridge does."""
    for _ in range(seconds):
        clock["t"] += 1000
        r = client.post("/api/posture/ingest", headers=auth(token),
                        json=sample(clock, label, dev, features=features or FEATURES_GOOD, confidence=confidence, **extra))
        assert r.status_code == 200, r.get_json()


def finish(client, dash, suffix=""):
    return client.post("/api/model/calibrate/finish" + suffix, headers=auth(dash)).get_json()


def test_the_model_name_is_kept_with_the_latest_reading_and_bad_names_are_ignored(env):
    client, clock, _ = env
    dash, dev = paired(client)
    stream(client, dev, clock, 1, source="posture-pipeline/side-angle-rule@0.1.0")
    assert client.get("/api/status", headers=auth(dash)).get_json()["sample"]["source"] == "posture-pipeline/side-angle-rule@0.1.0"
    for bad in ("x" * 200, 123, "", "tab\tchar"):
        stream(client, dev, clock, 1, source=bad)
        assert "source" not in client.get("/api/status", headers=auth(dash)).get_json()["sample"]


def test_model_health_says_stub_until_a_real_model_streams(env):
    client, clock, _ = env
    dash, dev = paired(client)
    health = lambda: client.get("/api/model/health", headers=auth(dash)).get_json()  # noqa: E731
    assert health()["stub"] is True and health()["live"] is False
    stream(client, dev, clock, 2, source="posture-pipeline/side-angle-rule@0.1.0")
    h = health()
    assert h["stub"] is False and h["live"] is True and h["source"].startswith("posture-pipeline")
    clock["t"] += 60_000                                   # the camera machine went quiet
    assert health()["stub"] is True and health()["live"] is False


def test_calibration_uses_the_live_feed_when_the_model_is_streaming(env):
    client, clock, _ = env
    dash, dev = paired(client)
    stream(client, dev, clock, 12, source="posture-pipeline/side-angle-rule@0.1.0")
    out = finish(client, dash)
    assert out["stub"] is False and out["accepted"] is True and out["issues"] == []
    assert out["goal"] == {"torsoAngle": 4.0, "neckAngle": 12.0}
    assert out["source"].startswith("posture-pipeline")
    # the dashboard then stores it, and the server's own gate re-checks it
    saved = client.put("/api/calibration", json=out, headers=auth(dash))
    assert saved.status_code == 200 and saved.get_json()["baseline"]["goal"]["torsoAngle"] == 4.0


def test_a_slouched_countdown_is_refused_with_the_back_angle_reason(env):
    client, clock, _ = env
    dash, dev = paired(client)
    stream(client, dev, clock, 12, label="SLOUCHING", dev=0.8, features={"torsoAngle": 22.0, "neckAngle": 35.0})
    out = finish(client, dash)
    assert out["stub"] is False and out["accepted"] is False
    assert any("leaning forward" in i for i in out["issues"])
    assert client.put("/api/calibration", json=out, headers=auth(dash)).status_code == 422


def test_leaning_far_back_is_refused_too(env):
    client, clock, _ = env
    dash, dev = paired(client)
    stream(client, dev, clock, 12, features={"torsoAngle": -16.0})
    assert finish(client, dash)["accepted"] is False


def test_moving_around_during_the_countdown_is_refused(env):
    client, clock, _ = env
    dash, dev = paired(client)
    for angle in (0, 12, 2, 14, 1, 13, 3, 12, 0, 14, 1, 13):
        stream(client, dev, clock, 1, features={"torsoAngle": float(angle)})
    out = finish(client, dash)
    assert out["accepted"] is False and any("moved around" in i for i in out["issues"])


def test_not_being_seen_clearly_is_refused(env):
    client, clock, _ = env
    dash, dev = paired(client)
    stream(client, dev, clock, 12, label="UNKNOWN", dev=None, features={}, confidence=0.0)
    out = finish(client, dash)
    assert out["stub"] is False and out["accepted"] is False
    assert any("couldn't see you" in i for i in out["issues"])


def test_calibration_falls_back_to_the_stub_when_nothing_is_streaming(env):
    client, clock, _ = env
    dash, dev = paired(client)
    assert finish(client, dash)["stub"] is True            # never streamed
    stream(client, dev, clock, 12)
    clock["t"] += 60_000
    assert finish(client, dash)["stub"] is True            # streamed, but it stopped


def test_the_demo_rejection_button_still_works_while_a_model_streams(env):
    client, clock, _ = env
    dash, dev = paired(client)
    stream(client, dev, clock, 12)
    out = finish(client, dash, "?force=bad")
    assert out["stub"] is True and out["accepted"] is False


def test_recent_readings_are_bounded_and_not_exposed_by_status(env):
    client, clock, store = env
    dash, dev = paired(client)
    stream(client, dev, clock, 90)
    sess = store.latest_session(store_user_id(store))
    assert 0 < len(sess["state"]["recent"]) <= 40
    assert "recent" not in str(client.get("/api/status", headers=auth(dash)).get_json())


def store_user_id(store):
    from api.tests.conftest import all_users
    return all_users(store)[0]["id"]
