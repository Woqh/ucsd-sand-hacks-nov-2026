"""Coach routes end to end (both stores): insights, preview, consent-gated Gemini endpoints with a fake
client, local-overlay segments."""
import json

import pytest

from api.ai import gemini
from api.tests.test_ai import FakeClient, valid_analysis
from api.tests.test_api import T0, auth, env, paired  # noqa: F401  (env is the shared fixture)
from api.tests.conftest import all_events, all_samples


@pytest.fixture
def seeded(env):
    client, clock, store = env
    gemini._calls.clear()
    r = client.post("/api/dev/seed", json={"days": 42}).get_json()
    return client, clock, store, auth(r["dashboardToken"])


def use_ai(monkeypatch, text=None, exc=None):
    fake = FakeClient(text=text, exc=exc)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(gemini, "_client_factory", lambda: fake)
    return fake


# --------------------------------------------------------------------------- no AI involved
def test_insights_tell_the_seeded_persons_story_without_any_ai(seeded, monkeypatch):
    client, _, _, h = seeded
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = client.get("/api/coach/insights?tzOffsetMin=0", headers=h)
    d = r.get_json()
    assert r.status_code == 200 and d["ai"] == {"configured": False, "model": None}
    p = d["pack"]
    assert p["patterns"]["fingerprint"]["signature"] == "headForward"
    assert p["coaching"]["response"]["nudges"] > 50 and p["breaks"]["longestSitMin"]
    assert p["patterns"]["drift"]["calibrationAgeDays"] == 50 and p["patterns"]["drift"]["recalibrateSuggested"]
    assert p["exercises"] and p["habits"]["challenge"]["title"]
    assert client.get("/api/coach/insights").status_code == 401


def test_a_new_user_gets_an_honest_empty_pack(env):
    client, _, _ = env
    dash, dev = paired(client)
    p = client.get("/api/coach/insights", headers=auth(dash)).get_json()["pack"]
    assert p["window"]["seatedHours"] == 0 and p["patterns"]["fingerprint"] is None and p["coaching"]["response"]["nudges"] == 0


def test_preview_shows_exactly_what_would_be_sent_and_no_pain_data(seeded):
    client, _, _, h = seeded
    client.post("/api/checkins", json={"pain": 7, "area": "neck"}, headers=h)             # health data exists...
    r = client.get("/api/coach/preview", headers=h).get_json()
    text = json.dumps(r["payload"]).lower()
    assert "pain" not in text and "checkin" not in text and "neck pain" not in text      # ...and never leaves
    assert r["bytes"] == len(json.dumps(r["payload"])) and r["bytes"] < 25_000
    assert any("pain check-ins are never sent" in line.lower() for line in r["disclosure"])
    assert any("paid" in line.lower() for line in r["disclosure"])                       # the unpaid-tier warning
    assert "exerciseLibrary" in r["payload"] and "exercises" not in r["payload"]


# --------------------------------------------------------------------------- Gemini, consent-gated
def test_analyze_requires_consent_and_a_configured_key(seeded, monkeypatch):
    client, _, _, h = seeded
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert client.post("/api/coach/analyze", json={}, headers=h).get_json()["error"]["code"] == "consent_required"
    assert client.post("/api/coach/analyze", json={"consent": "yes"}, headers=h).status_code == 400
    r = client.post("/api/coach/analyze", json={"consent": True}, headers=h)
    assert r.status_code == 503 and r.get_json()["error"]["code"] == "ai_not_configured"
    assert client.post("/api/coach/analyze", json={"consent": True}, headers=auth("x" * 30)).status_code == 401


def test_analyze_sends_only_the_previewed_payload_and_stores_nothing(seeded, monkeypatch):
    client, _, store, h = seeded
    fake = use_ai(monkeypatch, text=json.dumps(valid_analysis()))
    client.post("/api/checkins", json={"pain": 9}, headers=h)
    preview = client.get("/api/coach/preview", headers=h).get_json()["payload"]
    n_events, n_samples = len(all_events(store)), len(all_samples(store))

    r = client.post("/api/coach/analyze", json={"consent": True}, headers=h)
    body = r.get_json()
    assert r.status_code == 200 and body["analysis"]["headline"] and body["model"] == gemini.DEFAULT_MODEL
    assert body["sent"] == preview                                                  # what was sent == what was previewed
    sent_to_google = fake.calls[0]["contents"]
    assert json.loads(sent_to_google) == preview and "pain" not in sent_to_google.lower()
    assert "Never give medical advice" in fake.calls[0]["config"].system_instruction
    assert (len(all_events(store)), len(all_samples(store))) == (n_events, n_samples)   # nothing persisted


def test_analyze_failure_modes_are_reported_not_leaked(seeded, monkeypatch):
    client, _, _, h = seeded
    use_ai(monkeypatch, text='{"headline": 5}')
    r = client.post("/api/coach/analyze", json={"consent": True}, headers=h)
    assert r.status_code == 502 and r.get_json()["error"]["code"] == "ai_bad_output"
    use_ai(monkeypatch, exc=RuntimeError("quota exceeded for key AIzaSySECRET"))
    r = client.post("/api/coach/analyze", json={"consent": True}, headers=h)
    assert r.status_code == 502 and r.get_json()["error"]["code"] == "ai_unavailable" and "SECRET" not in r.get_data(as_text=True)


def test_ai_calls_are_rate_limited_per_user(seeded, monkeypatch):
    client, _, _, h = seeded
    use_ai(monkeypatch, text=json.dumps(valid_analysis()))
    codes = [client.post("/api/coach/analyze", json={"consent": True}, headers=h).status_code for _ in range(gemini.MAX_CALLS_PER_HOUR + 1)]
    assert codes[:-1] == [200] * gemini.MAX_CALLS_PER_HOUR and codes[-1] == 429


def test_ask_is_grounded_and_validated(seeded, monkeypatch):
    client, _, _, h = seeded
    fake = use_ai(monkeypatch, text='{"answer": "Afternoons.", "basedOn": ["dangerHours"], "outOfScope": false}')
    for bad in ({"question": "hi", "consent": True}, {"question": "x" * 301, "consent": True}, {"consent": True}):
        assert client.post("/api/coach/ask", json=bad, headers=h).status_code == 400
    assert client.post("/api/coach/ask", json={"question": "When do I slouch most?"}, headers=h).status_code == 400   # no consent
    r = client.post("/api/coach/ask", json={"question": "When do I slouch most?", "consent": True}, headers=h)
    assert r.status_code == 200 and r.get_json()["answer"] == "Afternoons." and r.get_json()["outOfScope"] is False
    sent = json.loads(fake.calls[0]["contents"])
    assert sent["question"] == "When do I slouch most?" and "habits" in sent
    assert "Evidence facts" in fake.calls[0]["config"].system_instruction and "619 million" in fake.calls[0]["config"].system_instruction


def test_settings_from_text_proposes_a_change_but_never_applies_it(seeded, monkeypatch):
    client, _, _, h = seeded
    before = client.get("/api/settings", headers=h).get_json()["settings"]
    use_ai(monkeypatch, text=json.dumps({"explanation": "Shorter nudges and quiet evenings.", "slouchThresholdSec": 20,
                                         "quietHoursEnabled": True, "quietStart": "18:00", "quietEnd": "09:00", "nudgeTone": "direct"}))
    r = client.post("/api/coach/settings-from-text", json={"text": "I work 9 to 6 and hate nagging", "consent": True}, headers=h)
    d = r.get_json()
    assert r.status_code == 200 and d["patch"]["slouchThresholdSec"] == 20 and d["patch"]["quietHours"]["start"] == "18:00"
    changed = {c["field"]: (c["from"], c["to"]) for c in d["changes"]}
    assert changed["slouchThresholdSec"] == (before["slouchThresholdSec"], 20) and changed["quietHours.enabled"] == (False, True)
    assert changed["nudgeTone"] == ("gentle", "direct")
    assert client.get("/api/settings", headers=h).get_json()["settings"] == before        # nothing was applied
    # the proposal is a valid patch: applying it through the normal API works
    assert client.put("/api/settings", json=d["patch"], headers=h).status_code == 200


def test_settings_from_text_rejects_unusable_model_output(seeded, monkeypatch):
    client, _, _, h = seeded
    use_ai(monkeypatch, text=json.dumps({"explanation": "x", "quietStart": "25:99"}))       # passes the schema, fails settings validation
    r = client.post("/api/coach/settings-from-text", json={"text": "evenings off", "consent": True}, headers=h)
    assert r.status_code == 502 and r.get_json()["error"]["code"] == "ai_bad_output"
    assert client.post("/api/coach/settings-from-text", json={"text": "", "consent": True}, headers=h).status_code == 400


# --------------------------------------------------------------------------- segments for local overlays
def test_segments_are_compact_and_validated(seeded):
    client, clock, _, h = seeded
    r = client.get("/api/segments?days=14", headers=h).get_json()
    segs = r["segments"]
    assert segs and all(len(s) == 3 and s[2] in "GDSA" and s[0] < s[1] for s in segs)
    assert r["until"] == clock["t"] and r["since"] == clock["t"] - 14 * 86_400_000
    assert segs == sorted(segs, key=lambda s: s[0]) and any(s[2] == "S" for s in segs)
    for bad in ("0", "31", "x"):
        assert client.get(f"/api/segments?days={bad}", headers=h).status_code == 400
    assert client.get("/api/segments").status_code == 401
