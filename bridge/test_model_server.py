"""scripts/model_server.py (the Camera page's local model) with the REAL angle rule and a synthetic pose.

Needs numpy, OpenCV and Flask, so it is skipped in the API's Python and runs in the model's environment:
    posture_pipeline-main\\.venv\\Scripts\\python.exe -m pytest bridge/test_model_server.py
"""
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("flask")

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT / "scripts", ROOT / "posture_pipeline-main", ROOT):
    sys.path.insert(0, str(p))

import model_server  # noqa: E402
import posture_model  # noqa: E402
from posture.core import LANDMARK_NAMES  # noqa: E402
from posture.side_angle import SideAnglePredictor  # noqa: E402

from bridge.engine import Engine  # noqa: E402


class SyntheticExtractor:
    """Ignores the picture and 'sees' a side-on person leaning `angle` degrees (image-right positive)."""

    angle = 2.0
    people = 1

    def extract(self, frame):
        xy = np.full((33, 2), np.nan)
        conf = np.zeros(33)
        h, w = frame.shape[:2]
        t = np.radians(self.angle)
        xy[23] = (0.5, 0.7)
        xy[11] = (0.5 + 0.2 * np.sin(t) * h / w, 0.7 - 0.2 * np.cos(t))   # normalized x is per-width: keep the true angle
        xy[7] = (xy[11][0] + 0.02, xy[11][1] - 0.1)
        conf[[11, 23, 7]] = 0.95
        return dict(image_xy=xy, confidence=conf, width=w, height=h, person_count=self.people)


@pytest.fixture
def client(monkeypatch):
    extractor = SyntheticExtractor()
    extractor.angle, extractor.people = 2.0, 1
    engine = Engine(extractor, SideAnglePredictor(), LANDMARK_NAMES, "posture-pipeline/test", neck_median_frames=1)
    monkeypatch.setattr(posture_model, "_engine", engine)
    monkeypatch.setattr(posture_model, "IS_PLACEHOLDER", False)
    monkeypatch.setattr(posture_model, "NAME", "test model")
    c = model_server.app.test_client()
    c.extractor, c.engine = extractor, engine
    return c


def jpeg():
    ok, buf = cv2.imencode(".jpg", np.full((640, 360, 3), 120, np.uint8))
    assert ok
    return buf.tobytes()


def analyze(c, query=""):
    return c.post("/analyze" + query, data=jpeg(), content_type="image/jpeg")


def test_health_reports_the_model_and_whether_it_is_the_real_one(client):
    h = client.get("/health").get_json()
    assert h["ready"] and h["name"] == "test model" and h["placeholder"] is False and h["problem"] is None


def test_a_frame_goes_through_the_angle_rule_and_comes_back_as_a_reading(client):
    r = analyze(client, "?facing=right").get_json()
    assert r["label"] == "GOOD" and r["stub"] is False and r["source"] == "posture-pipeline/test"
    assert r["features"]["torsoAngle"] == pytest.approx(2.0, abs=0.2) and "note" not in r
    assert 0 <= r["deviation"] < 0.2 and r["confidence"] == 0.95 and "inferenceMs" in r


def test_leaning_forward_is_slouching_and_the_goal_posture_is_the_reference(client):
    client.extractor.angle = 22.0
    r = analyze(client, "?facing=right").get_json()
    assert r["label"] == "SLOUCHING" and r["deviation"] == pytest.approx(0.88, abs=0.03)
    # the same posture IS the goal for someone calibrated at 22 degrees
    r = analyze(client, "?facing=right&goal=22").get_json()
    assert r["label"] == "GOOD" and r["deviation"] < 0.05


def test_facing_left_reverses_forward_and_auto_without_feet_says_why(client):
    client.extractor.angle = -22.0
    assert analyze(client, "?facing=left").get_json()["label"] == "SLOUCHING"
    r = analyze(client, "?facing=auto").get_json()
    assert r["label"] == "UNKNOWN" and r["confidence"] == 0.0 and "Pick which way you face" in r["note"]


def test_nobody_in_the_picture_is_away_with_a_note(client):
    client.extractor.people = 0
    r = analyze(client, "?facing=right").get_json()
    assert r["label"] == "AWAY" and r["note"] == "Nobody in view." and r["features"] == {}


@pytest.mark.parametrize("query", ["?facing=sideways", "?goal=abc", "?goal=120", "?goal=nan"])
def test_bad_options_are_refused(client, query):
    assert analyze(client, query).status_code == 400


def test_a_body_that_is_not_an_image_is_refused(client):
    assert client.post("/analyze", data=b"not an image").status_code == 400
    assert client.post("/analyze").status_code == 400


def test_the_reading_carries_only_numbers_and_short_text(client):
    r = analyze(client, "?facing=right").get_json()
    assert set(r) <= {"label", "deviation", "confidence", "features", "stub", "source", "note", "inferenceMs"}
    assert set(r["features"]) <= {"torsoAngle", "neckAngle"}


def test_clean_bounds_the_optional_text():
    out = model_server._clean({"label": "GOOD", "deviation": 0.1, "confidence": 1, "features": {"x": 1}, "source": "s" * 200,
                               "note": "n" * 500})
    assert len(out["note"]) == 160 and len(out["source"]) == 80
    assert "note" not in model_server._clean({"label": "GOOD", "note": "tab\tbad"})
