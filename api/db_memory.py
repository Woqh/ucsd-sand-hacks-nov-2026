"""In-memory Store with the same interface as the Supabase one in db.py.

Used for tests and for local dev when SUPABASE_URL isn't set. When `path` is given it persists to
a JSON file after every write, so Flask's debug reloader doesn't wipe your paired device.
Never used on Vercel (db.get_store refuses to fall back to it there).
"""
from __future__ import annotations

import copy
import json
import os
import threading
import uuid
from typing import Any, Optional


class MemoryStore:
    kind = "memory"

    def __init__(self, path: Optional[str] = None):
        self._lock = threading.RLock()
        self._path = path
        self.users: dict[str, dict] = {}
        self.sessions: dict[str, dict] = {}
        self.events: list[dict] = []
        self.subs: list[dict] = []
        self._next_event_id = 1
        self._next_sub_id = 1
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.users, self.sessions = d["users"], d["sessions"]
                self.events, self.subs = d["events"], d["subs"]
                self._next_event_id = max([e["id"] for e in self.events], default=0) + 1
                self._next_sub_id = max([s["id"] for s in self.subs], default=0) + 1
            except Exception:
                pass  # corrupt dev file: start fresh

    def _save(self) -> None:
        if not self._path:
            return
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"users": self.users, "sessions": self.sessions, "events": self.events,
                       "subs": self.subs}, f)
        os.replace(tmp, self._path)

    # ---- users
    def create_user(self, dashboard_token_hash: str, pairing_code: str, pairing_expires_at: int,
                    settings: dict) -> dict:
        with self._lock:
            u = {"id": str(uuid.uuid4()), "dashboard_token_hash": dashboard_token_hash,
                 "device_token_hash": None, "pairing_code": pairing_code,
                 "pairing_expires_at": pairing_expires_at, "settings": copy.deepcopy(settings),
                 "calibration": None}
            self.users[u["id"]] = u
            self._save()
            return copy.deepcopy(u)

    def _find_user(self, field: str, value: str) -> Optional[dict]:
        for u in self.users.values():
            if u.get(field) == value:
                return copy.deepcopy(u)
        return None

    def get_user_by_dashboard_hash(self, h: str) -> Optional[dict]:
        with self._lock:
            return self._find_user("dashboard_token_hash", h)

    def get_user_by_device_hash(self, h: str) -> Optional[dict]:
        with self._lock:
            return self._find_user("device_token_hash", h)

    def get_user_by_pairing_code(self, code: str) -> Optional[dict]:
        with self._lock:
            return self._find_user("pairing_code", code)

    def update_user(self, user_id: str, fields: dict) -> None:
        with self._lock:
            self.users[user_id].update(copy.deepcopy(fields))
            self._save()

    # ---- sessions
    def get_session(self, session_id: str) -> Optional[dict]:
        with self._lock:
            s = self.sessions.get(session_id)
            return copy.deepcopy(s) if s else None

    def latest_session(self, user_id: str) -> Optional[dict]:
        with self._lock:
            mine = [s for s in self.sessions.values() if s["user_id"] == user_id]
            return copy.deepcopy(max(mine, key=lambda s: s["last_seen_server_ms"])) if mine else None

    def save_session(self, session: dict) -> None:
        with self._lock:
            self.sessions[session["id"]] = copy.deepcopy(session)
            self._save()

    # ---- events
    def insert_events(self, rows: list[dict]) -> None:
        with self._lock:
            for r in rows:
                r = copy.deepcopy(r)
                r["id"] = self._next_event_id
                self._next_event_id += 1
                self.events.append(r)
            self._save()

    def list_events(self, user_id: str, since: int, until: int) -> list[dict]:
        with self._lock:
            out = [e for e in self.events if e["user_id"] == user_id and since <= e["t"] < until]
            return copy.deepcopy(sorted(out, key=lambda e: (e["t"], e["id"])))

    def last_event_before(self, user_id: str, t: int) -> Optional[dict]:
        with self._lock:
            mine = [e for e in self.events if e["user_id"] == user_id and e["t"] < t
                    and e.get("kind", "transition") == "transition"]
            return copy.deepcopy(max(mine, key=lambda e: (e["t"], e["id"]))) if mine else None

    def clear_history(self, user_id: str) -> None:
        with self._lock:
            self.events = [e for e in self.events if e["user_id"] != user_id]
            self.sessions = {k: s for k, s in self.sessions.items() if s["user_id"] != user_id}
            self._save()

    # ---- push subscriptions
    def save_push_subscription(self, user_id: str, kind: str, endpoint: str, data: dict) -> None:
        with self._lock:
            for s in self.subs:
                if s["user_id"] == user_id and s["kind"] == kind and s["endpoint"] == endpoint:
                    s["data"] = copy.deepcopy(data)
                    break
            else:
                self.subs.append({"id": self._next_sub_id, "user_id": user_id, "kind": kind,
                                  "endpoint": endpoint, "data": copy.deepcopy(data)})
                self._next_sub_id += 1
            self._save()

    def list_push_subscriptions(self, user_id: str, kind: Optional[str] = None) -> list[dict]:
        with self._lock:
            return copy.deepcopy([s for s in self.subs if s["user_id"] == user_id
                                  and (kind is None or s["kind"] == kind)])

    def delete_push_subscription(self, user_id: str, kind: str, endpoint: str) -> None:
        with self._lock:
            self.subs = [s for s in self.subs if not (s["user_id"] == user_id and s["kind"] == kind
                                                      and s["endpoint"] == endpoint)]
            self._save()
