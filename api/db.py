"""The ONLY module that talks to Supabase.

`get_store()` returns an object with the Store interface below. Two implementations:
  * SupabaseStore: service-role key over the Supabase HTTP API (supabase-py). No connection pool,
    so it suits serverless. Used whenever SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY are set.
  * MemoryStore (api/db_memory.py): local dev / tests only. Refused on Vercel so a missing env var
    fails loudly instead of silently losing data.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from flask import current_app

PAGE = 1000  # PostgREST returns at most 1000 rows per request


class SupabaseStore:
    kind = "supabase"

    def __init__(self, url: str, key: str):
        from supabase import create_client  # lazy: keeps tests / memory mode dependency-light
        self.c = create_client(url, key)

    # ---- helpers
    def _t(self, name: str):
        return self.c.table(name)

    @staticmethod
    def _first(res) -> Optional[dict]:
        return res.data[0] if res.data else None

    # ---- users
    def create_user(self, dashboard_token_hash: str, pairing_code: str, pairing_expires_at: int,
                    settings: dict) -> dict:
        res = self._t("users").insert({
            "dashboard_token_hash": dashboard_token_hash, "pairing_code": pairing_code,
            "pairing_expires_at": pairing_expires_at, "settings": settings}).execute()
        return res.data[0]

    def _user_by(self, col: str, val: str) -> Optional[dict]:
        return self._first(self._t("users").select("*").eq(col, val).limit(1).execute())

    def get_user_by_dashboard_hash(self, h: str) -> Optional[dict]:
        return self._user_by("dashboard_token_hash", h)

    def get_user_by_device_hash(self, h: str) -> Optional[dict]:
        return self._user_by("device_token_hash", h)

    def get_user_by_pairing_code(self, code: str) -> Optional[dict]:
        return self._user_by("pairing_code", code)

    def update_user(self, user_id: str, fields: dict) -> None:
        self._t("users").update(fields).eq("id", user_id).execute()

    # ---- sessions
    def get_session(self, session_id: str) -> Optional[dict]:
        return self._first(self._t("sessions").select("*").eq("id", session_id).limit(1).execute())

    def latest_session(self, user_id: str) -> Optional[dict]:
        return self._first(self._t("sessions").select("*").eq("user_id", user_id)
                           .order("last_seen_server_ms", desc=True).limit(1).execute())

    def save_session(self, session: dict) -> None:
        self._t("sessions").upsert(session, on_conflict="id").execute()

    # ---- events
    def insert_events(self, rows: list[dict]) -> None:
        for i in range(0, len(rows), 500):  # keep request bodies small (seed data can be thousands)
            self._t("events").insert(rows[i:i + 500]).execute()

    def list_events(self, user_id: str, since: int, until: int) -> list[dict]:
        out: list[dict] = []
        start = 0
        while True:
            res = (self._t("events").select("*").eq("user_id", user_id).gte("t", since).lt("t", until)
                   .order("t").order("id").range(start, start + PAGE - 1).execute())
            out += res.data
            if len(res.data) < PAGE:
                return out
            start += PAGE

    def last_event_before(self, user_id: str, t: int) -> Optional[dict]:
        return self._first(self._t("events").select("*").eq("user_id", user_id).eq("kind", "transition")
                           .lt("t", t).order("t", desc=True).order("id", desc=True).limit(1).execute())

    def clear_history(self, user_id: str) -> None:
        self._t("events").delete().eq("user_id", user_id).execute()
        self._t("sessions").delete().eq("user_id", user_id).execute()

    # ---- push subscriptions
    def save_push_subscription(self, user_id: str, kind: str, endpoint: str, data: dict) -> None:
        self._t("push_subscriptions").upsert(
            {"user_id": user_id, "kind": kind, "endpoint": endpoint, "data": data},
            on_conflict="user_id,kind,endpoint").execute()

    def list_push_subscriptions(self, user_id: str, kind: Optional[str] = None) -> list[dict]:
        q = self._t("push_subscriptions").select("*").eq("user_id", user_id)
        if kind:
            q = q.eq("kind", kind)
        return q.execute().data

    def delete_push_subscription(self, user_id: str, kind: str, endpoint: str) -> None:
        (self._t("push_subscriptions").delete().eq("user_id", user_id).eq("kind", kind)
         .eq("endpoint", endpoint).execute())


_cached: Any = None


def make_store() -> Any:
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if url and key:
        return SupabaseStore(url, key)
    if os.environ.get("VERCEL"):
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set on Vercel")
    from api.db_memory import MemoryStore
    return MemoryStore(path=os.environ.get("DEV_DB_FILE", ".devdb.json"))


def get_store() -> Any:
    """Per-app store (tests inject one via app.config['STORE']); otherwise a lazily-built singleton."""
    global _cached
    injected = current_app.config.get("STORE")
    if injected is not None:
        return injected
    if _cached is None:
        _cached = make_store()
    return _cached
