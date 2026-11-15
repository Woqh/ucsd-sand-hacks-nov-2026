"""The bridge client against a real Sitwise API served on a loopback port (no mocks)."""
import threading
import uuid

import pytest
from werkzeug.serving import make_server

from api.app import create_app
from api.db_memory import MemoryStore
from bridge import adapter
from bridge.client import Api, BridgeError, load_saved, save_token


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("ENABLE_DEV_ROUTES", "1")
    httpd = make_server("127.0.0.1", 0, create_app(MemoryStore()), threaded=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def pair(base):
    dash = Api(base)
    made = dash._call("POST", "/pair/create", auth=False)
    dash.token = made["dashboardToken"]
    return dash, made["pairingCode"]


def reading(**kw):
    import time
    return {"schema": 1, "sessionId": str(uuid.uuid4()), "t": int(time.time() * 1000), "label": "GOOD", "deviation": 0.1,
            "confidence": 0.9, "features": {"torsoAngle": 4.0}, "source": "test", **kw}


def test_claim_ingest_and_goal_roundtrip(server):
    dash, code = pair(server)
    bridge = Api(server)
    assert bridge.claim(code.lower() + " ")                       # tolerant of case and stray spaces
    assert bridge.goal_torso_angle() is None                      # not calibrated yet
    out = bridge.ingest(reading())
    assert out["state"] in ("GOOD", "AWAY") and out["serverTime"]
    dash._call("PUT", "/calibration", {"goal": {"torsoAngle": 6.5}, "tolerance": 6, "capturedAt": 1_731_672_000_000})
    assert bridge.goal_torso_angle() == 6.5
    assert dash._call("GET", "/status")["sample"]["source"] == "test"


def test_errors_are_typed(server):
    with pytest.raises(BridgeError) as e:
        Api(server).claim("NOPE00")
    assert e.value.status == 404
    with pytest.raises(BridgeError) as e:
        Api(server, "wrong-token").ingest(reading())
    assert e.value.status == 401
    with pytest.raises(BridgeError) as e:
        Api("http://127.0.0.1:9", timeout=2).goal_torso_angle()   # nothing listens here
    assert e.value.status == 0 and e.value.code == "network"


def test_the_client_refuses_to_send_anything_but_numbers_and_labels(server):
    dash, code = pair(server)
    bridge = Api(server)
    bridge.claim(code)
    with pytest.raises(ValueError):
        bridge.ingest(reading(landmarks=[[0.1, 0.2]]))
    assert adapter.validate_outgoing(reading())


def test_the_token_is_remembered_in_a_given_file(tmp_path):
    path = tmp_path / "sub" / "bridge.json"
    assert load_saved(path) == {}
    save_token("http://x", "secret", path)
    assert load_saved(path) == {"base": "http://x", "deviceToken": "secret"}
    path.write_text("not json")
    assert load_saved(path) == {}
