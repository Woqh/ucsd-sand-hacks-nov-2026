"""The shared engine (frame -> PostureSample) with fake pose + angle models."""
from bridge import adapter
from bridge.engine import Engine, note_for
from bridge.fakes import NAMES, FakeExtractor, FakePredictor, frame


def engine(**kw):
    pred = FakePredictor()
    return Engine(FakeExtractor(), pred, NAMES, "test/1", **kw), pred


def run(eng, f, facing="right"):
    return eng.analyze(f, facing, session_id="11111111-1111-4111-8111-111111111111", t_ms=1_700_000_000_000)


def test_a_frame_becomes_a_contract_sample_carrying_the_model_name():
    eng, _ = engine()
    _, result, s = run(eng, frame(4.0))
    assert (s["label"], s["source"], s["t"]) == ("GOOD", "test/1", 1_700_000_000_000)
    assert s["features"] == {"torsoAngle": 4.0, "neckAngle": 5.0}
    assert adapter.validate_outgoing(s)
    assert result["prediction_valid"]


def test_the_goal_posture_is_the_reference_and_only_a_change_resets_the_model():
    eng, pred = engine()
    assert eng.set_goal(None) is False and pred.neutral == 0.0      # not calibrated: vertical, nothing to reset
    assert eng.set_goal(12.0) is True and pred.neutral == 12.0
    assert eng.set_goal(12.0) is False
    assert eng.set_goal(None) is True and pred.neutral == 0.0
    eng.set_goal(12.0)
    assert run(eng, frame(14.0))[2]["label"] == "GOOD"              # 14 deg is on a 12 deg goal


def test_no_person_is_away_and_unknown_facing_is_unknown_with_a_reason():
    eng, _ = engine()
    _, r, s = run(eng, frame(people=0))
    assert s["label"] == "AWAY" and note_for(r, s) == "Nobody in view."
    _, r, s = run(eng, frame(), facing="unknown")
    assert s["label"] == "UNKNOWN" and s["confidence"] == 0.0
    assert "Pick which way you face" in note_for(r, s)


def test_a_good_reading_has_no_note():
    eng, _ = engine()
    _, r, s = run(eng, frame())
    assert note_for(r, s) is None


def test_the_neck_median_resets_when_the_facing_changes_or_the_person_leaves():
    class Neck(FakePredictor):
        values = iter([10.0, 50.0, 10.0, 10.0])

        def analyze(self, pose, viewpoint, facing, roll):
            out = super().analyze(pose, viewpoint, facing, roll)
            out["measurements"]["neck_inclination_deg"] = next(self.values)
            return out

    eng = Engine(FakeExtractor(), Neck(), NAMES, "t", neck_median_frames=3)
    assert run(eng, frame())[2]["features"]["neckAngle"] == 10.0
    assert run(eng, frame())[2]["features"]["neckAngle"] == 30.0        # median of 10 and 50
    assert run(eng, frame(), facing="left")[2]["features"]["neckAngle"] == -10.0   # history cleared by the new facing (sign flips too)
    run(eng, frame(people=0))                                             # leaving clears it again
    assert not eng._neck
