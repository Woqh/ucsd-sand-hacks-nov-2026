"""Gemini layer: validation, the wrapper (with a fake client + the REAL SDK config types), cost guard, and
the sync between the Python evidence facts and the web copy."""
import json
import pathlib
import re
from types import SimpleNamespace

import pytest

from api.ai import evidence_facts, gemini, prompts, schemas
from api.core.posture_profile import EXERCISE_IDS

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def valid_analysis(**over):
    base = {
        "headline": "You respond fast, and mid-afternoons are your weak spot",
        "summary": "You sit about 6 hours a day and slouch roughly 15% of it.",
        "howYouRespond": "You sit back up within 30 seconds after most first nudges.",
        "whatWorks": [{"insight": "Early, gentle nudges", "evidence": "82% fixed within 30 s"}],
        "strengths": ["Quick to recover"],
        "focusAreas": [{"title": "Afternoons", "why": "Highest slouch share", "action": "Stand up at 2 PM"}],
        "weeklyPlan": [{"when": "Daily", "action": "Chin tucks"}, {"when": "Mon", "action": "Raise screen"},
                       {"when": "Wed", "action": "Stand-up break at 3 PM"}],
        "recommendedExerciseIds": ["chin_tuck"],
        "suggestedTone": "gentle", "toneWhy": "You respond well to early nudges.",
        "confidence": "medium", "caveats": ["Only six weeks of data."],
    }
    return {**base, **over}


class FakeClient:
    def __init__(self, text=None, exc=None):
        self.text, self.exc, self.calls = text, exc, []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.exc:
            raise self.exc
        return SimpleNamespace(text=self.text)


# --------------------------------------------------------------------------- validator
def test_a_valid_analysis_passes_and_unknown_keys_are_dropped():
    out = schemas.parse_output(json.dumps({**valid_analysis(), "extra": "x", "focusAreas": [
        {"title": " A ", "why": "w", "action": "a", "surprise": 1}]}), schemas.ANALYSIS_SCHEMA)
    assert "extra" not in out and out["focusAreas"] == [{"title": "A", "why": "w", "action": "a"}]


@pytest.mark.parametrize("mutate", [
    lambda a: a.pop("headline"),
    lambda a: a.update(headline="x" * 141),
    lambda a: a.update(suggestedTone="angry"),
    lambda a: a.update(confidence="certain"),
    lambda a: a.update(recommendedExerciseIds=["not_a_real_exercise"]),
    lambda a: a.update(recommendedExerciseIds=["chin_tuck"] * 4),
    lambda a: a.update(weeklyPlan=[{"when": "Daily", "action": "x"}]),
    lambda a: a.update(focusAreas=[]),
    lambda a: a.update(whatWorks="not a list"),
    lambda a: a.update(strengths=[1, 2]),
])
def test_invalid_analyses_are_rejected(mutate):
    a = valid_analysis()
    mutate(a)
    with pytest.raises(schemas.AIOutputError):
        schemas.parse_output(json.dumps(a), schemas.ANALYSIS_SCHEMA)


def test_non_json_and_wrong_types_are_rejected():
    for bad in ("not json", "[]", "null", ""):
        with pytest.raises(schemas.AIOutputError):
            schemas.parse_output(bad, schemas.ANALYSIS_SCHEMA)
    ok = schemas.parse_output('{"answer": "hi", "basedOn": [], "outOfScope": false}', schemas.ASK_SCHEMA)
    assert ok["outOfScope"] is False
    with pytest.raises(schemas.AIOutputError):
        schemas.parse_output('{"answer": "hi", "basedOn": [], "outOfScope": "no"}', schemas.ASK_SCHEMA)


def test_settings_schema_ranges_and_the_exercise_enum_match_the_app():
    assert schemas.ANALYSIS_SCHEMA["properties"]["recommendedExerciseIds"]["items"]["enum"] == list(EXERCISE_IDS)
    with pytest.raises(schemas.AIOutputError):
        schemas.parse_output('{"explanation": "x", "slouchThresholdSec": 2}', schemas.SETTINGS_TEXT_SCHEMA)
    assert schemas.parse_output('{"explanation": "x", "sensitivity": 0.8}', schemas.SETTINGS_TEXT_SCHEMA)["sensitivity"] == 0.8


# --------------------------------------------------------------------------- wrapper
def test_config_is_built_from_the_real_sdk_types():
    from google.genai import types
    cfg = gemini.build_config("SYS", schemas.ASK_SCHEMA)
    assert isinstance(cfg, types.GenerateContentConfig)           # a wrong field name would raise right here
    assert cfg.system_instruction == "SYS" and cfg.response_mime_type == "application/json"
    assert cfg.response_json_schema == schemas.ASK_SCHEMA


def test_generate_json_sends_the_payload_and_returns_validated_output():
    fake = FakeClient(text=json.dumps(valid_analysis()))
    out = gemini.generate_json("SYS", {"habits": {"a": 1}}, schemas.ANALYSIS_SCHEMA, client=fake, model="m-1")
    assert out["headline"] and fake.calls[0]["model"] == "m-1"
    assert json.loads(fake.calls[0]["contents"]) == {"habits": {"a": 1}}


def test_failures_become_generic_ai_errors_without_leaking_details():
    secret = "AIzaSyFAKE-this-must-never-appear"
    with pytest.raises(gemini.AIError) as e:
        gemini.generate_json("S", {}, schemas.ASK_SCHEMA, client=FakeClient(exc=RuntimeError(f"401 bad key {secret}")))
    assert e.value.code == "ai_unavailable" and e.value.status == 502 and secret not in e.value.message
    with pytest.raises(gemini.AIError) as e:
        gemini.generate_json("S", {}, schemas.ASK_SCHEMA, client=FakeClient(text=""))
    assert e.value.code == "ai_empty"
    with pytest.raises(gemini.AIError) as e:
        gemini.generate_json("S", {}, schemas.ASK_SCHEMA, client=FakeClient(text='{"answer": 5}'))
    assert e.value.code == "ai_bad_output"


def test_not_configured_is_a_clear_503(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert gemini.configured() is False
    with pytest.raises(gemini.AIError) as e:
        gemini.generate_json("S", {}, schemas.ASK_SCHEMA)
    assert e.value.status == 503 and e.value.code == "ai_not_configured"
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-4-hydrogen")
    assert gemini.configured() and gemini.model_name() == "gemini-4-hydrogen"
    monkeypatch.delenv("GEMINI_MODEL")
    assert gemini.model_name() == gemini.DEFAULT_MODEL


def test_the_real_client_can_be_constructed_without_a_network_call(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key")
    client = gemini._real_client()
    assert hasattr(client.models, "generate_content")


def test_rate_limit_is_per_user_and_expires():
    gemini._calls.clear()
    for i in range(gemini.MAX_CALLS_PER_HOUR):
        gemini.check_rate("u1", now=1000.0 + i)
    with pytest.raises(gemini.AIError) as e:
        gemini.check_rate("u1", now=1010.0)
    assert e.value.status == 429 and e.value.code == "ai_rate_limited"
    gemini.check_rate("u2", now=1010.0)                          # another user is unaffected
    gemini.check_rate("u1", now=1000.0 + 3601 + gemini.MAX_CALLS_PER_HOUR)   # an hour later it clears
    gemini._calls.clear()


# --------------------------------------------------------------------------- prompts and evidence facts
def test_prompts_carry_the_guardrails():
    for p in (prompts.ANALYSIS_SYSTEM, prompts.ASK_SYSTEM):
        assert "Never give medical advice" in p and "null" in p
    assert "exerciseLibrary" in prompts.ANALYSIS_SYSTEM and "outOfScope" in prompts.ASK_SYSTEM
    assert all(f in prompts.ASK_SYSTEM for f in evidence_facts.FACTS)
    assert "medical advice" in prompts.SETTINGS_SYSTEM


def test_python_evidence_facts_match_the_web_copy():
    ts = (ROOT / "web/src/evidence.ts").read_text(encoding="utf-8")
    ts_urls = set(re.findall(r"url: '(https://[^']+)'", ts))
    assert {u for _, u in evidence_facts.SOURCES.values()} <= ts_urls          # every Python source URL is in the web copy
    for label, _url in evidence_facts.SOURCES.values():
        assert label in ts, label                                                # ...and so is its citation label
    cited = " ".join(evidence_facts.FACTS)
    for sid in evidence_facts.SOURCES:
        assert f"[{sid}]" in cited, sid                                          # every source is actually used by a fact
    facts = " ".join(evidence_facts.FACTS)
    for web, py in [("619 million", "619 million"), ("554–694 million", "554-694 million"), ("843 million", "843 million"),
                    ("759–933 million", "759-933 million"), ("203 million", "203 million"), ("163–253 million", "163-253 million")]:
        assert web in ts and py in facts, web
    assert "between ages 45 and 74" in facts and "peakAges: '45 and 74'" in ts
    assert "no consensus" in facts and "arthritis" in facts.lower()
