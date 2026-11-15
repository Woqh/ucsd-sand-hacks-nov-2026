"""In-memory Store with the same interface as the PostgresStore in db.py.

Used for tests and for local dev when DATABASE_URL isn't set. When `path` is given it persists to
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
        self.checkins: list[dict] = []
        self.samples: list[dict] = []
        self.calibrations: list[dict] = []
        self._next_event_id = 1
        self._next_sub_id = 1
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.users, self.sessions = d["users"], d["sessions"]
                self.events, self.subs = d["events"], d["subs"]
                self.checkins = d.get("checkins", [])
                self.samples = d.get("samples", [])
                self.calibrations = d.get("calibrations", [])
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
                       "subs": self.subs, "checkins": self.checkins,
                       "samples": self.samples, "calibrations": self.calibrations}, f)
        os.replace(tmp, self._path)

    def ping(self) -> tuple[bool, Optional[str]]:
        return True, None

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
        """Upsert. Like the Postgres store, an existing row keeps its id/user_id/started_at and only
        last_t, last_seen_server_ms, state and last_sample change."""
        with self._lock:
            existing = self.sessions.get(session["id"])
            if existing:
                for k in ("last_t", "last_seen_server_ms", "state", "last_sample"):
                    existing[k] = copy.deepcopy(session.get(k))
            else:
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
            self.checkins = [c for c in self.checkins if c["user_id"] != user_id]
            self.samples = [x for x in self.samples if x["user_id"] != user_id]
            self._save()

    # ---- samples
    def insert_samples(self, rows: list[dict]) -> None:
        with self._lock:
            for r in rows:
                self.samples.append({k: r.get(k) for k in ("user_id", "session_id", "t", "state", "label", "deviation",
                                                           "confidence", "neck", "torso", "head_fwd")})
            self._save()

    def list_samples(self, user_id: str, since: int, until: int, limit: int = 50_000) -> list[dict]:
        with self._lock:
            out = [x for x in self.samples if x["user_id"] == user_id and since <= x["t"] < until]
            out.sort(key=lambda x: x["t"])
            return [{k: v for k, v in x.items() if k != "user_id"} for x in out[:limit]]

    def sample_rollup(self, user_id: str, since: int, until: int) -> list[dict]:
        """Same shape and semantics as the Postgres store (hourly, per state, UTC hours)."""
        with self._lock:
            groups: dict[tuple[int, Any], list[dict]] = {}
            for x in self.samples:
                if x["user_id"] == user_id and since <= x["t"] < until:
                    groups.setdefault(((x["t"] // 3_600_000) * 3_600_000, x["state"]), []).append(x)

            def avg(rows: list[dict], k: str) -> Optional[float]:
                vals = [r[k] for r in rows if r.get(k) is not None]
                return sum(vals) / len(vals) if vals else None

            return [{"hour": h, "state": st, "n": len(rows), "avg_dev": avg(rows, "deviation"),
                     "avg_neck": avg(rows, "neck"), "avg_torso": avg(rows, "torso"),
                     "avg_head_fwd": avg(rows, "head_fwd")}
                    for (h, st), rows in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1])))]

    # ---- calibration history
    def add_calibration(self, user_id: str, t: int, baseline: dict) -> None:
        with self._lock:
            self.calibrations.append({"user_id": user_id, "t": t, "baseline": copy.deepcopy(baseline)})
            self._save()

    def list_calibrations(self, user_id: str, limit: int = 20) -> list[dict]:
        with self._lock:
            mine = sorted((c for c in self.calibrations if c["user_id"] == user_id), key=lambda c: c["t"], reverse=True)
            return [{"t": c["t"], "baseline": copy.deepcopy(c["baseline"])} for c in mine[:limit]]

    # ---- pain check-ins
    def add_checkin(self, user_id: str, t: int, pain: int, area: Optional[str]) -> dict:
        with self._lock:
            c = {"id": max([x["id"] for x in self.checkins], default=0) + 1,
                 "user_id": user_id, "t": t, "pain": pain, "area": area}
            self.checkins.append(c)
            self._save()
            return copy.deepcopy(c)

    def list_checkins(self, user_id: str, limit: int = 100) -> list[dict]:
        with self._lock:
            mine = [c for c in self.checkins if c["user_id"] == user_id]
            return copy.deepcopy(sorted(mine, key=lambda c: (c["t"], c["id"]), reverse=True)[:limit])

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
