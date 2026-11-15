"""Store contract: the same behaviour from MemoryStore and PostgresStore (see conftest.py)."""
import pytest

from api.tests.conftest import all_events

T0 = 1_731_672_000_000


def mkuser(store, n=1):
    return store.create_user(f"hash-{n}", f"CODE{n:02d}", T0 + 600_000, {"slouchThresholdSec": 30})


def ev(user, t, to="GOOD", frm="AWAY", **kw):
    return {"user_id": user["id"], "session_id": None, "t": t, "kind": "transition",
            "from_state": frm, "to_state": to, "alert": False, "level": 0, "reason": "", "deviation": None, **kw}


def test_user_roundtrip_and_updates(store):
    u = mkuser(store)
    assert isinstance(u["id"], str) and u["device_token_hash"] is None and u["calibration"] is None
    assert store.get_user_by_dashboard_hash("hash-1")["id"] == u["id"]
    assert store.get_user_by_pairing_code("CODE01")["id"] == u["id"]
    assert store.get_user_by_dashboard_hash("nope") is None

    store.update_user(u["id"], {"device_token_hash": "dev-1", "pairing_code": None, "pairing_expires_at": None})
    assert store.get_user_by_device_hash("dev-1")["id"] == u["id"]
    assert store.get_user_by_pairing_code("CODE01") is None

    baseline = {"schema": 1, "goal": {"neckAngle": 15.5, "n": 2}, "tolerance": 6.0, "capturedAt": T0}
    store.update_user(u["id"], {"calibration": baseline, "settings": {"a": [1, 2, {"b": None}], "c": 0.25}})
    got = store.get_user_by_dashboard_hash("hash-1")
    assert got["calibration"] == baseline                       # jsonb round-trips floats/ints/nesting
    assert got["settings"] == {"a": [1, 2, {"b": None}], "c": 0.25}
    store.update_user(u["id"], {"calibration": None})
    assert store.get_user_by_dashboard_hash("hash-1")["calibration"] is None


def test_session_upsert_keeps_identity_and_latest_wins(store):
    u = mkuser(store)
    sid1, sid2 = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
    base = {"user_id": u["id"], "started_at": T0, "state": {"state": "GOOD", "since": T0}, "last_sample": None}
    store.save_session({**base, "id": sid1, "last_t": T0, "last_seen_server_ms": T0})
    store.save_session({**base, "id": sid2, "last_t": T0 + 5, "last_seen_server_ms": T0 + 5000,
                        "last_sample": {"label": "GOOD", "features": {"neckAngle": 1.5}}})
    assert store.latest_session(u["id"])["id"] == sid2
    # update sid1 with a newer sighting: it becomes the latest; started_at is not overwritten
    store.save_session({**base, "id": sid1, "started_at": T0 + 999, "last_t": T0 + 9,
                        "last_seen_server_ms": T0 + 9000, "state": {"state": "SLOUCHING"}})
    s1 = store.get_session(sid1)
    assert store.latest_session(u["id"])["id"] == sid1
    assert s1["state"] == {"state": "SLOUCHING"} and s1["last_t"] == T0 + 9 and s1["started_at"] == T0
    assert store.get_session(sid2)["last_sample"]["features"]["neckAngle"] == 1.5
    assert store.get_session("33333333-3333-4333-8333-333333333333") is None


def test_events_ranges_ordering_and_chunked_insert(store):
    u, other = mkuser(store, 1), mkuser(store, 2)
    # 450 rows (> the 200-row insert chunk), plus one event for another user that must not leak
    rows = [ev(u, T0 + i * 1000, to="GOOD" if i % 2 else "SLOUCHING") for i in range(450)]
    rows.append(ev(other, T0 + 5000))
    store.insert_events(rows)
    assert len(all_events(store)) == 451

    got = store.list_events(u["id"], T0, T0 + 450_000)
    assert len(got) == 450 and [e["t"] for e in got] == sorted(e["t"] for e in got)
    # half-open [since, until): the since instant is included, the until instant is not
    assert [e["t"] for e in store.list_events(u["id"], T0 + 1000, T0 + 4000)] == [T0 + 1000, T0 + 2000, T0 + 3000]
    assert store.list_events(u["id"], T0 + 1, T0 + 999) == []   # millisecond-exact bounds
    # same-t events keep insertion order
    store.insert_events([ev(u, T0 + 9_999_000, to="A"), ev(u, T0 + 9_999_000, to="B")])
    tail = store.list_events(u["id"], T0 + 9_999_000, T0 + 10_000_000)
    assert [e["to_state"] for e in tail] == ["A", "B"]
    assert isinstance(got[0]["id"], int) and isinstance(got[0]["user_id"], str)


def test_last_event_before_ignores_alert_kind_and_other_users(store):
    u, other = mkuser(store, 1), mkuser(store, 2)
    store.insert_events([
        ev(u, T0 + 1000, to="GOOD"),
        ev(u, T0 + 2000, to="SLOUCHING", frm="GOOD", alert=True, level=1, reason="threshold", deviation=0.7),
        {**ev(u, T0 + 3000, to="SLOUCHING", frm="SLOUCHING"), "kind": "alert", "alert": True, "level": 2},
        ev(other, T0 + 2500, to="AWAY"),
    ])
    last = store.last_event_before(u["id"], T0 + 10_000)
    assert last["t"] == T0 + 2000 and last["to_state"] == "SLOUCHING" and last["level"] == 1
    assert abs(last["deviation"] - 0.7) < 1e-9
    assert store.last_event_before(u["id"], T0 + 1000) is None          # strictly before
    assert store.last_event_before(u["id"], T0 + 1001)["t"] == T0 + 1000


def test_clear_history_only_touches_that_user(store):
    u, other = mkuser(store, 1), mkuser(store, 2)
    base = {"started_at": T0, "last_t": T0, "last_seen_server_ms": T0, "state": {}, "last_sample": None}
    for who, sid in ((u, "11111111-1111-4111-8111-111111111111"), (other, "22222222-2222-4222-8222-222222222222")):
        store.save_session({**base, "id": sid, "user_id": who["id"]})
        store.insert_events([ev(who, T0 + 1000)])
    store.clear_history(u["id"])
    assert store.latest_session(u["id"]) is None and store.list_events(u["id"], 0, T0 * 2) == []
    assert store.latest_session(other["id"]) is not None and len(store.list_events(other["id"], 0, T0 * 2)) == 1
    assert store.get_user_by_dashboard_hash("hash-1") is not None       # the user itself survives


def test_push_subscriptions_upsert_list_delete(store):
    u = mkuser(store)
    store.save_push_subscription(u["id"], "apns", "tok1", {"sandbox": True})
    store.save_push_subscription(u["id"], "apns", "tok1", {"sandbox": False})   # upsert, not a duplicate
    store.save_push_subscription(u["id"], "web", "https://push.example/a", {"keys": {"p256dh": "k", "auth": "a"}})
    assert len(store.list_push_subscriptions(u["id"])) == 2
    apns = store.list_push_subscriptions(u["id"], "apns")
    assert len(apns) == 1 and apns[0]["data"] == {"sandbox": False} and apns[0]["endpoint"] == "tok1"
    store.delete_push_subscription(u["id"], "apns", "tok1")
    assert store.list_push_subscriptions(u["id"], "apns") == []
    assert len(store.list_push_subscriptions(u["id"], "web")) == 1


def test_ping_ok(store):
    assert store.ping() == (True, None)


def test_postgres_rejects_unknown_user_fields_and_reports_missing_schema(store):
    if store.kind != "postgres":
        pytest.skip("Postgres only")
    u = mkuser(store)
    with pytest.raises(ValueError):
        store.update_user(u["id"], {"id": "x; drop table users"})          # column names are whitelisted
    with store.pool.connection() as c:
        c.execute("drop table push_subscriptions, events, sessions, users cascade")
    assert store.ping() == (False, "schema_missing")
