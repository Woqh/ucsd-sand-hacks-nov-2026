"""End-to-end API tests with a fake clock. The `store` fixture (conftest.py) runs each test on the
in-memory store and, if TEST_DATABASE_URL is set, on real Postgres too."""
import uuid

import pytest

from api import util
from api.app import create_app
from api.tests.conftest import all_events, all_samples, all_subscriptions, all_users

T0 = 1_731_672_000_000  # 2024-11-15 12:00:00 UTC
SID = str(uuid.uuid4())


@pytest.fixture
def env(monkeypatch, store):
    clock = {"t": T0}
    monkeypatch.setattr(util, "now_ms", lambda: clock["t"])
    monkeypatch.setenv("ENABLE_DEV_ROUTES", "1")
    for k in ("APNS_KEY_ID", "APNS_AUTH_KEY", "VAPID_PRIVATE_KEY"):
        monkeypatch.delenv(k, raising=False)
    client = create_app(store).test_client()
    return client, clock, store


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def paired(client):
    r = client.post("/api/pair/create").get_json()
    dash = r["dashboardToken"]
    dev = client.post("/api/pair/claim", json={"code": r["pairingCode"].lower()}).get_json()["deviceToken"]
    return dash, dev


def sample(clock, label="GOOD", dev=0.1, sid=SID, **extra):
    return {"schema": 1, "sessionId": sid, "t": clock["t"], "label": label, "deviation": dev,
            "confidence": 0.95, "features": {"neckAngle": 15.0}, **extra}


def feed(client, token, clock, seconds, label, dev):
    last = None
    for _ in range(seconds):
        clock["t"] += 1000
        last = client.post("/api/posture/ingest", json=sample(clock, label, dev), headers=auth(token))
        assert last.status_code == 200, last.get_json()
    return last.get_json()


def test_pairing_flow_and_token_rules(env):
    client, clock, store = env
    r = client.post("/api/pair/create").get_json()
    assert len(r["pairingCode"]) == 6 and r["dashboardToken"]
    # tokens are stored hashed, never raw
    assert all(r["dashboardToken"] not in str(u) for u in all_users(store))

    claim = client.post("/api/pair/claim", json={"code": r["pairingCode"]})
    assert claim.status_code == 200
    assert client.post("/api/pair/claim", json={"code": r["pairingCode"]}).status_code == 404  # one-time
    assert client.post("/api/pair/claim", json={}).status_code == 400

    dash = r["dashboardToken"]
    again = client.post("/api/pair/create", headers=auth(dash)).get_json()
    assert "dashboardToken" not in again and again["pairingCode"] != r["pairingCode"]

    st = client.get("/api/status", headers=auth(dash)).get_json()
    assert st["paired"] is True and st["state"] == "AWAY" and st["stale"] is True


def test_expired_pairing_code(env):
    client, clock, _ = env
    r = client.post("/api/pair/create").get_json()
    clock["t"] += 11 * 60 * 1000
    assert client.post("/api/pair/claim", json={"code": r["pairingCode"]}).status_code == 404


def test_every_other_route_requires_the_right_token(env):
    client, clock, _ = env
    dash, dev = paired(client)
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/status", headers=auth("x" * 30)).status_code == 401
    assert client.get("/api/status", headers=auth(dev)).status_code == 401          # device can't read status
    assert client.post("/api/posture/ingest", json=sample(clock), headers=auth(dash)).status_code == 401
    assert client.get("/api/settings", headers=auth(dev)).status_code == 200        # both can
    assert client.get("/api/model/health", headers=auth(dash)).status_code == 200
    assert client.get("/api/model/health").status_code == 401
    assert client.get("/api/health").status_code == 200                              # documented exception


def test_ingest_validates_input(env):
    client, clock, _ = env
    _, dev = paired(client)
    bad = client.post("/api/posture/ingest", json={"sessionId": "nope"}, headers=auth(dev))
    assert bad.status_code == 400 and bad.get_json()["error"]["code"] == "bad_sample"
    skew = sample(clock)
    skew["t"] -= 2 * 3600 * 1000
    assert client.post("/api/posture/ingest", json=skew, headers=auth(dev)).get_json()["error"]["code"] == "clock_skew"


def test_slouch_fires_alert_then_recovers_and_status_tracks_it(env):
    client, clock, store = env
    dash, dev = paired(client)
    assert client.put("/api/settings", json={"slouchThresholdSec": 5}, headers=auth(dash)).status_code == 200

    r = feed(client, dev, clock, 3, "GOOD", 0.1)
    assert r["state"] == "GOOD" and r["alert"] is None

    r = feed(client, dev, clock, 4, "SLOUCHING", 0.8)
    assert r["state"] == "DEVIATING" and r["alert"] is None
    r = feed(client, dev, clock, 3, "SLOUCHING", 0.8)
    # the alert fired on one of those samples; with no push provider configured it reports skipped
    st = client.get("/api/status", headers=auth(dash)).get_json()
    assert st["state"] == "SLOUCHING" and st["stale"] is False and st["device"]["online"] is True
    assert st["sample"]["label"] == "SLOUCHING"
    alerts = [e for e in all_events(store) if e["alert"]]
    assert len(alerts) == 1 and alerts[0]["to_state"] == "SLOUCHING" and alerts[0]["level"] == 1

    r = feed(client, dev, clock, 5, "GOOD", 0.1)
    assert r["state"] == "GOOD"
    st = client.get("/api/status", headers=auth(dash)).get_json()
    assert st["state"] == "GOOD" and st["today"]["slouchEvents"] == 1
    assert st["today"]["score"] is not None


def test_alert_response_reports_channels_skipped_when_not_configured(env):
    client, clock, _ = env
    dash, dev = paired(client)
    client.put("/api/settings", json={"slouchThresholdSec": 5}, headers=auth(dash))
    client.post("/api/push/apns/register", json={"token": "ab" * 32, "sandbox": True}, headers=auth(dev))
    feed(client, dev, clock, 2, "GOOD", 0.1)
    alert = None
    for _ in range(8):
        r = feed(client, dev, clock, 1, "SLOUCHING", 0.8)
        alert = alert or r["alert"]
    assert alert["level"] == 1
    assert alert["channels"]["phone"]["skipped"] == "apns_not_configured"
    assert alert["channels"]["desktop"]["skipped"] == "no_browser_subscribed"


def test_receiver_phone_pairs_without_replacing_sensor_and_gets_phone_alerts(env, monkeypatch):
    client, clock, store = env
    dash, sensor = paired(client)
    pairing = client.post("/api/push/web/receiver/pairing", headers=auth(dash))
    assert pairing.status_code == 200
    code = pairing.get_json()["code"]
    assert len(code) == 8
    assert client.post("/api/push/web/receiver/pairing", headers=auth(sensor)).status_code == 401

    claim = client.post("/api/push/web/receiver/claim", json={"code": f" {code[:4]}-{code[4:].lower()} "})
    assert claim.status_code == 200
    receiver = claim.get_json()["receiverToken"]
    assert client.post("/api/push/web/receiver/claim", json={"code": code}).status_code == 404
    assert client.get("/api/settings", headers=auth(receiver)).status_code == 401

    subscription = {"endpoint": "https://push.example/device/one",
                    "keys": {"p256dh": "public-key", "auth": "auth-key"}}
    assert client.post("/api/push/web/receiver/subscribe", json={"subscription": subscription},
                       headers=auth(receiver)).status_code == 200
    assert client.post("/api/push/web/receiver/subscribe", json={"subscription": subscription},
                       headers=auth(dash)).status_code == 401
    assert any(s["kind"] == "web_phone" and s["endpoint"] == subscription["endpoint"]
               for s in all_subscriptions(store))

    monkeypatch.setattr("api.push.dispatch.apns.configured", lambda: False)
    monkeypatch.setattr("api.push.dispatch.webpush.configured", lambda: True)
    monkeypatch.setattr("api.push.dispatch.webpush.send", lambda *args, **kwargs: (True, 201, None))
    test = client.post("/api/push/test", json={"channel": "phone"}, headers=auth(dash))
    assert test.get_json()["result"] == {"sent": 1, "failed": 0, "skipped": None}

    assert client.post("/api/posture/ingest", json=sample(clock), headers=auth(sensor)).status_code == 200
    unsub = client.post("/api/push/web/receiver/unsubscribe", json={"endpoint": subscription["endpoint"]},
                        headers=auth(receiver))
    assert unsub.status_code == 200
    assert not any(s["kind"] == "web_phone" for s in all_subscriptions(store))
    assert client.post("/api/push/web/receiver/subscribe", json={"subscription": subscription},
                       headers=auth(receiver)).status_code == 401


def test_receiver_pairing_code_expires(env):
    client, clock, _ = env
    dash, _ = paired(client)
    code = client.post("/api/push/web/receiver/pairing", headers=auth(dash)).get_json()["code"]
    clock["t"] += 10 * 60 * 1000 + 1
    claim = client.post("/api/push/web/receiver/claim", json={"code": code})
    assert claim.status_code == 404 and claim.get_json()["error"]["code"] == "invalid_code"


def test_channels_can_be_turned_off(env):
    client, clock, _ = env
    dash, dev = paired(client)
    client.put("/api/settings", json={"slouchThresholdSec": 5, "alertChannels": {"phone": False, "desktop": False}},
               headers=auth(dash))
    feed(client, dev, clock, 2, "GOOD", 0.1)
    for _ in range(8):
        r = feed(client, dev, clock, 1, "SLOUCHING", 0.8)
        assert r["alert"] is None


def test_stale_session_reads_as_away(env):
    client, clock, _ = env
    dash, dev = paired(client)
    feed(client, dev, clock, 3, "GOOD", 0.1)
    assert client.get("/api/status", headers=auth(dash)).get_json()["state"] == "GOOD"
    clock["t"] += 16_000   # phone went quiet
    st = client.get("/api/status", headers=auth(dash)).get_json()
    assert st["state"] == "AWAY" and st["stale"] is True and st["rawState"] == "GOOD"


def test_new_session_closes_the_previous_one(env):
    client, clock, store = env
    dash, dev = paired(client)
    feed(client, dev, clock, 3, "GOOD", 0.1)
    clock["t"] += 60_000
    new_sid = str(uuid.uuid4())
    client.post("/api/posture/ingest", json=sample(clock, sid=new_sid), headers=auth(dev))
    closes = [e for e in all_events(store) if e["reason"] == "session_replaced"]
    assert len(closes) == 1 and closes[0]["to_state"] == "AWAY"


def test_session_cannot_be_hijacked_by_another_user(env):
    client, clock, _ = env
    _, dev1 = paired(client)
    _, dev2 = paired(client)
    client.post("/api/posture/ingest", json=sample(clock), headers=auth(dev1))
    r = client.post("/api/posture/ingest", json=sample(clock), headers=auth(dev2))
    assert r.status_code == 403


def test_settings_roundtrip_and_validation(env):
    client, _, _ = env
    dash, dev = paired(client)
    s = client.get("/api/settings", headers=auth(dash)).get_json()["settings"]
    assert s["slouchThresholdSec"] == 30
    r = client.put("/api/settings", json={"sensitivity": 0.8, "quietHours": {"enabled": True}}, headers=auth(dev))
    assert r.status_code == 200
    s = client.get("/api/settings", headers=auth(dash)).get_json()["settings"]
    assert s["sensitivity"] == 0.8 and s["quietHours"] == {"enabled": True, "start": "22:00", "end": "07:00"}
    bad = client.put("/api/settings", json={"slouchThresholdSec": 1}, headers=auth(dash))
    assert bad.status_code == 400 and bad.get_json()["error"]["code"] == "invalid_settings"


def test_calibration_roundtrip(env):
    client, clock, _ = env
    dash, dev = paired(client)
    assert client.get("/api/calibration", headers=auth(dash)).get_json()["calibrated"] is False
    baseline = {"schema": 1, "goal": {"neckAngle": 15.0, "torsoAngle": 5.0}, "tolerance": 6.0, "capturedAt": clock["t"]}
    assert client.put("/api/calibration", json=baseline, headers=auth(dev)).status_code == 200
    got = client.get("/api/calibration", headers=auth(dash)).get_json()
    assert got["calibrated"] and got["baseline"]["goal"]["neckAngle"] == 15.0
    assert client.put("/api/calibration", json={**baseline, "tolerance": -1}, headers=auth(dash)).status_code == 400
    assert client.get("/api/status", headers=auth(dash)).get_json()["calibrated"] is True


def test_calibration_gate_only_accepts_good_posture(env):
    client, clock, _ = env
    dash, dev = paired(client)
    h = auth(dash)
    # the model stub can be told to reject the captured posture
    bad = client.post("/api/model/calibrate/finish?force=bad", headers=h).get_json()
    assert bad["accepted"] is False and len(bad["issues"]) == 2
    ok = client.post("/api/model/calibrate/finish", headers=h).get_json()
    assert ok["accepted"] is True and ok["issues"] == []

    # the server refuses to store a rejected baseline (even if a client forgot to check)
    r = client.put("/api/calibration", json=bad, headers=h)
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "posture_not_good"
    assert "head is too far forward" in r.get_json()["error"]["message"]
    assert client.get("/api/calibration", headers=h).get_json()["calibrated"] is False
    # rejected without reasons still gets a helpful message
    r = client.put("/api/calibration", json={**bad, "issues": []}, headers=h)
    assert r.status_code == 422 and "sit upright" in r.get_json()["error"]["message"]

    # an accepted baseline is stored WITHOUT the verdict fields; omitting `accepted` still works
    assert client.put("/api/calibration", json=ok, headers=auth(dev)).status_code == 200
    stored = client.get("/api/calibration", headers=h).get_json()["baseline"]
    assert "accepted" not in stored and "issues" not in stored and stored["goal"]["neckAngle"] == 15.0
    legacy = {k: v for k, v in ok.items() if k not in ("accepted", "issues", "stub")}
    assert client.put("/api/calibration", json=legacy, headers=auth(dev)).status_code == 200
    # a bad value for `accepted` is a 400, not silently treated as accepted
    assert client.put("/api/calibration", json={**ok, "accepted": "yes"}, headers=h).status_code == 400


def test_ingest_stores_a_downsampled_reading_with_features(env):
    client, clock, store = env
    _, dev = paired(client)
    for _ in range(60):                                   # 60 samples at 1 Hz
        clock["t"] += 1000
        r = client.post("/api/posture/ingest", json=sample(clock, "GOOD", 0.1), headers=auth(dev))
        assert r.status_code == 200
    rows = all_samples(store)
    assert 10 <= len(rows) <= 14                          # about one per 5 s, not one per second
    assert all(r["state"] in ("GOOD", "DEVIATING", "SLOUCHING") and r["neck"] == 15.0 for r in rows)
    gaps = [b["t"] - a["t"] for a, b in zip(rows, rows[1:])]
    assert gaps and min(gaps) >= 5000
    # unusable readings (low confidence / UNKNOWN) are not stored
    n = len(all_samples(store))
    clock["t"] += 10_000
    client.post("/api/posture/ingest", json={**sample(clock), "confidence": 0.1}, headers=auth(dev))
    clock["t"] += 10_000
    client.post("/api/posture/ingest", json={**sample(clock, "UNKNOWN", None)}, headers=auth(dev))
    assert len(all_samples(store)) == n


def test_calibration_history_is_recorded_on_every_save(env):
    client, clock, store = env
    dash, dev = paired(client)
    ok = client.post("/api/model/calibrate/finish", headers=auth(dash)).get_json()
    for _ in range(2):
        assert client.put("/api/calibration", json=ok, headers=auth(dev)).status_code == 200
    uid = all_users(store)[0]["id"]
    hist = store.list_calibrations(uid)
    assert len(hist) == 2 and hist[0]["baseline"]["goal"]["torsoAngle"] == 5.0


def test_back_angle_gate_is_enforced_server_side(env):
    client, clock, _ = env
    dash, dev = paired(client)
    h = auth(dash)

    def baseline(angle, **kw):
        return {"schema": 1, "goal": {"neckAngle": 15.0, "torsoAngle": angle, "headForwardOffset": 0.18},
                "tolerance": 6.0, "capturedAt": clock["t"], **kw}

    # slouched spine/back angle: refused even though the model said accepted: true
    r = client.put("/api/calibration", json=baseline(18.0, accepted=True), headers=h)
    err = r.get_json()["error"]
    assert r.status_code == 422 and err["code"] == "posture_not_good"
    assert "leaning forward" in err["issues"][0] and "within 10" in err["issues"][0]   # structured reasons
    assert client.get("/api/calibration", headers=h).get_json()["calibrated"] is False
    # an upright back and a slight lean either way are fine (the range brackets 0)
    assert client.put("/api/calibration", json=baseline(-5.0), headers=h).status_code == 200
    assert client.put("/api/calibration", json=baseline(0.0), headers=auth(dev)).status_code == 200
    # leaning too far BACK is refused too, not only too far forward
    r = client.put("/api/calibration", json=baseline(-15.0), headers=h)
    assert r.status_code == 422 and "leaning back" in r.get_json()["error"]["issues"][0]
    assert client.put("/api/calibration", json=baseline(-40.0), headers=h).status_code == 422
    # no back angle measured: can't be checked, so it is refused (not silently accepted)
    nobody = baseline(5.0)
    del nobody["goal"]["torsoAngle"]
    r = client.put("/api/calibration", json=nobody, headers=h)
    assert r.status_code == 400 and "torsoAngle" in r.get_json()["error"]["message"]
    # NaN/Infinity parse in Python's json and fail every comparison, so they must be rejected explicitly
    for bad in ("NaN", "Infinity", "-Infinity"):
        raw = '{"goal":{"torsoAngle":%s},"tolerance":6,"capturedAt":1731672000000}' % bad
        r = client.put("/api/calibration", data=raw, content_type="application/json", headers=h)
        assert r.status_code == 400, bad
    # the calibrated baseline from before is untouched by all the refusals
    assert client.get("/api/calibration", headers=h).get_json()["baseline"]["goal"]["torsoAngle"] == 0.0


def test_checkins_validation_and_listing(env):
    client, clock, _ = env
    dash, dev = paired(client)
    h = auth(dash)
    for bad in ({"pain": 11}, {"pain": -1}, {"pain": "3"}, {"pain": True}, {"pain": 2.5}, {}, {"pain": 3, "area": "knee"}):
        assert client.post("/api/checkins", json=bad, headers=h).status_code == 400, bad
    c = client.post("/api/checkins", json={"pain": 4, "area": "neck"}, headers=h).get_json()["checkin"]
    assert set(c) == {"id", "t", "pain", "area"} and c["t"] == clock["t"] and c["area"] == "neck"
    clock["t"] += 86_400_000
    assert client.post("/api/checkins", json={"pain": 6}, headers=h).status_code == 200      # area is optional
    rows = client.get("/api/checkins", headers=h).get_json()["checkins"]
    assert [r["pain"] for r in rows] == [6, 4] and rows[0]["area"] is None                    # newest first
    assert client.post("/api/checkins", json={"pain": 3}, headers=auth(dev)).status_code == 401   # dashboard only


def test_pain_insight_needs_enough_weeks_and_is_hedged_data_only(env):
    client, clock, _ = env
    # a user with no check-ins: empty, not enough
    dash, _ = paired(client)
    empty = client.get("/api/insights/pain", headers=auth(dash)).get_json()
    assert empty["points"] == [] and empty["correlation"]["enough"] is False and empty["lastCheckinAt"] is None

    # seeded user (42 days of history + one demo check-in per week): enough weeks for a correlation
    seeded = client.post("/api/dev/seed", json={"days": 42}).get_json()
    assert seeded["checkins"] >= 5
    out = client.get("/api/insights/pain", headers=auth(seeded["dashboardToken"])).get_json()
    corr = out["correlation"]
    assert corr["enough"] and corr["n"] >= 5 and corr["needed"] == 5
    assert corr["direction"] == "positive" and corr["rho"] > 0.3 and corr["strength"] in ("modest", "stronger")
    used = [p for p in out["points"] if p["used"]]
    assert len(used) == corr["n"] and all(0 <= p["pain"] <= 10 and 0 <= p["slouchPct"] <= 100 for p in used)
    assert out["nextSuggestedAt"] == out["lastCheckinAt"] + 7 * 86_400_000


def test_export_is_deidentified_weekly_aggregates(env):
    client, clock, store = env
    seeded = client.post("/api/dev/seed", json={"days": 42}).get_json()
    h = auth(seeded["dashboardToken"])
    r = client.get("/api/export", headers=h)
    body = r.get_json()
    assert r.status_code == 200 and body["kind"] == "sitwise-weekly-export" and len(body["weeks"]) == 12
    assert all(set(w) == {"weekStart", "seatedMinutes", "goodPct", "slouchPct", "slouchEpisodes"} for w in body["weeks"])
    assert any(w["seatedMinutes"] > 0 for w in body["weeks"]) and body["checkins"]
    assert all(set(c) == {"weekStart", "pain", "area"} for c in body["checkins"])
    # privacy: nothing identifying, nothing finer than a day
    text = r.get_data(as_text=True)
    for user in all_users(store):
        assert user["id"] not in text and user["dashboard_token_hash"] not in text
    assert seeded["dashboardToken"] not in text
    assert all(len(w["weekStart"]) == 10 for w in body["weeks"])                              # YYYY-MM-DD
    assert client.get("/api/export").status_code == 401


def test_push_registration_validation(env):
    client, _, store = env
    dash, dev = paired(client)
    assert client.post("/api/push/apns/register", json={"token": "zz"}, headers=auth(dev)).status_code == 400
    assert client.post("/api/push/apns/register", json={"token": "AB" * 32}, headers=auth(dev)).status_code == 200
    sub = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}
    assert client.post("/api/push/web/subscribe", json={"subscription": sub}, headers=auth(dash)).status_code == 200
    assert client.post("/api/push/web/subscribe", json={"subscription": {"endpoint": "http://x"}}, headers=auth(dash)).status_code == 400
    kinds = sorted(s["kind"] for s in all_subscriptions(store))
    assert kinds == ["apns", "web"]
    t = client.post("/api/push/test", json={"channel": "desktop"}, headers=auth(dash)).get_json()
    assert t["result"]["skipped"] == "vapid_not_configured"


def test_model_stubs_return_fixed_mock_data(env):
    client, _, _ = env
    dash, _ = paired(client)
    h = auth(dash)
    good = client.post("/api/model/analyze", json={}, headers=h).get_json()
    assert good["label"] == "GOOD" and good["stub"] is True
    slouch = client.post("/api/model/analyze?force=slouch", json={}, headers=h).get_json()
    assert slouch["label"] == "SLOUCHING" and slouch["deviation"] > 0.4
    assert client.post("/api/model/calibrate/start", headers=h).get_json() == {"schema": 1, "status": "started", "stub": True}
    fin = client.post("/api/model/calibrate/finish", headers=h).get_json()
    assert fin["stub"] and set(fin["goal"]) == {"neckAngle", "torsoAngle", "headForwardOffset"}
    assert client.get("/api/model/health", headers=h).get_json()["ready"] is True


def test_seed_then_metrics(env):
    client, clock, _ = env
    r = client.post("/api/dev/seed", json={"days": 7, "tzOffsetMin": 0}).get_json()
    assert r["events"] > 100 and r["dashboardToken"]
    h = auth(r["dashboardToken"])

    week = client.get("/api/metrics?range=week", headers=h).get_json()
    assert len(week["daily"]) == 7
    scores = [d["score"] for d in week["daily"] if d["score"] is not None]
    assert len(scores) >= 5 and all(0 <= s <= 100 for s in scores)
    assert scores[-1] > scores[0]                               # the seeded story: improving
    s = week["summary"]
    assert s["seatedSec"] > 3600 and s["slouchEvents"] > 0 and s["longestGoodStreakSec"] > 0
    assert week["goal"]["targetPct"] % 5 == 0
    assert week["outlook"]["status"] in ("on_track", "at_risk")
    assert week["heatmap"] and {"day", "hour", "goodPct"} <= set(week["heatmap"][0])
    assert week["timeline"] == []

    day = client.get("/api/metrics?range=day", headers=h).get_json()
    assert len(day["daily"]) == 1 and day["timeline"]
    assert client.get("/api/metrics?range=year", headers=h).status_code == 400
    assert client.get("/api/metrics?range=week&tzOffsetMin=x", headers=h).status_code == 400

    # re-seeding an existing user replaces their history rather than doubling it
    n1 = len(all_events(client.application.config["STORE"]))
    client.post("/api/dev/seed", json={"days": 7}, headers=h)
    assert len(all_events(client.application.config["STORE"])) == n1


def test_dev_routes_are_off_by_default(env, monkeypatch):
    client, _, _ = env
    monkeypatch.delenv("ENABLE_DEV_ROUTES")
    assert client.post("/api/dev/seed").status_code == 404
    assert client.get("/api/health").get_json()["devRoutes"] is False


def test_unknown_route_is_json_404(env):
    client, _, _ = env
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.get_json()["error"]["code"] == "not_found"


def test_focus_session_endpoint_and_tone_setting(env):
    client, clock, store = env
    dash, dev = paired(client)
    h = auth(dash)
    s = client.get("/api/settings", headers=h).get_json()["settings"]
    assert s["nudgeTone"] == "gentle" and s["focus"] == {"onlyDuringFocus": False, "untilMs": 0}
    assert client.put("/api/settings", json={"nudgeTone": "direct", "focus": {"onlyDuringFocus": True}}, headers=h).status_code == 200
    r = client.post("/api/focus", json={"minutes": 25}, headers=h).get_json()
    assert r["focusUntilMs"] == clock["t"] + 25 * 60_000 and r["settings"]["focus"]["untilMs"] == r["focusUntilMs"]
    assert r["settings"]["nudgeTone"] == "direct" and r["settings"]["focus"]["onlyDuringFocus"] is True    # unrelated fields kept
    assert client.post("/api/focus", json={"minutes": 0}, headers=h).get_json()["focusUntilMs"] == 0
    for bad in ({"minutes": -1}, {"minutes": 241}, {"minutes": "25"}, {"minutes": True}, {}):
        assert client.post("/api/focus", json=bad, headers=h).status_code == 400, bad
    assert client.post("/api/focus", json={"minutes": 5}, headers=auth(dev)).status_code == 401          # dashboard only
    assert client.put("/api/settings", json={"nudgeTone": "angry"}, headers=h).status_code == 400


def test_focus_mode_gates_alerts_end_to_end(env):
    client, clock, store = env
    dash, dev = paired(client)
    h = auth(dash)
    client.put("/api/settings", json={"slouchThresholdSec": 5, "focus": {"onlyDuringFocus": True}}, headers=h)
    feed(client, dev, clock, 2, "GOOD", 0.1)
    alerts = []
    for _ in range(8):
        alerts.append(feed(client, dev, clock, 1, "SLOUCHING", 0.8)["alert"])
    assert not any(alerts)                                                  # focus mode on, no session: silent
    client.post("/api/focus", json={"minutes": 10}, headers=h)
    alerts = [feed(client, dev, clock, 1, "SLOUCHING", 0.8)["alert"] for _ in range(3)]
    assert any(alerts)                                                      # a session is running: it nudges
