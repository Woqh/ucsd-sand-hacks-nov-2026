"""The capture loop with a fake camera, model and API: cadence, goal refresh, error handling, privacy."""
import pytest

from bridge.client import BridgeError
from bridge.engine import Engine
from bridge.fakes import NAMES, Clock, FakeApi, FakeCapture, FakeExtractor, FakePredictor, frame
from bridge.runner import Bridge


def make(frames, api, **kw):
    clock = Clock()
    logs = []
    pred = FakePredictor()
    b = Bridge(capture=FakeCapture(frames), engine=Engine(FakeExtractor(), pred, NAMES, "test/1"), api=api, facing="right",
               clock=clock, sleep=clock.sleep, wall_ms=lambda: 1_700_000_000_000 + int(clock.t * 1000), log=logs.append, **kw)
    return b, pred, logs, clock


def test_posts_about_once_a_second_not_once_per_frame():
    api = FakeApi()
    b, _, _, _ = make([frame()] * 20, api, interval_s=1.0, fps=5.0, is_file=True)
    summary = b.run()
    assert summary["frames"] == 20
    assert 4 <= len(api.sent) <= 5                    # 20 frames at 5 fps = 4 s


def test_each_reading_carries_a_new_session_id_the_model_name_and_only_contract_fields():
    api = FakeApi()
    b, _, _, _ = make([frame(4.0)] * 6, api, is_file=True)
    b.run()
    s = api.sent[0]
    assert s["sessionId"] == b.session_id and s["source"] == "test/1" and s["label"] == "GOOD"
    assert s["confidence"] == 0.9                      # the weakest of the two landmarks the angle used
    assert s["features"] == {"torsoAngle": 4.0, "neckAngle": 5.0}
    assert set(s) <= {"schema", "sessionId", "t", "label", "deviation", "confidence", "features", "source"}


def test_the_users_goal_posture_becomes_the_models_reference_and_updates_when_it_changes():
    api = FakeApi(goal=12.0)
    b, pred, logs, clock = make([frame(14.0)] * 12, api, goal_every_s=2.0, fps=5.0, is_file=True)
    b.run(max_frames=4)
    assert pred.neutral == 12.0 and api.sent[0]["label"] == "GOOD" and api.sent[0]["deviation"] == 0.08
    api.goal = 4.0                                    # recalibrated from the dashboard
    b.run(max_frames=8)
    assert pred.neutral == 4.0 and any("4.0 deg from vertical" in m for m in logs)


def test_not_calibrated_means_upright_is_the_reference():
    b, pred, logs, _ = make([frame()] * 3, FakeApi(goal=None), is_file=True)
    b.run()
    assert pred.neutral == 0.0


def test_the_facing_direction_and_roll_are_passed_to_the_model():
    b, pred, _, _ = make([frame()] * 2, FakeApi(), is_file=True, camera_roll_deg=2.5)
    b.run()
    assert pred.calls[0] == ("side", "right", 2.5)


def test_nobody_in_view_sends_away_and_two_people_send_unknown():
    api = FakeApi()
    b, _, _, _ = make([frame(people=0), frame(people=2)], api, interval_s=0, fps=0, is_file=True)
    b.run()
    assert [s["label"] for s in api.sent] == ["AWAY", "UNKNOWN"]
    assert b.stats["abstained"] == 2


def test_a_network_failure_is_logged_not_fatal():
    api = FakeApi(fail=BridgeError(0, "network", "Can't reach the server"))
    b, _, logs, _ = make([frame()] * 8, api, fps=5.0, is_file=True)
    summary = b.run()
    assert summary["frames"] == 8 and summary["posted"] == 0 and summary["failed"] >= 1
    assert sum("couldn't send" in m for m in logs) == 1   # rate-limited, not one line per frame


@pytest.mark.parametrize("error", [BridgeError(401, "unauthorized", "bad token"), BridgeError(400, "clock_skew", "check your clock")])
def test_a_rejected_token_or_clock_stops_the_loop(error):
    b, _, _, _ = make([frame()] * 5, FakeApi(fail=error), is_file=True)
    with pytest.raises(BridgeError):
        b.run()


def test_dry_run_sends_nothing(capsys):
    b, _, logs, _ = make([frame()] * 3, None, is_file=True)
    b.run()
    assert any("[dry run]" in m for m in logs)


def test_a_video_file_ends_but_a_looping_one_starts_over():
    b, _, _, _ = make([frame()] * 3, FakeApi(), is_file=True)
    assert b.run()["frames"] == 3
    b2, _, _, _ = make([frame()] * 3, FakeApi(), is_file=True, loop_video=True, rewind=None)
    cap = b2.capture
    b2.rewind = cap.rewind
    assert b2.run(max_frames=10)["frames"] == 10 and cap.rewinds >= 3


def test_a_camera_that_stops_delivering_raises_after_retries():
    b, _, _, _ = make([], FakeApi(), is_file=False)
    with pytest.raises(RuntimeError):
        b.run()


def test_preview_keys_change_facing_and_quit():
    keys = iter([None, "left", "quit"])
    b, pred, _, _ = make([frame()] * 10, FakeApi(), is_file=True, preview=lambda *a: next(keys))
    summary = b.run()
    assert summary["frames"] == 3 and b.facing == "left"


def test_a_single_spiky_neck_reading_is_smoothed_away():
    class Spiky(FakePredictor):
        necks = iter([40.0, 41.0, -30.0, 40.0, 42.0])

        def analyze(self, pose, viewpoint, facing, roll):
            out = super().analyze(pose, viewpoint, facing, roll)
            out["measurements"]["neck_inclination_deg"] = next(self.necks)
            return out

    api = FakeApi()
    clock = Clock()
    b = Bridge(capture=FakeCapture([frame()] * 5), engine=Engine(FakeExtractor(), Spiky(), NAMES, "t"), api=api, facing="right",
               clock=clock, sleep=clock.sleep, log=lambda m: None, is_file=True, interval_s=0, fps=0)
    b.run()
    necks = [s["features"]["neckAngle"] for s in api.sent]
    assert necks[2] == 40.0 and min(necks) >= 40.0          # the -30 spike never reaches the server
