"""JSON schemas for what Gemini may return, plus a small validator.

Gemini enforces only a SUBSET of JSON Schema (it ignores length limits, for example), and model output
is untrusted data, so every response is parsed and validated here before anything uses it. Unknown
keys are dropped; anything that doesn't fit raises AIOutputError and the caller falls back to the
on-device analysis.
"""
from __future__ import annotations

import json
from typing import Any

from api.core.posture_profile import EXERCISE_IDS
from api.core.settings import TONES


class AIOutputError(ValueError):
    pass


def _str(n: int) -> dict[str, Any]:
    return {"type": "string", "maxLength": n}


def _list(items: dict[str, Any], lo: int, hi: int) -> dict[str, Any]:
    return {"type": "array", "minItems": lo, "maxItems": hi, "items": items}


def _obj(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required}


ANALYSIS_SCHEMA = _obj({
    "headline": _str(140),
    "summary": _str(700),                         # a plain-language profile of this person's sitting habits
    "howYouRespond": _str(500),                   # how they respond to being coached
    "whatWorks": _list(_obj({"insight": _str(200), "evidence": _str(200)}, ["insight", "evidence"]), 0, 4),
    "strengths": _list(_str(160), 0, 3),
    "focusAreas": _list(_obj({"title": _str(80), "why": _str(240), "action": _str(240)}, ["title", "why", "action"]), 1, 3),
    "weeklyPlan": _list(_obj({"when": _str(30), "action": _str(160)}, ["when", "action"]), 3, 5),
    "recommendedExerciseIds": _list({"type": "string", "enum": list(EXERCISE_IDS)}, 0, 3),
    "suggestedTone": {"type": "string", "enum": list(TONES)},
    "toneWhy": _str(240),
    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    "caveats": _list(_str(200), 0, 3),
}, ["headline", "summary", "howYouRespond", "whatWorks", "focusAreas", "weeklyPlan",
    "recommendedExerciseIds", "suggestedTone", "toneWhy", "confidence", "caveats"])

ASK_SCHEMA = _obj({
    "answer": _str(900),
    "basedOn": _list(_str(160), 0, 5),
    "outOfScope": {"type": "boolean"},
}, ["answer", "basedOn", "outOfScope"])

# Flat on purpose (simpler for the model); the route maps it onto a real settings patch and validates
# that patch with the same code the settings API uses.
SETTINGS_TEXT_SCHEMA = _obj({
    "explanation": _str(300),
    "slouchThresholdSec": {"type": "integer", "minimum": 5, "maximum": 300},
    "sensitivity": {"type": "number", "minimum": 0, "maximum": 1},
    "cooldownSec": {"type": "integer", "minimum": 15, "maximum": 900},
    "phoneAlerts": {"type": "boolean"},
    "desktopAlerts": {"type": "boolean"},
    "quietHoursEnabled": {"type": "boolean"},
    "quietStart": _str(5),
    "quietEnd": _str(5),
    "nudgeTone": {"type": "string", "enum": list(TONES)},
    "onlyDuringFocus": {"type": "boolean"},
}, ["explanation"])


def validate(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Errors (empty = valid) for the JSON Schema subset used above."""
    errs: list[str] = []
    t = schema.get("type")
    if t == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected object"]
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{path}.{k}: missing")
        for k, sub in schema.get("properties", {}).items():
            if k in value:
                errs += validate(value[k], sub, f"{path}.{k}")
    elif t == "array":
        if not isinstance(value, list):
            return [f"{path}: expected array"]
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{path}: too few items")
        if len(value) > schema.get("maxItems", 10**9):
            errs.append(f"{path}: too many items")
        for i, v in enumerate(value):
            errs += validate(v, schema.get("items", {}), f"{path}[{i}]")
    elif t == "string":
        if not isinstance(value, str):
            return [f"{path}: expected string"]
        if len(value) > schema.get("maxLength", 10**9):
            errs.append(f"{path}: too long")
    elif t in ("integer", "number"):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (t == "integer" and isinstance(value, float) and not value.is_integer()):
            return [f"{path}: expected {t}"]
        if value < schema.get("minimum", float("-inf")) or value > schema.get("maximum", float("inf")):
            errs.append(f"{path}: out of range")
    elif t == "boolean":
        if not isinstance(value, bool):
            return [f"{path}: expected boolean"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: not an allowed value")
    return errs


def prune(value: Any, schema: dict[str, Any]) -> Any:
    """Drop keys the schema doesn't declare (the model may add extras); strip strings."""
    if schema.get("type") == "object" and isinstance(value, dict):
        props = schema.get("properties", {})
        return {k: prune(v, props[k]) for k, v in value.items() if k in props}
    if schema.get("type") == "array" and isinstance(value, list):
        return [prune(v, schema.get("items", {})) for v in value]
    if isinstance(value, str):
        return value.strip()
    return value


def parse_output(text: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Parse the model's text as JSON and validate it against `schema`; raise AIOutputError otherwise."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        raise AIOutputError("the model did not return valid JSON")
    data = prune(data, schema)
    errs = validate(data, schema)
    if errs:
        raise AIOutputError("; ".join(errs[:4]))
    return data
