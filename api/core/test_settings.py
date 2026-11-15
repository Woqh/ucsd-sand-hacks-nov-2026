import pytest

from api.core.settings import DEFAULT_SETTINGS, SampleError, config_from_settings, merge_settings, parse_sample

SID = "123e4567-e89b-12d3-a456-426614174000"


def test_defaults_and_partial_merge():
    s, errs = merge_settings(None, {"slouchThresholdSec": 45, "alertChannels": {"desktop": False}})
    assert not errs
    assert s["slouchThresholdSec"] == 45
    assert s["alertChannels"] == {"phone": True, "desktop": False}
    assert s["cooldownSec"] == DEFAULT_SETTINGS["cooldownSec"]


def test_merge_does_not_mutate_defaults():
    merge_settings(None, {"alertChannels": {"phone": False}})
    assert DEFAULT_SETTINGS["alertChannels"]["phone"] is True


@pytest.mark.parametrize("patch", [
    {"slouchThresholdSec": 1}, {"slouchThresholdSec": "30"}, {"sensitivity": 1.5},
    {"cooldownSec": True}, {"alertChannels": {"phone": "yes"}}, {"alertChannels": 3},
    {"quietHours": {"start": "25:00"}}, {"quietHours": {"enabled": "no"}}, {"tzOffsetMin": 5000},
])
def test_rejects_bad_values(patch):
    _, errs = merge_settings(None, patch)
    assert errs


def test_unknown_keys_ignored():
    s, errs = merge_settings(None, {"nope": 1})
    assert not errs and "nope" not in s


def test_config_from_settings():
    s, _ = merge_settings(None, {"slouchThresholdSec": 20, "sensitivity": 1,
                                 "quietHours": {"enabled": True, "start": "23:30", "end": "06:15"},
                                 "tzOffsetMin": -480})
    c = config_from_settings(s)
    assert c.slouch_threshold_sec == 20 and c.sensitivity == 1.0
    assert c.quiet_hours_enabled and c.quiet_start_min == 23 * 60 + 30 and c.quiet_end_min == 6 * 60 + 15
    assert c.tz_offset_min == -480
    assert config_from_settings(None).slouch_threshold_sec == 30


def test_parse_sample_ok():
    sid, sample, feats = parse_sample({
        "schema": 1, "sessionId": SID.upper(), "t": 1731628800000, "label": "SLOUCHING",
        "deviation": 0.7, "confidence": 0.9, "features": {"neckAngle": 30.5, "bad": "x"}})
    assert sid == SID and sample.label == "SLOUCHING" and sample.deviation == 0.7
    assert feats == {"neckAngle": 30.5}


@pytest.mark.parametrize("payload", [
    None, {}, {"sessionId": "nope", "t": 1, "label": "GOOD"},
    {"sessionId": SID, "t": -1, "label": "GOOD"}, {"sessionId": SID, "t": 1, "label": "BAD"},
    {"sessionId": SID, "t": 1, "label": "GOOD", "deviation": -1},
    {"sessionId": SID, "t": 1, "label": "GOOD", "confidence": 2},
    {"sessionId": SID, "t": 1, "label": "GOOD", "features": [1]},
])
def test_parse_sample_rejects(payload):
    with pytest.raises(SampleError):
        parse_sample(payload)


# --------------------------------------------------------------------------- tone and focus mode
def test_tone_and_focus_defaults_and_validation():
    s, errs = merge_settings(None, {})
    assert s["nudgeTone"] == "gentle" and s["focus"] == {"onlyDuringFocus": False, "untilMs": 0}
    s, errs = merge_settings(None, {"nudgeTone": "direct", "focus": {"onlyDuringFocus": True, "untilMs": 1_731_672_000_000}})
    assert not errs and s["nudgeTone"] == "direct" and s["focus"] == {"onlyDuringFocus": True, "untilMs": 1_731_672_000_000}
    for bad in ({"nudgeTone": "angry"}, {"nudgeTone": 3}, {"focus": 1}, {"focus": {"onlyDuringFocus": "yes"}},
                {"focus": {"untilMs": -1}}, {"focus": {"untilMs": "soon"}}, {"focus": {"untilMs": 9e15}}):
        assert merge_settings(None, bad)[1], bad
    # a partial focus update keeps the other field
    s2, _ = merge_settings(s, {"focus": {"untilMs": 0}})
    assert s2["focus"] == {"onlyDuringFocus": True, "untilMs": 0}


def test_config_carries_focus_mode():
    c = config_from_settings(merge_settings(None, {"focus": {"onlyDuringFocus": True, "untilMs": 5000}})[0])
    assert c.focus_only is True and c.focus_until_ms == 5000
    assert config_from_settings(None).focus_only is False
