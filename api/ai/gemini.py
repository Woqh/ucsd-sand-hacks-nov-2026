"""Gemini, used for ONE thing: turning the de-identified habits pack into a coaching profile, answers and
settings suggestions. Optional: with no GEMINI_API_KEY every caller falls back to the on-device analysis.

PRIVACY / TERMS (docs/health-claims.md, docs/api.md): only the de-identified pack is ever sent (no
identity, no images, no pain data), only after the user opts in and can preview exactly what is sent.
Google's terms for the UNPAID Gemini API tier let Google use inputs for product improvement (with human
review) and forbid submitting personal or sensitive information, so use a key from a PAID (billing-
enabled) project. The terms also forbid using the service to provide medical advice, so every prompt
keeps it on habits and ergonomics.

Nothing returned here is stored by the server: the profile lives only in the user's browser.
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from typing import Any, Callable, Optional

from api.ai.schemas import AIOutputError, parse_output

DEFAULT_MODEL = "gemini-3.5-flash-lite"   # Google's recommendation for new projects: gemini-4-hydrogen or this
TIMEOUT_MS = 30_000
MAX_CALLS_PER_HOUR = 6                    # per user, best effort (per server process)


class AIError(Exception):
    """A failure the API reports as JSON; the dashboard falls back to the on-device analysis."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def model_name() -> str:
    return os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL


def build_config(system: str, schema: dict[str, Any]) -> Any:
    """The SDK's own config object, so field names are checked against the real library."""
    from google.genai import types
    return types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_json_schema=schema,
        temperature=0.4,
    )


def _real_client() -> Any:
    from google import genai          # imported lazily: only the AI endpoints pay for this import
    from google.genai import types
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(timeout=TIMEOUT_MS))


_client_factory: Callable[[], Any] = _real_client   # tests replace this


def generate_json(system: str, payload: dict[str, Any], schema: dict[str, Any], *,
                  model: Optional[str] = None, client: Any = None) -> dict[str, Any]:
    """Ask Gemini for JSON matching `schema` and return it validated. Raises AIError (never anything
    that could carry the API key or the payload)."""
    if client is None and not configured():
        raise AIError(503, "ai_not_configured", "AI analysis isn't enabled on this server.")
    cfg = build_config(system, schema)
    try:
        resp = (client or _client_factory()).models.generate_content(
            model=model or model_name(), contents=json.dumps(payload, separators=(",", ":")), config=cfg)
        text = resp.text
    except Exception as exc:           # network, auth, quota, safety blocks: report generically
        raise AIError(502, "ai_unavailable", "The AI service couldn't be reached right now.") from exc
    if not text:
        raise AIError(502, "ai_empty", "The AI service returned no answer.")
    try:
        return parse_output(text, schema)
    except AIOutputError as exc:
        raise AIError(502, "ai_bad_output", "The AI service returned something we couldn't use.") from exc


# ------------------------------------------------------------------ cost guard
_calls: dict[str, deque] = defaultdict(deque)


def check_rate(user_id: str, now: Optional[float] = None) -> None:
    """At most MAX_CALLS_PER_HOUR AI calls per user per hour (in-process, so a best-effort guard on a
    serverless host, not a hard quota)."""
    now = time.time() if now is None else now
    q = _calls[user_id]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= MAX_CALLS_PER_HOUR:
        raise AIError(429, "ai_rate_limited", "That's a lot of AI requests. Try again in a little while.")
    q.append(now)
